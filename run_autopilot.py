#!/usr/bin/env python3
"""
Main Autonomous CLI & Daemon Entrypoint for Polymarket Autopilot.
Executes a full AI-driven cycle with file locking (`fcntl.flock`) and live-data guardrails:
  1. Fetch live Polymarket contracts (refuses to execute fake trades if offline fallback is active)
  2. Mark-to-market open positions against live orderbook bids & run AI Autonomous Exit Manager
  3. Generate quantitative signals across 3 strategies
  4. Audit candidate signals via Antigravity CLI (`agy -p`) / AI Analyst + 7-Gate Risk Manager
  5. Execute paper trades, sync `docs/state.json` and `web/src/data/initial-state.json`.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from typing import Dict, List, Optional

from src.argon_entry import ArgonEntryGate, EntryReview
from src.execution import ExecutionBooks
from src.ai_analyst import AutonomousAIAnalyst
from src.config import BASE_DIR, DEFAULT_CONFIG, LOCK_FILE_PATH, STATE_JSON_PATH, TradingConfig
from src.paper_trader import PaperTrader
from src.polymarket_client import MarketContract, PolymarketClient
from src.risk_manager import RiskDecision, RiskManager
from src.strategy_engine import StrategyEngine


def sync_web_publish_dir(auto_push: bool = False) -> None:
    """
    Syncs dashboard.html -> docs/index.html, data/portfolio_state.json -> docs/state.json,
    and updates web/src/data/initial-state.json for Next.js / Vercel deployments.
    """
    docs_dir = BASE_DIR / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dashboard_file = BASE_DIR / "dashboard.html"
    if dashboard_file.exists():
        shutil.copyfile(dashboard_file, docs_dir / "index.html")
    if STATE_JSON_PATH.exists():
        shutil.copyfile(STATE_JSON_PATH, docs_dir / "state.json")
        nextjs_snapshot = BASE_DIR / "web" / "src" / "data" / "initial-state.json"
        if nextjs_snapshot.parent.exists():
            shutil.copyfile(STATE_JSON_PATH, nextjs_snapshot)

    if auto_push:
        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(BASE_DIR),
                    "add",
                    "docs/index.html",
                    "docs/state.json",
                    "data/portfolio_state.json",
                    "web/src/data/initial-state.json",
                ],
                check=False,
            )
            subprocess.run(
                ["git", "-C", str(BASE_DIR), "commit", "-m", "chore(autopilot): autonomous AI state update"],
                capture_output=True,
                check=False,
            )
            subprocess.run(["git", "-C", str(BASE_DIR), "push"], capture_output=True, timeout=15, check=False)
        except Exception as exc:
            sys.stderr.write(f"[git auto-push warn] {exc}\n")


def _apply_conservative_argon_sizing(
    sig, decision, entry_review, metrics, open_ids, risk_manager, trader,
):
    """Re-size an Argon-approved order conservatively using the model's chosen-side probability.

    The model probability is for the CHOSEN side (YES for BUY_YES/BUY_BUNDLE legs, NO for
    BUY_NO). We take min(strategy fair_value, model prob) as the win probability, re-run the
    exact same risk gates, and cap the result at the original size. The allocation is NEVER
    larger than the initial sizing, and if the conservative probability erases the edge the
    entry is blocked.
    """
    prob = entry_review.chosen_side_prob
    if prob is None:
        return decision
    conservative_p = min(float(sig.fair_value), float(prob))
    resized = replace(sig, fair_value=conservative_p)
    d2 = risk_manager.evaluate_signal(
        signal=resized,
        total_equity_usdc=metrics["total_equity_usdc"],
        available_cash_usdc=metrics["cash_usdc"],
        current_exposure_usdc=metrics["current_exposure_usdc"],
        daily_pnl_usdc=metrics.get("daily_pnl_usdc", 0.0),
        open_market_ids=open_ids,
        strategy_exposure_usdc=trader.strategy_exposure(sig.strategy),
        daily_risk_reference_usdc=metrics["daily_risk_reference_usdc"],
    )
    if not d2.approved:
        return replace(
            decision, approved=False, recommended_size_usdc=0.0, shares_qty=0.0,
            reject_reason=f"ARGON_CONSERVATIVE_RESIZE_BLOCKED: {d2.reject_reason}",
        )
    capped = min(d2.recommended_size_usdc, decision.recommended_size_usdc)
    return replace(
        decision,
        recommended_size_usdc=capped,
        shares_qty=capped / decision.entry_price,
        risk_checks_passed=decision.risk_checks_passed
        + [f"ARGON_CONSERVATIVE_SIZED_${capped:.2f}_P{conservative_p:.3f}"],
    )


def run_cycle(
    limit: int = 40,
    verbose: bool = True,
    auto_push: bool = False,
    config: Optional[TradingConfig] = None,
) -> dict:
    cfg = config or DEFAULT_CONFIG
    LOCK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(LOCK_FILE_PATH, "w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Another cycle is currently executing; return latest persisted state
            if STATE_JSON_PATH.exists():
                return json.loads(STATE_JSON_PATH.read_text(encoding="utf-8"))
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        client = PolymarketClient(cfg)
        strategy_engine = StrategyEngine(cfg)
        risk_manager = RiskManager(cfg)
        ai_analyst = AutonomousAIAnalyst(use_agy_cli=True)
        trader = PaperTrader(cfg)

        # Mandatory Argon entry-review gate. Shares the dual-account router so quota failover
        # and the honest configured/cooldown state are consistent with the rest of the system.
        entry_gate = ArgonEntryGate(cfg, ai_analyst.account_router, clock=trader._now)
        entry_gate.begin_cycle()

        # Legacy PENDING_MAKER orders created before this gate carry no genuine APPROVE and
        # must not fill unaudited on restart: cancel & refund them before any lifecycle step.
        legacy_refunded = trader.migrate_legacy_pending_orders()

        cycle_num = trader.increment_cycle()

        # Step 1: Fetch active Polymarket contracts
        contracts = client.fetch_active_markets(limit=limit)
        trader.set_reference_time(client.server_now)
        contracts_by_id: Dict[str, MarketContract] = {c.market_id: c for c in contracts}
        is_live_data = client.last_source == "LIVE_POLYMARKET_GAMMA_API"
        can_trade = is_live_data or cfg.allow_snapshot_trading

        if is_live_data:
            for mid in trader.held_market_ids():
                held = client.fetch_market(mid)
                if held is not None:
                    contracts_by_id[mid] = held
        valuation_contracts = list(contracts_by_id.values())
        books = ExecutionBooks(client, valuation_contracts)

        # Step 2: Mark-to-market existing positions & run AI Autonomous Exit Manager (only on live data)
        if can_trade:
            trader.mark_with_books(books)
            before = trader.get_account_metrics()
            if before["daily_pnl_usdc"] <= -before["daily_risk_reference_usdc"] * cfg.max_daily_drawdown_pct:
                trader.cancel_pending()
            # Expired entry approvals must be re-reviewed: refund them so they cannot fill
            # at the execution boundary until a fresh Argon APPROVE re-proposes them.
            expired_refunded = trader.cancel_expired_pending_reviews()
            trader.process_lifecycle(valuation_contracts, books)
            open_positions = trader.mark_with_books(books)
            exit_decisions = ai_analyst.evaluate_open_positions(open_positions)
            closed_count = trader.execute_ai_exits(exit_decisions)
        else:
            closed_count = 0
            expired_refunded = 0

        # Step 3: Generate quantitative signals across 3 strategies
        signals = strategy_engine.evaluate_markets(contracts)

        # Step 4: 7-Gate Risk sizing + CLOB depth, THEN a mandatory genuine Argon entry review
        # of the whole order (all legs, chosen side, live price, rules, expiry, size) before any
        # paper money is reserved/spent. Only an Argon APPROVE opens a trade.
        decisions: List[RiskDecision] = []
        entry_reviews = []
        for sig in signals:
            metrics = trader.get_account_metrics()
            open_ids = trader.get_open_market_ids()

            if set(sig.leg_market_ids) & (open_ids | trader.held_market_ids()):
                open_ids.add(sig.market_id)
            already_open = sig.market_id in (open_ids | trader.held_market_ids())
            if already_open:
                open_ids.add(sig.market_id)
            entry_review: Optional[EntryReview] = None
            approval_expires_at = ""

            if not can_trade:
                decision = RiskDecision(
                    signal_id=sig.signal_id,
                    market_id=sig.market_id,
                    question=sig.question,
                    strategy=sig.strategy,
                    approved=False,
                    recommended_size_usdc=0.0,
                    shares_qty=0.0,
                    entry_price=sig.entry_price,
                    reject_reason=(
                        f"OFFLINE_SNAPSHOT_PROTECTION: Nguồn dữ liệu hiện tại là {client.last_source}. "
                        f"Tạm khóa mở lệnh mới cho tới khi kết nối trực tiếp Polymarket Gamma API."
                    ),
                    risk_checks_passed=[],
                )
                decisions.append(decision)
                continue

            decision = risk_manager.evaluate_signal(
                signal=sig,
                total_equity_usdc=metrics["total_equity_usdc"],
                available_cash_usdc=metrics["cash_usdc"],
                current_exposure_usdc=metrics["current_exposure_usdc"],
                daily_pnl_usdc=metrics.get("daily_pnl_usdc", 0.0),
                open_market_ids=open_ids,
                strategy_exposure_usdc=trader.strategy_exposure(sig.strategy),
                daily_risk_reference_usdc=metrics["daily_risk_reference_usdc"],
            )

            # Pre-inference CLOB depth check: cheap gate before paying for an Argon call.
            decision = books.validate(sig, decision)

            if decision.approved and cfg.require_argon_entry_review:
                # Expose the proposed size to the model so it can critique risk/size context.
                setattr(sig, "_proposed_size_usdc", decision.recommended_size_usdc)
                entry_review = entry_gate.review_order(sig, contracts_by_id)
                if entry_review.status != "APPROVE":
                    reason = (
                        f"ARGON_{entry_review.status}: "
                        f"{entry_review.reject_reason or entry_review.reasoning}"
                    )
                    decision = replace(
                        decision, approved=False, recommended_size_usdc=0.0,
                        shares_qty=0.0, reject_reason=reason,
                    )
                else:
                    decision = _apply_conservative_argon_sizing(
                        sig, decision, entry_review, metrics, open_ids,
                        risk_manager, trader,
                    )
                    if decision.approved:
                        # Re-fetch CLOB books AFTER the slow inference and re-validate so a
                        # stale pre-inference quote can never authorize execution.
                        fresh_books = ExecutionBooks(client, valuation_contracts)
                        decision = fresh_books.validate(sig, decision)
                    if decision.approved:
                        approval_expires_at = entry_gate.approval_expires_at(entry_review)
            elif decision.approved and not cfg.require_argon_entry_review:
                # Explicit deterministic mode (tests / offline): recorded honestly, never
                # presented as a genuine AI inference.
                decision = replace(
                    decision,
                    risk_checks_passed=decision.risk_checks_passed + ["DETERMINISTIC_ENTRY_MODE"],
                )

            if entry_review is not None:
                entry_reviews.append(dict(entry_review.to_dict(), question=sig.question, market_id=sig.market_id))
            decisions.append(decision)
            if not already_open:
                trader.record_and_execute(
                    sig, decision, entry_review=entry_review,
                    approval_expires_at=approval_expires_at,
                )

        # Step 5: Final mark-to-market & AI Self-Tuning Executive Summary
        if can_trade:
            trader.mark_with_books(books)
        final_metrics = trader.get_account_metrics()
        ai_summary = ai_analyst.generate_self_tuning_summary(
            final_metrics,
            len(decisions),
            data_source=client.last_source,
            now=trader._now(),
        )

        entry_review_summary = {
            "mode": "ARGON_REQUIRED" if cfg.require_argon_entry_review else "DETERMINISTIC_TEST",
            "provider": "argon_cli",
            "model": cfg.argon_model,
            "cli_available": bool(entry_gate.binary),
            "calls_made": entry_gate.calls_made,
            "max_calls_per_cycle": cfg.argon_max_calls_per_cycle,
            "approval_ttl_sec": cfg.argon_approval_ttl_sec,
            "legacy_pending_refunded": legacy_refunded,
            "expired_pending_refunded": expired_refunded,
            "approved_count": sum(1 for r in entry_reviews if r["status"] == "APPROVE"),
            "blocked_count": sum(1 for r in entry_reviews if r["status"] != "APPROVE"),
            "reviews": entry_reviews[:25],
        }

        state = trader.export_full_state(
            data_source=client.last_source,
            contracts=contracts,
            signals=signals,
            decisions=decisions,
            ai_summary=ai_summary,
            entry_review=entry_review_summary,
        )

        sync_web_publish_dir(auto_push=auto_push)

        if verbose:
            m = state["metrics"]
            print("=" * 78)
            print(f" POLYMARKET AI AUTOPILOT - CYCLE #{cycle_num} ({ai_summary['ai_mode']})")
            print("=" * 78)
            print(f" AGY CLI Bridge     : {ai_summary.get('agy_cli_path', 'active')}")
            print(f" Data Source        : {state['data_source']}")
            print(
                f" Entry Review Mode  : {entry_review_summary['mode']} "
                f"(model {entry_review_summary['model']}, CLI {'found' if entry_review_summary['cli_available'] else 'MISSING'}, "
                f"{entry_review_summary['calls_made']} calls, "
                f"{entry_review_summary['approved_count']} APPROVE / {entry_review_summary['blocked_count']} blocked)"
            )
            if legacy_refunded or expired_refunded:
                print(
                    f" Pending Refunds    : {legacy_refunded} legacy unreviewed, "
                    f"{expired_refunded} expired approvals cancelled & refunded"
                )
            print(f" Markets Scanned    : {state['scanned_markets_count']} active contracts")
            print(f" AI Auto-Exits      : {closed_count} positions closed with profit/stop")
            approved_cnt = sum(1 for d in decisions if d.approved)
            rejected_cnt = sum(1 for d in decisions if not d.approved)
            print(f" New Entry Signals  : {approved_cnt} APPROVED | {rejected_cnt} SKIPPED/BLOCKED")
            print("-" * 78)
            print(
                f" Total Equity       : ${m['total_equity_usdc']:,.2f} USDC "
                f"(Cash: ${m['cash_usdc']:,.2f} | Deployed: ${m['current_exposure_usdc']:,.2f})"
            )
            print(
                f" Total PnL          : {m['total_pnl_usdc']:+,.2f} USDC ({m['return_pct']:+.2f}%) "
                f"[Realized: {m['realized_pnl_usdc']:+,.2f} | Unrealized: {m['unrealized_pnl_usdc']:+,.2f}]"
            )
            print(f" AI Regime Note     : {ai_summary['executive_summary']}")
            print("=" * 78)

        return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket Autonomous AI Autopilot")
    parser.add_argument("--limit", type=int, default=40, help="Number of active events to scan")
    parser.add_argument("--json", action="store_true", help="Output state as JSON")
    parser.add_argument("--auto-push", action="store_true", help="Auto commit and git push docs/state.json for remote Web UI")
    parser.add_argument("--daemon", action="store_true", help="Run continuously 24/7 in autonomous loop")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between autonomous cycles in daemon mode")
    args = parser.parse_args()

    if args.daemon:
        print(f"[AI AUTOPILOT DAEMON] Starting 24/7 zero-touch loop (interval: {args.interval}s)...")
        while True:
            try:
                run_cycle(limit=args.limit, verbose=True, auto_push=args.auto_push)
            except Exception as exc:
                print(f"[AI AUTOPILOT WARN] Cycle error recovered: {exc}")
            time.sleep(max(5, args.interval))
    else:
        state = run_cycle(limit=args.limit, verbose=not args.json, auto_push=args.auto_push)
        if args.json:
            print(json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
