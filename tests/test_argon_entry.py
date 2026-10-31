"""
Isolated tests for the mandatory Argon entry-review gate.

No real `agy` CLI, credentials, network, production DB or ~/.gemini are touched: the CLI is
replaced by an injected fake runner and the router runs in isolated mode. These tests assert
the honest behaviours required of the gate: genuine approve/reject/insufficient/unavailable,
strict schema/NaN validation, correct NO/bundle side context, two-account quota retry,
blocked backup/both-cooldown, no reuse of a stale approval, legacy pending refund, pending
fill eligibility vs expiry, and fresh-book re-validation after slow inference.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.account_router import ArgonAccountRouter
from src.argon_entry import ArgonEntryGate, EntryReview, validate_review_payload, STATUS_APPROVE
from src.config import TradingConfig
from src.execution import ExecutionBooks
from src.paper_trader import PaperTrader
from src.polymarket_client import MarketContract
from src.risk_manager import RiskManager
from src.strategy_engine import TradeSignal


def make_contract(market_id="m1", best_bid=0.60, best_ask=0.63, closed=False, days=7.0):
    return MarketContract(
        market_id=market_id,
        event_id="evt-1",
        event_title="Test Event",
        question=f"Will {market_id} resolve YES?",
        slug=market_id,
        yes_price=round((best_bid + best_ask) / 2, 4),
        no_price=round(1.0 - (best_bid + best_ask) / 2, 4),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=round(best_ask - best_bid, 4),
        liquidity_usd=120000.0,
        volume_24h_usd=50000.0,
        end_date_iso="2026-12-01T00:00:00Z",
        days_to_expiry=days,
        resolution_rules="Resolves YES per official source " + "x" * 120,
        neg_risk=False,
        outcomes_count_in_event=1,
        yes_token_id="ytok-" + market_id,
        no_token_id="ntok-" + market_id,
    )


def make_signal(side="BUY_YES", market_id="m1", entry_price=0.63, fair_value=0.98, leg_ids=None):
    return TradeSignal(
        signal_id=f"sig-{market_id}",
        market_id=market_id,
        event_title="Test Event",
        question=f"Will {market_id} resolve YES?",
        strategy="BOND_CARRY",
        side=side,
        order_type="LIMIT_IOC",
        entry_price=entry_price,
        fair_value=fair_value,
        edge_bps=150.0,
        expected_apr_pct=30.0,
        confidence_score=0.88,
        liquidity_usd=120000.0,
        volume_24h_usd=50000.0,
        spread=0.03,
        days_to_expiry=7.0,
        resolution_rules_len=200,
        rationale="test",
        leg_market_ids=leg_ids or [],
    )


def response(verdict="APPROVE", prob=0.9, research=True, reasoning="Có căn cứ độc lập.", risks=None):
    return json.dumps({
        "verdict": verdict,
        "chosen_side_prob": prob,
        "has_independent_research": research,
        "clarity_score": 90,
        "reasoning": reasoning,
        "risks": risks if risks is not None else ["rủi ro phân xử"],
    })


class FakeRunner:
    """Pops queued (returncode, stdout, stderr) tuples; records argv seen per call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv, cwd, timeout):
        self.calls.append(argv)
        if not self.responses:
            raise AssertionError("FakeRunner exhausted: unexpected extra CLI call")
        return self.responses.pop(0)


def make_router(configured=("account_1", "account_2")):
    router = ArgonAccountRouter(isolated_mode=True)
    for slot in ("account_1", "account_2"):
        router.state["accounts"][slot]["configured"] = slot in configured
        router.state["accounts"][slot]["status"] = "ACTIVE" if slot == "account_1" else "STANDBY"
        router.state["accounts"][slot]["cooldown_until_iso"] = ""
    return router


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def mono(self):
        return self.t


class EntryGateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = TradingConfig(require_argon_entry_review=True)

    def gate(self, responses, router=None, clock=None):
        router = router or make_router()
        self.fake = FakeRunner(responses)
        return ArgonEntryGate(
            self.cfg, router, binary="/fake/agy", runner=self.fake,
            monotonic=(clock.mono if clock else None),
        )

    # -- schema validation ------------------------------------------------
    def test_valid_payload_parses(self):
        v = validate_review_payload(response(verdict="REJECT", prob=None))
        self.assertEqual(v["verdict"], "REJECT")

    def test_invalid_verdict_and_nan_and_missing_raise(self):
        with self.assertRaises(ValueError):
            validate_review_payload(json.dumps({"verdict": "MAYBE", "chosen_side_prob": None,
                                                "has_independent_research": False, "reasoning": "x", "risks": []}))
        # NaN is not finite -> rejected (Python json parses the bare token NaN).
        with self.assertRaises(ValueError):
            validate_review_payload('{"verdict":"APPROVE","chosen_side_prob":NaN,'
                                    '"has_independent_research":true,"reasoning":"x","risks":[]}')
        with self.assertRaises(ValueError):
            validate_review_payload('{"verdict":"APPROVE"}')
        with self.assertRaises(ValueError):
            validate_review_payload('not json at all')

    # -- genuine verdict handling ----------------------------------------
    def test_approve_opens_and_counts_success(self):
        router = make_router()
        gate = self.gate([(0, response(verdict="APPROVE", prob=0.92), "")], router=router)
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, STATUS_APPROVE)
        self.assertTrue(review.approved)
        self.assertEqual(review.account_slot, "account_1")
        self.assertEqual(review.model, "gemini-4-argon-high")
        self.assertEqual(review.chosen_side_prob, 0.92)
        self.assertEqual(router.state["accounts"]["account_1"]["calls_succeeded"], 1)

    def test_reject_blocks(self):
        gate = self.gate([(0, response(verdict="REJECT", prob=None, reasoning="Lợi thế âm."), "")])
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, "REJECT")
        self.assertFalse(review.approved)

    def test_insufficient_data_blocks(self):
        gate = self.gate([(0, response(verdict="INSUFFICIENT_DATA", prob=None, research=False,
                                        reasoning="Cần tin tức độc lập."), "")])
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, "INSUFFICIENT_DATA")
        self.assertFalse(review.approved)

    def test_approve_without_independent_research_is_downgraded(self):
        # An APPROVE that admits no independent research is NOT evidence of an edge: downgrade.
        gate = self.gate([(0, response(verdict="APPROVE", prob=0.9, research=False), "")])
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, "INSUFFICIENT_DATA")
        self.assertIn("DOWNGRADED", review.reject_reason)

    # -- unavailable / block paths ---------------------------------------
    def test_invalid_json_is_unavailable(self):
        gate = self.gate([(0, "garbage not json", "")])
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, "UNAVAILABLE")
        self.assertEqual(review.reject_reason, "INVALID_RESPONSE")

    def test_nonzero_exit_is_unavailable(self):
        gate = self.gate([(1, "", "boom")])
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, "UNAVAILABLE")
        self.assertEqual(review.reject_reason, "ARGON_CALL_FAILED")

    def test_missing_binary_blocks(self):
        router = make_router()
        gate = ArgonEntryGate(self.cfg, router, binary="", runner=FakeRunner([]))
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.reject_reason, "ARGON_CLI_NOT_FOUND")

    def test_no_configured_account_blocks(self):
        router = make_router(configured=())
        gate = self.gate([], router=router)
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.reject_reason, "NO_CONFIGURED_ACCOUNT")

    def test_missing_leg_context_blocks(self):
        gate = self.gate([])
        review = gate.review_order(make_signal(), {})  # contract absent
        self.assertEqual(review.reject_reason, "MISSING_LEG_CONTEXT")

    def test_budget_exhaustion_blocks_deferred_signals(self):
        cfg = TradingConfig(require_argon_entry_review=True, argon_max_calls_per_cycle=1)
        router = make_router()
        fake = FakeRunner([(0, response(), ""), (0, response(), "")])
        gate = ArgonEntryGate(cfg, router, binary="/fake/agy", runner=fake)
        first = gate.review_order(make_signal(market_id="m1"), {"m1": make_contract("m1")})
        self.assertEqual(first.status, STATUS_APPROVE)
        second = gate.review_order(make_signal(market_id="m2"), {"m2": make_contract("m2")})
        self.assertEqual(second.reject_reason, "CYCLE_BUDGET_EXHAUSTED")

    # -- side / bundle context -------------------------------------------
    def test_no_side_context_is_labelled_and_priced(self):
        gate = self.gate([])
        sig = make_signal(side="BUY_NO", entry_price=0.37)
        contract = make_contract(best_bid=0.60, best_ask=0.63)
        ctx = gate._build_context(sig, [contract])
        leg = ctx["legs"][0]
        self.assertEqual(leg["side_bought"], "NO")
        self.assertAlmostEqual(leg["chosen_side_entry_price"], round(1 - 0.60, 4))
        self.assertEqual(ctx["independent_research_available"], False)

    def test_bundle_context_covers_all_legs_as_yes(self):
        gate = self.gate([])
        legs = [make_contract("a"), make_contract("b"), make_contract("c")]
        sig = make_signal(side="BUY_BUNDLE", market_id="bundle-evt", leg_ids=["a", "b", "c"])
        ctx = gate._build_context(sig, legs)
        self.assertEqual(len(ctx["legs"]), 3)
        self.assertTrue(all(l["side_bought"] == "YES" for l in ctx["legs"]))

    # -- two-account routing ---------------------------------------------
    def test_quota_failover_retries_on_alternate_account(self):
        router = make_router()
        gate = self.gate([
            (0, "Error 429: RESOURCE_EXHAUSTED quota exceeded", ""),
            (0, response(verdict="APPROVE", prob=0.9), ""),
        ], router=router)
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, STATUS_APPROVE)
        self.assertEqual(review.account_slot, "account_2")
        self.assertEqual(review.attempts, 2)
        self.assertEqual(router.state["accounts"]["account_1"]["status"], "COOLDOWN")
        self.assertEqual(router.state["accounts"]["account_2"]["calls_succeeded"], 1)

    def test_quota_with_no_configured_backup_blocks(self):
        router = make_router(configured=("account_1",))
        gate = self.gate([(0, "429 RESOURCE_EXHAUSTED", "")], router=router)
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, "UNAVAILABLE")
        self.assertEqual(review.reject_reason, "ALL_ACCOUNTS_UNAVAILABLE")

    def test_quota_with_backup_in_cooldown_blocks(self):
        router = make_router()
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        router.state["accounts"]["account_2"]["cooldown_until_iso"] = future
        gate = self.gate([(0, "rate limit exceeded", "")], router=router)
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.reject_reason, "ALL_ACCOUNTS_UNAVAILABLE")

    def test_only_one_retry(self):
        # Two consecutive quota errors must not loop: exactly one retry, then block.
        router = make_router()
        gate = self.gate([
            (0, "429 RESOURCE_EXHAUSTED", ""),
            (0, "429 RESOURCE_EXHAUSTED", ""),
        ], router=router)
        review = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertEqual(review.status, "UNAVAILABLE")
        self.assertEqual(len(self.fake.calls), 2)

    # -- cache: old caches cannot authorize new trades --------------------
    def test_same_order_within_ttl_is_cache_hit(self):
        gate = self.gate([(0, response(), "")])
        c = {"m1": make_contract()}
        first = gate.review_order(make_signal(), c)
        second = gate.review_order(make_signal(), c)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(len(self.fake.calls), 1)

    def test_price_change_is_not_served_from_cache(self):
        gate = self.gate([(0, response(), ""), (0, response(verdict="REJECT", prob=None), "")])
        gate.review_order(make_signal(entry_price=0.63), {"m1": make_contract()})
        second = gate.review_order(make_signal(entry_price=0.70), {"m1": make_contract()})
        self.assertEqual(second.status, "REJECT")
        self.assertEqual(len(self.fake.calls), 2)

    def test_expired_cache_triggers_fresh_call(self):
        clock = FakeClock()
        gate = self.gate([(0, response(), ""), (0, response(verdict="REJECT", prob=None), "")], clock=clock)
        gate.review_order(make_signal(), {"m1": make_contract()})
        clock.t += self.cfg.argon_cache_ttl_sec + 1.0
        second = gate.review_order(make_signal(), {"m1": make_contract()})
        self.assertFalse(second.cache_hit)
        self.assertEqual(len(self.fake.calls), 2)


