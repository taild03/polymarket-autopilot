#!/usr/bin/env python3
"""
Main Autonomous CLI & Daemon Entrypoint for Polymarket Autopilot.
Executes a full AI-driven cycle:
  1. Fetch live Polymarket contracts
  2. Mark-to-market open positions & run AI Autonomous Exit Manager (Take-Profit / Stop-Loss)
  3. Generate quantitative signals across 3 strategies
  4. Audit candidate signals via Antigravity CLI (`agy -p`) / AI Semantic Analyst + 7-Gate Risk Manager
  5. Execute paper trades, sync `docs/index.html` + `docs/state.json` for remote Web/GitHub Pages viewing,
     and optionally auto-push to Git remote.
"""
import argparse
import json
import shutil
import subprocess
import time
from typing import Dict, List

from src.ai_analyst import AutonomousAIAnalyst
from src.config import BASE_DIR, DEFAULT_CONFIG, STATE_JSON_PATH
from src.paper_trader import PaperTrader
from src.polymarket_client import MarketContract, PolymarketClient
from src.risk_manager import RiskDecision, RiskManager
from src.strategy_engine import StrategyEngine


def sync_web_publish_dir(auto_push: bool = False) -> None:
    """
    Syncs dashboard.html -> docs/index.html and data/portfolio_state.json -> docs/state.json
    so GitHub Pages / Vercel / Cloudflare Pages can host the live dashboard from anywhere.
    """
    docs_dir = BASE_DIR / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dashboard_file = BASE_DIR / "dashboard.html"
    if dashboard_file.exists():
        shutil.copyfile(dashboard_file, docs_dir / "index.html")
    if STATE_JSON_PATH.exists():
        shutil.copyfile(STATE_JSON_PATH, docs_dir / "state.json")

    if auto_push:
        try:
            subprocess.run(["git", "-C", str(BASE_DIR), "add", "docs/index.html", "docs/state.json", "data/portfolio_state.json"], check=False)
            subprocess.run(["git", "-C", str(BASE_DIR), "commit", "-m", "chore(autopilot): autonomous AI state update"], capture_output=True, check=False)
            subprocess.run(["git", "-C", str(BASE_DIR), "push"], capture_output=True, timeout=15, check=False)
        except Exception:
            pass


def run_cycle(limit: int = 35, verbose: bool = True, auto_push: bool = False) -> dict:
    client = PolymarketClient(DEFAULT_CONFIG)
    strategy_engine = StrategyEngine(DEFAULT_CONFIG)
    risk_manager = RiskManager(DEFAULT_CONFIG)
    ai_analyst = AutonomousAIAnalyst(use_agy_cli=True)
    trader = PaperTrader(DEFAULT_CONFIG)

    cycle_num = trader.increment_cycle()

    # Step 1: Fetch active Polymarket contracts
    contracts = client.fetch_active_markets(limit=limit)
    contracts_by_id: Dict[str, MarketContract] = {c.market_id: c for c in contracts}

    # Step 2: Mark-to-market existing positions & run AI Autonomous Exit Manager
    trader.mark_to_market(contracts)
    open_positions = trader.get_open_positions()
    exit_decisions = ai_analyst.evaluate_open_positions(open_positions)
    closed_count = trader.execute_ai_exits(exit_decisions)

    # Step 3: Generate quantitative signals across 3 strategies
    signals = strategy_engine.evaluate_markets(contracts)

    # Step 4: Antigravity CLI (`agy -p`) / AI Semantic Audit + 7-Gate Risk Check
    decisions: List[RiskDecision] = []
    for sig in signals:
        metrics = trader.get_account_metrics()
        open_ids = trader.get_open_market_ids()

        already_open = sig.market_id in open_ids
        ai_audit = None if already_open else ai_analyst.audit_signal(sig, contracts_by_id.get(sig.market_id))

        decision = risk_manager.evaluate_signal(
            signal=sig,
            total_equity_usdc=metrics["total_equity_usdc"],
            available_cash_usdc=metrics["cash_usdc"],
            current_exposure_usdc=metrics["current_exposure_usdc"],
            daily_pnl_usdc=metrics["total_pnl_usdc"],
            open_market_ids=open_ids,
        )

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
    trader.mark_to_market(contracts)
    final_metrics = trader.get_account_metrics()
    ai_summary = ai_analyst.generate_self_tuning_summary(final_metrics, len(decisions))

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
        print(f" POLYMARKET AI AUTOPILOT — CYCLE #{cycle_num} ({ai_summary['ai_mode']})")
        print("=" * 78)
        print(f" AGY CLI Bridge     : {ai_summary.get('agy_cli_path', 'active')}")
        print(f" Data Source        : {state['data_source']}")
        print(f" Markets Scanned    : {state['scanned_markets_count']} active contracts")
        print(f" AI Auto-Exits      : {closed_count} positions closed with profit/stop")
        approved_cnt = sum(1 for d in decisions if d.approved)
        rejected_cnt = sum(1 for d in decisions if not d.approved)
        print(f" New Entry Signals  : {approved_cnt} FILLED | {rejected_cnt} SKIPPED/BLOCKED")
        print("-" * 78)
        print(
            f" Total Equity       : ${m['total_equity_usdc']:,.2f} USDC "
            f"(Cash: ${m['cash_usdc']:,.2f} | Deployed: ${m['current_exposure_usdc']:,.2f})"
        )
        print(
            f" Total PnL          : +${m['total_pnl_usdc']:,.2f} USDC (+{m['return_pct']:.2f}%) "
            f"[Realized: +${m['realized_pnl_usdc']:,.2f} | Unrealized: +${m['unrealized_pnl_usdc']:,.2f}]"
        )
        print(f" AI Regime Note     : {ai_summary['executive_summary']}")
        print("=" * 78)

    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket Autonomous AI Autopilot")
    parser.add_argument("--limit", type=int, default=35, help="Number of active events to scan")
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
