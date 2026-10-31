"""
Unit test suite for Polymarket Autopilot (AI Analyst, Strategy Engine, Risk Manager, Kill Switch, Honest Mark-to-Market).
Runs in isolated test mode so live OAuth tokens and production SQLite databases are never touched.
"""
import sys
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.account_router import ArgonAccountRouter
from src.ai_analyst import AutonomousAIAnalyst
from src.config import TradingConfig
from src.paper_trader import PaperTrader
from src.polymarket_client import PolymarketClient
from src.risk_manager import RiskManager
from src.strategy_engine import StrategyEngine


class TestPolymarketAutopilot(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TradingConfig(allow_snapshot_trading=True)
        self.client = PolymarketClient(self.config)
        self.contracts = self.client._get_fallback_contracts()
        self.contracts_by_id = {c.market_id: c for c in self.contracts}
        self.engine = StrategyEngine(self.config)
        self.risk = RiskManager(self.config)
        self.ai = AutonomousAIAnalyst(use_agy_cli=False, isolated_mode=True)

    def test_strategy_engine_detects_all_three_archetypes_with_honest_pricing(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
        strategies_found = {s.strategy for s in signals}
        self.assertIn("BUNDLE_ARB", strategies_found)
        self.assertIn("BOND_CARRY", strategies_found)
        self.assertIn("MAKER_SPREAD", strategies_found)

        # Verify MAKER_SPREAD entry price is snapped strictly to 0.01 tick size
        maker_sigs = [s for s in signals if s.strategy == "MAKER_SPREAD"]
        for ms in maker_sigs:
            self.assertAlmostEqual(round(ms.entry_price * 100), ms.entry_price * 100, places=5)

    def test_ai_analyst_vetoes_vague_oracle_trap_and_approves_clear_rules(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
        trap_sig = next(s for s in signals if s.market_id == "pm-illiquid-meme-trap")
        trap_audit = self.ai.audit_signal(trap_sig, self.contracts_by_id[trap_sig.market_id])
        self.assertEqual(trap_audit.ai_verdict, "VETO_TRAP")
        self.assertLess(trap_audit.oracle_clarity_score, 50.0)

        fed_sig = next(s for s in signals if s.strategy == "BUNDLE_ARB")
        fed_audit = self.ai.audit_signal(fed_sig, self.contracts_by_id[fed_sig.leg_market_ids[0]])
        self.assertIn(fed_audit.ai_verdict, ("STRONG_BUY", "APPROVE"))
        self.assertGreaterEqual(fed_audit.oracle_clarity_score, 80.0)

    def test_ai_analyst_autonomous_take_profit_trigger(self) -> None:
        sample_positions = [
            {
                "position_id": "pos-1",
                "market_id": "pm-btc-above-55k-week",
                "question": "Will Bitcoin close above $55,000 this Friday 23:59 UTC?",
                "entry_price": 0.945,
                "mark_price": 0.971,
                "fair_value": 0.973,
                "shares_qty": 52.91,
                "cost_basis_usdc": 50.0,
                "unrealized_pnl_usdc": 1.38,
            }
        ]
        exits = self.ai.evaluate_open_positions(sample_positions)
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].action, "TAKE_PROFIT")

    def test_self_tuning_summary_honors_server_clock(self) -> None:
        from datetime import datetime, timezone
        server_now = datetime(2026, 10, 21, 7, 35, tzinfo=timezone.utc)
        summary = self.ai.generate_self_tuning_summary({}, 0, now=server_now)
        self.assertEqual(summary["timestamp"], server_now.isoformat())

    def test_risk_manager_blocks_illiquid_trap(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
        trap_sig = next(s for s in signals if s.market_id == "pm-illiquid-meme-trap")
        decision = self.risk.evaluate_signal(
            signal=trap_sig,
            total_equity_usdc=1000.0,
            available_cash_usdc=1000.0,
            current_exposure_usdc=0.0,
            daily_pnl_usdc=0.0,
            open_market_ids=set(),
        )
        self.assertFalse(decision.approved)
        self.assertIn("LOW_LIQUIDITY", decision.reject_reason)

    def test_kill_switch_triggers_on_3pct_drawdown(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
        valid_sig = next(s for s in signals if s.market_id == "pm-btc-above-55k-week")
        decision = self.risk.evaluate_signal(
            signal=valid_sig,
            total_equity_usdc=1000.0,
            available_cash_usdc=900.0,
            current_exposure_usdc=100.0,
            daily_pnl_usdc=-31.50,
            open_market_ids=set(),
        )
        self.assertFalse(decision.approved)
        self.assertIn("KILL_SWITCH_ACTIVE", decision.reject_reason)

    def test_position_size_respects_cap_and_minimum_order(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
        max_cap = self.config.initial_capital_usdc * self.config.max_position_pct
        for sig in signals:
            decision = self.risk.evaluate_signal(
                signal=sig,
                total_equity_usdc=1000.0,
                available_cash_usdc=1000.0,
                current_exposure_usdc=0.0,
                daily_pnl_usdc=0.0,
                open_market_ids=set(),
            )
            if decision.approved:
                self.assertLessEqual(decision.recommended_size_usdc, max_cap)
                self.assertGreaterEqual(decision.recommended_size_usdc, self.config.min_order_size_usdc)

    def test_paper_trader_does_not_fabricate_mark_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            trader = PaperTrader(config=self.config, db_path=db_path)
            signals = self.engine.evaluate_markets(self.contracts)
            valid_sig = next(s for s in signals if s.market_id == "pm-btc-above-55k-week")
            decision = self.risk.evaluate_signal(
                signal=valid_sig,
                total_equity_usdc=1000.0,
                available_cash_usdc=1000.0,
                current_exposure_usdc=0.0,
                daily_pnl_usdc=0.0,
                open_market_ids=set(),
            )
            self.assertTrue(decision.approved)
            trader.record_and_execute(valid_sig, decision)

            # Mark-to-market 5 times with unchanged contract prices -> mark_price must equal live best_bid, never drift up
            for _ in range(5):
                trader.mark_to_market(self.contracts)
            open_pos = trader.get_open_positions()
            self.assertEqual(len(open_pos), 1)
            contract = self.contracts_by_id["pm-btc-above-55k-week"]
            self.assertAlmostEqual(open_pos[0]["mark_price"], contract.best_bid, places=4)

    def test_dual_argon_account_router_detects_quota_and_ignores_dollar_429(self) -> None:
        router = ArgonAccountRouter(isolated_mode=True)
        self.assertTrue(router.is_quota_error("Error 429: RESOURCE_EXHAUSTED quota exceeded"))
        self.assertFalse(router.is_quota_error("200 OK"))
        self.assertFalse(router.is_quota_error("Bitcoin trading volume is $429M today"))
        initial_slot = router.state["active_slot"]
        new_slot = router.handle_quota_exhausted("HTTP 429 Quota Exceeded")
        self.assertNotEqual(initial_slot, new_slot)
        self.assertEqual(router.state["accounts"][initial_slot]["status"], "COOLDOWN")

    def test_maker_reserves_cash_then_fills_only_with_depth(self):
        from src.execution import ExecutionBooks
        from unittest.mock import Mock
        sig = next(s for s in self.engine.evaluate_markets(self.contracts) if s.strategy == 'MAKER_SPREAD')
        sig = replace(sig, liquidity_usd=100000, volume_24h_usd=100000, resolution_rules_len=200, fair_value=sig.entry_price + 0.04)
        decision = self.risk.evaluate_signal(sig, 1000, 1000, 0, 0, set())
        contract = self.contracts_by_id[sig.market_id]
        contract.yes_token_id = 'token'
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.config, Path(tmp)/'ledger.db')
            trader.record_and_execute(sig, decision)
            trader.record_and_execute(sig, decision)
            self.assertEqual(len(trader.get_pending_orders()), 1)
            self.assertEqual(trader.get_open_positions(), [])
            self.assertAlmostEqual(trader.get_account_metrics()['total_equity_usdc'], 1000)
            self.assertIn(sig.market_id, trader.get_open_market_ids())
            client = Mock()
            client.fetch_clob_book_top.return_value = {'asks': [(sig.entry_price, 0.1)]}
            trader.process_lifecycle([contract], ExecutionBooks(client, [contract]))
            self.assertEqual(len(trader.get_pending_orders()), 1)
            client.fetch_clob_book_top.return_value = {'asks': [(sig.entry_price, 10000)]}
            trader.process_lifecycle([contract], ExecutionBooks(client, [contract]))
            self.assertEqual(len(trader.get_open_positions()), 1)
            self.assertEqual(len(trader.get_pending_orders()), 0)

    def test_pending_closed_market_refunds_once(self):
        from src.execution import ExecutionBooks
        sig = next(s for s in self.engine.evaluate_markets(self.contracts) if s.strategy == 'MAKER_SPREAD')
        sig = replace(sig, liquidity_usd=100000, volume_24h_usd=100000, resolution_rules_len=200, fair_value=sig.entry_price + 0.04)
        decision = self.risk.evaluate_signal(sig, 1000, 1000, 0, 0, set())
        contract = self.contracts_by_id[sig.market_id]
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.config, Path(tmp)/'ledger.db')
            trader.record_and_execute(sig, decision)
            contract.closed = True
            for _ in range(2):
                trader.process_lifecycle([contract], ExecutionBooks(self.client, [contract]))
            self.assertEqual(trader.get_account_metrics()['cash_usdc'], 1000)
            self.assertFalse(trader.get_open_market_ids())

    def test_settlement_requires_confirmed_result_and_is_idempotent(self):
        from src.execution import ExecutionBooks
        sig = next(s for s in self.engine.evaluate_markets(self.contracts) if s.market_id == 'pm-btc-above-55k-week')
        decision = self.risk.evaluate_signal(sig, 1000, 1000, 0, 0, set())
        contract = self.contracts_by_id[sig.market_id]
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.config, Path(tmp)/'ledger.db')
            trader.record_and_execute(sig, decision)
            contract.closed = True
            books = ExecutionBooks(self.client, [contract])
            trader.process_lifecycle([contract], books)
            self.assertEqual(len(trader.get_open_positions()), 1)
            contract.settlement_yes = 0.0
            trader.process_lifecycle([contract], books)
            metrics = trader.get_account_metrics()
            trader.process_lifecycle([contract], books)
            self.assertEqual(metrics, trader.get_account_metrics())
            self.assertAlmostEqual(metrics['realized_pnl_usdc'], -decision.recommended_size_usdc)

    def test_orderbook_sorting_empty_and_invalid_levels(self):
        book = self.client.normalize_book({'bids': [{'price': '.2', 'size': '10'}, {'price': '.4', 'size': '5'}], 'asks': [{'price': '.8', 'size': '10'}, {'price': '.6', 'size': '5'}]})
        self.assertEqual(book['best_bid'], .4)
        self.assertEqual(book['best_ask'], .6)
        self.assertEqual(self.client.normalize_book({})['best_bid'], 0)
        with self.assertRaises(ValueError):
            self.client.normalize_book({'bids': [{'price': 'nan', 'size': '1'}]})

    def test_execution_rejects_missing_or_insufficient_books(self):
        from src.execution import ExecutionBooks
        from unittest.mock import Mock
        sig = next(s for s in self.engine.evaluate_markets(self.contracts) if s.market_id == 'pm-btc-above-55k-week')
        decision = self.risk.evaluate_signal(sig, 1000, 1000, 0, 0, set())
        client = Mock(config=self.config)
        client.fetch_clob_book_top.return_value = None
        self.contracts_by_id[sig.market_id].yes_token_id = 'token'
        self.assertFalse(ExecutionBooks(client, self.contracts).validate(sig, decision).approved)
        client.fetch_clob_book_top.return_value = {'bid_depth_usd': 1000, 'asks': [(sig.entry_price, 0.1)]}
        self.assertEqual(ExecutionBooks(client, self.contracts).validate(sig, decision).reject_reason, 'INSUFFICIENT_ASK_DEPTH')

    def test_bundle_tracks_exact_legs(self):
        sig = next(s for s in self.engine.evaluate_markets(self.contracts) if s.strategy == 'BUNDLE_ARB')
        decision = self.risk.evaluate_signal(sig, 1000, 1000, 0, 0, set())
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.config, Path(tmp)/'ledger.db')
            trader.record_and_execute(sig, decision)
            trader.mark_to_market(self.contracts)
            mark = trader.get_open_positions()[0]['mark_price']
            self.assertAlmostEqual(mark, sum(self.contracts_by_id[mid].best_bid for mid in sig.leg_market_ids))
            trader.mark_to_market(self.contracts[:1])
            self.assertEqual(trader.get_open_positions()[0]['mark_price'], mark)

    def test_parser_retains_closed_resolution_and_negative_expiry(self):
        market = {'id':'closed', 'closed': True, 'active':False, 'umaResolutionStatus':'proposed', 'outcomes':'["Yes","No"]', 'outcomePrices':'["1","0"]', 'endDate':'2000-01-01T00:00:00Z'}
        event = {'markets':[market]}
        self.assertEqual(self.client._parse_events_payload([event]), [])
        parsed = self.client._parse_events_payload([event], include_closed=True)[0]
        self.assertIsNone(parsed.settlement_yes)
        self.assertLess(parsed.days_to_expiry, 0)
        market['umaResolutionStatus'] = 'resolved'
        self.assertEqual(self.client._parse_events_payload([event], include_closed=True)[0].settlement_yes, 1)


if __name__ == "__main__":
    unittest.main()
