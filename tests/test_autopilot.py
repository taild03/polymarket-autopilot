"""
Unit test suite for Polymarket Autopilot (AI Analyst, Strategy Engine, Risk Manager, Kill Switch).
"""
import unittest
from src.account_router import ArgonAccountRouter
from src.ai_analyst import AutonomousAIAnalyst
from src.config import DEFAULT_CONFIG
from src.polymarket_client import PolymarketClient
from src.risk_manager import RiskManager
from src.strategy_engine import StrategyEngine


class TestPolymarketAutopilot(unittest.TestCase):
    def setUp(self) -> None:
        self.client = PolymarketClient(DEFAULT_CONFIG)
        self.contracts = self.client._get_fallback_contracts()
        self.contracts_by_id = {c.market_id: c for c in self.contracts}
        self.engine = StrategyEngine(DEFAULT_CONFIG)
        self.risk = RiskManager(DEFAULT_CONFIG)
        self.ai = AutonomousAIAnalyst()

    def test_strategy_engine_detects_all_three_archetypes(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
        strategies_found = {s.strategy for s in signals}
        self.assertIn("BUNDLE_ARB", strategies_found)
        self.assertIn("BOND_CARRY", strategies_found)
        self.assertIn("MAKER_SPREAD", strategies_found)

    def test_ai_analyst_vetoes_vague_oracle_trap_and_approves_clear_rules(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
        trap_sig = next(s for s in signals if s.market_id == "pm-illiquid-meme-trap")
        trap_audit = self.ai.audit_signal(trap_sig, self.contracts_by_id[trap_sig.market_id])
        self.assertEqual(trap_audit.ai_verdict, "VETO_TRAP")
        self.assertLess(trap_audit.oracle_clarity_score, 50.0)

        fed_sig = next(s for s in signals if s.market_id == "pm-fed-nov-hold")
        fed_audit = self.ai.audit_signal(fed_sig, self.contracts_by_id[fed_sig.market_id])
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

    def test_position_size_never_exceeds_5pct_cap(self) -> None:
        signals = self.engine.evaluate_markets(self.contracts)
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
                self.assertLessEqual(decision.recommended_size_usdc, 50.0)
                self.assertGreaterEqual(decision.recommended_size_usdc, 15.0)


    def test_dual_argon_account_router_detects_quota_and_switches(self) -> None:
        router = ArgonAccountRouter()
        self.assertTrue(router.is_quota_error("Error 429: RESOURCE_EXHAUSTED quota exceeded"))
        self.assertFalse(router.is_quota_error("200 OK"))
        initial_slot = router.state["active_slot"]
        new_slot = router.handle_quota_exhausted("429 Quota Exceeded")
        self.assertNotEqual(initial_slot, new_slot)
        # Switch back to account_1 after test
        router.activate_slot("account_1", reason="Reset after unit test")


if __name__ == "__main__":
    unittest.main()
