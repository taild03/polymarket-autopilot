"""Risk, persistence and API regressions with no production data or credentials."""
import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.config import TradingConfig
from src.paper_trader import PaperTrader
from src.polymarket_client import PolymarketClient
from src.risk_manager import RiskManager
from src.strategy_engine import StrategyEngine
from server import AutopilotRequestHandler


class OperationalTests(unittest.TestCase):
    def test_daily_drawdown_resets_on_server_day_not_all_time_peak(self):
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(db_path=Path(tmp)/'ledger.db')
            day = datetime(2025, 1, 1, tzinfo=timezone.utc)
            trader.set_reference_time(day)
            trader.get_account_metrics()
            with trader._connect() as conn:
                conn.execute('UPDATE account_state SET cash_usdc=960, realized_pnl_usdc=-40')
            self.assertEqual(trader.get_account_metrics()['daily_pnl_usdc'], -40)
            trader.set_reference_time(day + timedelta(days=1))
            self.assertEqual(trader.get_account_metrics()['daily_pnl_usdc'], 0)
            self.assertEqual(trader.get_account_metrics()['drawdown_from_peak_usdc'], -40)

    def test_strategy_bucket_and_nan_are_rejected(self):
        cfg = TradingConfig()
        signals = StrategyEngine(cfg).evaluate_markets(PolymarketClient(cfg)._get_fallback_contracts())
        sig = next(s for s in signals if s.strategy == 'BOND_CARRY')
        risk = RiskManager(cfg)
        self.assertFalse(risk.evaluate_signal(sig, 1000, 700, 300, 0, set(), strategy_exposure_usdc=300).approved)
        sig.entry_price = float('nan')
        self.assertEqual(risk.evaluate_signal(sig, 1000, 1000, 0, 0, set()).reject_reason, 'INVALID_NUMERIC_INPUT')

    def test_equity_history_is_observed_and_idempotent_per_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            trader = PaperTrader(db_path=Path(tmp)/'ledger.db')
            with patch('src.paper_trader.STATE_JSON_PATH', Path(tmp)/'state.json'):
                one = trader.export_full_state('TEST', [], [], [])
                two = trader.export_full_state('TEST', [], [], [])
                self.assertEqual(len(two['equity_history']), 1)
                trader.increment_cycle()
                three = trader.export_full_state('TEST', [], [], [])
            self.assertEqual(len(three['equity_history']), 2)
            self.assertEqual(one['equity_history'][0]['equity'], 1000)
            self.assertEqual(json.loads((Path(tmp)/'state.json').read_text())['metrics']['total_equity_usdc'], 1000)

    def test_tls_fallback_never_disables_verification(self):
        client = PolymarketClient()
        with patch('src.polymarket_client.urllib.request.urlopen', side_effect=OSError('DNS')), \
             patch.object(client, '_resolve_host_via_doh', return_value='1.1.1.1'), \
             patch('src.polymarket_client.subprocess.run') as run:
            run.return_value.returncode = 1
            run.return_value.stdout = b''
            with self.assertRaises(OSError):
                client._http_get_with_clock_skew_tolerance('https://gamma-api.polymarket.com/events')
            for call in run.call_args_list:
                self.assertNotIn('-k', call.args[0])
                self.assertNotIn('--insecure', call.args[0])

    def test_oauth_callback_uses_state_and_correct_path(self):
        from manage_accounts import valid_oauth_callback
        self.assertTrue(valid_oauth_callback('/auth/callback?state=expected&code=abc', 'expected'))
        self.assertFalse(valid_oauth_callback('/auth/callback?state=wrong&code=abc', 'expected'))
        self.assertFalse(valid_oauth_callback('/favicon.ico?state=expected', 'expected'))
        self.assertFalse(valid_oauth_callback('/auth/callback?code=abc', 'expected'))

    def test_maker_rejects_wrong_tick_and_minimum_shares(self):
        from unittest.mock import Mock
        from src.execution import ExecutionBooks
        cfg = TradingConfig()
        client = PolymarketClient(cfg)
        contracts = client._get_fallback_contracts()
        sig = next(s for s in StrategyEngine(cfg).evaluate_markets(contracts) if s.strategy == 'MAKER_SPREAD')
        sig.liquidity_usd = sig.volume_24h_usd = 100000
        sig.resolution_rules_len = 200
        sig.fair_value = sig.entry_price + .04
        decision = RiskManager(cfg).evaluate_signal(sig, 1000, 1000, 0, 0, set())
        next(c for c in contracts if c.market_id == sig.market_id).yes_token_id = 'token'
        mocked = Mock(config=cfg)
        mocked.fetch_clob_book_top.return_value = {'bid_depth_usd':1000, 'asks':[(.9,1000)], 'best_ask':.9, 'tick_size':.07, 'min_order_size':0}
        self.assertEqual(ExecutionBooks(mocked, contracts).validate(sig, decision).reject_reason, 'INVALID_TICK_SIZE')
        mocked.fetch_clob_book_top.return_value['tick_size'] = .01
        mocked.fetch_clob_book_top.return_value['min_order_size'] = 100000
        self.assertEqual(ExecutionBooks(mocked, contracts).validate(sig, decision).reject_reason, 'BELOW_MINIMUM_SHARES')

    def handler(self, headers=None, body=b'{}'):
        handler = object.__new__(AutopilotRequestHandler)
        handler.headers = headers or {}
        handler.client_address = ('127.0.0.1', 12345)
        handler.path = '/api/scan'
        handler.rfile = io.BytesIO(body)
        handler.result = None
        handler._send_json = lambda payload, status=200: setattr(handler, 'result', (status, payload))
        return handler

    def test_api_denies_foreign_origin_and_missing_token(self):
        with patch.dict('os.environ', {'AUTOPILOT_API_TOKEN': 'test-secret'}):
            handler = self.handler({'Origin':'https://untrusted.example'})
            self.assertFalse(handler._authorized())
            self.assertEqual(handler.result[0], 403)
            handler = self.handler()
            self.assertFalse(handler._authorized())
            self.assertEqual(handler.result[0], 401)
            handler = self.handler({'Authorization':'Bearer test-secret'})
            self.assertTrue(handler._authorized())

    def test_api_rejects_invalid_body_before_running_cycle(self):
        with patch.dict('os.environ', {'AUTOPILOT_API_TOKEN':''}), patch('server.run_cycle') as cycle:
            handler = self.handler({'Content-Type':'application/json', 'Content-Length':'2'}, b'[]')
            handler.do_POST()
            self.assertEqual(handler.result[0], 400)
            cycle.assert_not_called()
            handler = self.handler({'Content-Type':'text/plain'})
            handler.do_POST()
            self.assertEqual(handler.result[0], 415)
            handler = self.handler({'Content-Type':'application/json','Content-Length':'99999'})
            handler.do_POST()
            self.assertEqual(handler.result[0], 400)


if __name__ == '__main__':
    unittest.main()
