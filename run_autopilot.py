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
from typing import Dict, List, Optional

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
            trader.process_lifecycle(valuation_contracts, books)
            open_positions = trader.mark_with_books(books)
            exit_decisions = ai_analyst.evaluate_open_positions(open_positions)
            closed_count = trader.execute_ai_exits(exit_decisions)
        else:
            closed_count = 0

        # Step 3: Generate quantitative signals across 3 strategies
        signals = strategy_engine.evaluate_markets(contracts)

        # Step 4: Antigravity CLI (`agy -p`) / AI Audit + 7-Gate Risk Check
        decisions: List[RiskDecision] = []
        for sig in signals:
            metrics = trader.get_account_metrics()
            open_ids = trader.get_open_market_ids()

            if set(sig.leg_market_ids) & (open_ids | trader.held_market_ids()):
                open_ids.add(sig.market_id)
            already_open = sig.market_id in (open_ids | trader.held_market_ids())
            if already_open:
                open_ids.add(sig.market_id)
            ai_audit = None

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

            decision = books.validate(sig, decision)
            if decision.approved:
                for audit_id in sig.leg_market_ids or [sig.market_id]:
                    ai_audit = ai_analyst.audit_signal(sig, contracts_by_id.get(audit_id))
                    if ai_audit.ai_verdict == "VETO_TRAP":
                        break

            if ai_audit and ai_audit.ai_verdict == "VETO_TRAP" and decision.approved:
                decision = RiskDecision(
                    signal_id=sig.signal_id,
                    market_id=sig.market_id,
                    question=sig.question,
                    strategy=sig.strategy,
                    approved=False,
                    recommended_size_usdc=0.0,
                    shares_qty=0.0,
                    entry_price=sig.entry_price,
                    reject_reason=ai_audit.ai_reasoning,
                    risk_checks_passed=decision.risk_checks_passed,
                )

            decisions.append(decision)
            if not already_open:
                trader.record_and_execute(sig, decision, ai_audit=ai_audit)

        # Step 5: Final mark-to-market & AI Self-Tuning Executive Summary
        if can_trade:
            trader.mark_with_books(books)
        final_metrics = trader.get_account_metrics()
        ai_summary = ai_analyst.generate_self_tuning_summary(
            final_metrics,
            len(decisions),
            data_source=client.last_source,
        )

        state = trader.export_full_state(
            data_source=client.last_source,
            contracts=contracts,
            signals=signals,
            decisions=decisions,
            ai_summary=ai_summary,
        )

        sync_web_publish_dir(auto_push=auto_push)

        if verbose:
            m = state["metrics"]
            print("=" * 78)
            print(f" POLYMARKET AI AUTOPILOT - CYCLE #{cycle_num} ({ai_summary['ai_mode']})")
            print("=" * 78)
            print(f" AGY CLI Bridge     : {ai_summary.get('agy_cli_path', 'active')}")
            print(f" Data Source        : {state['data_source']}")
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