class PendingLifecycleTests(unittest.TestCase):
    """Legacy refund, pending fill eligibility/expiry, and fresh-book re-validation."""

    def setUp(self):
        self.cfg = TradingConfig(require_argon_entry_review=True)
        self.risk = RiskManager(self.cfg)

    def _maker_signal_and_decision(self):
        sig = TradeSignal(
            signal_id="sig-maker", market_id="m1", event_title="E", question="Q?",
            strategy="MAKER_SPREAD", side="BUY_YES", order_type="LIMIT_MAKER",
            entry_price=0.60, fair_value=0.66, edge_bps=200, expected_apr_pct=40,
            confidence_score=0.8, liquidity_usd=120000, volume_24h_usd=120000,
            spread=0.04, days_to_expiry=7.0, resolution_rules_len=200, rationale="r",
        )
        decision = self.risk.evaluate_signal(sig, 1000, 1000, 0, 0, set())
        self.assertTrue(decision.approved)
        return sig, decision

    def _review(self, when):
        return EntryReview(
            status="APPROVE", provider="argon_cli", model="gemini-4-argon-high",
            account_slot="account_1", account_label="Argon #1", timestamp=when.isoformat(),
            chosen_side="BUY_YES", reasoning="ok", risks=[], chosen_side_prob=0.66,
            has_independent_research=True,
        )

    def test_direct_execution_without_review_cannot_reserve_cash(self):
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.cfg, Path(tmp) / "ledger.db")
            sig, decision = self._maker_signal_and_decision()
            trader.record_and_execute(sig, decision)
            self.assertEqual(trader.get_pending_orders(), [])
            self.assertEqual(trader.get_account_metrics()["cash_usdc"], 1000)

    def test_legacy_unreviewed_pending_is_refunded(self):
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.cfg, Path(tmp) / "ledger.db")
            sig, decision = self._maker_signal_and_decision()
            # Seed a pre-gate database, then reopen under the required policy.
            trader = PaperTrader(TradingConfig(require_argon_entry_review=False), Path(tmp) / "ledger.db")
            trader.record_and_execute(sig, decision)
            self.assertEqual(len(trader.get_pending_orders()), 1)
            self.assertLess(trader.get_account_metrics()["cash_usdc"], 1000)
            trader = PaperTrader(self.cfg, Path(tmp) / "ledger.db")
            refunded = trader.migrate_legacy_pending_orders()
            self.assertEqual(refunded, 1)
            self.assertEqual(trader.get_pending_orders(), [])
            self.assertEqual(trader.get_account_metrics()["cash_usdc"], 1000)

    def test_approved_non_expired_pending_fills(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.cfg, Path(tmp) / "ledger.db")
            trader.set_reference_time(now)
            sig, decision = self._maker_signal_and_decision()
            review = self._review(now)
            expires = (now + timedelta(seconds=self.cfg.argon_approval_ttl_sec)).isoformat()
            trader.record_and_execute(sig, decision, entry_review=review, approval_expires_at=expires)
            self.assertEqual(len(trader.get_pending_orders()), 1)

            contract = make_contract("m1", best_bid=0.60, best_ask=0.63)
            client = Mock(config=self.cfg)
            client.fetch_clob_book_top.return_value = {"asks": [(0.60, 100000)]}
            books = ExecutionBooks(client, [contract])

            # Not expired -> eligible, fills to OPEN on available depth.
            trader.process_lifecycle([contract], books)
            self.assertEqual(len(trader.get_open_positions()), 1)
            self.assertEqual(len(trader.get_pending_orders()), 0)

    def test_expired_approval_cannot_fill_and_is_refunded(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(self.cfg, Path(tmp) / "ledger.db")
            trader.set_reference_time(now)
            sig, decision = self._maker_signal_and_decision()
            review = self._review(now)
            expires = (now + timedelta(seconds=1)).isoformat()
            trader.record_and_execute(sig, decision, entry_review=review, approval_expires_at=expires)

            contract = make_contract("m1", best_bid=0.60, best_ask=0.63)
            client = Mock(config=self.cfg)
            client.fetch_clob_book_top.return_value = {"asks": [(0.60, 100000)]}
            books = ExecutionBooks(client, [contract])

            trader.set_reference_time(now + timedelta(seconds=2))
            trader.process_lifecycle([contract], books)
            self.assertEqual(len(trader.get_open_positions()), 0)  # refused to fill unaudited
            refunded = trader.cancel_expired_pending_reviews()
            self.assertEqual(refunded, 1)
            self.assertEqual(trader.get_account_metrics()["cash_usdc"], 1000)

    def test_fresh_book_after_inference_blocks_stale_authorization(self):
        # Approval is granted, but a re-fetched (fresh) book lacks ask depth -> execution blocked.
        sig = TradeSignal(
            signal_id="sig", market_id="m1", event_title="E", question="Q?",
            strategy="BOND_CARRY", side="BUY_YES", order_type="LIMIT_IOC",
            entry_price=0.63, fair_value=0.98, edge_bps=150, expected_apr_pct=30,
            confidence_score=0.88, liquidity_usd=120000, volume_24h_usd=50000,
            spread=0.03, days_to_expiry=7.0, resolution_rules_len=200, rationale="r",
        )
        decision = self.risk.evaluate_signal(sig, 1000, 1000, 0, 0, set())
        self.assertTrue(decision.approved)
        contract = make_contract("m1")
        client = Mock(config=self.cfg)
        # Fresh book after slow inference: the asks evaporated.
        client.fetch_clob_book_top.return_value = {"bid_depth_usd": 100000, "asks": []}
        fresh = ExecutionBooks(client, [contract])
        revalidated = fresh.validate(sig, decision)
        self.assertFalse(revalidated.approved)


if __name__ == "__main__":
    unittest.main()
