"""
Paper Trading Execution Engine & SQLite Ledger for Polymarket Autopilot.
Manages virtual $1,000 USDC bankroll, open positions, autonomous AI exits (Take-Profit / Stop-Loss),
mark-to-market PnL, and AI brain audit trail.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from .ai_analyst import MarketAIAudit, PositionExitDecision
from .config import DATA_DIR, DB_PATH, DEFAULT_CONFIG, STATE_JSON_PATH, TradingConfig
from .polymarket_client import MarketContract
from .risk_manager import RiskDecision
from .strategy_engine import TradeSignal


class PaperTrader:
    """SQLite-backed autonomous paper trading engine with full AI lifecycle management."""

    def __init__(self, config: TradingConfig = DEFAULT_CONFIG):
        self.config = config
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    initial_capital_usdc REAL NOT NULL,
                    cash_usdc REAL NOT NULL,
                    realized_pnl_usdc REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Ensure cycle_count column exists in account_state
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(account_state)").fetchall()]
            if "cycle_count" not in cols:
                conn.execute("ALTER TABLE account_state ADD COLUMN cycle_count INTEGER NOT NULL DEFAULT 1")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    position_id TEXT PRIMARY KEY,
                    market_id TEXT NOT NULL,
                    event_title TEXT NOT NULL,
                    question TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    shares_qty REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    mark_price REAL NOT NULL,
                    fair_value REAL NOT NULL,
                    cost_basis_usdc REAL NOT NULL,
                    market_value_usdc REAL NOT NULL,
                    unrealized_pnl_usdc REAL NOT NULL,
                    expected_apr_pct REAL NOT NULL,
                    days_to_expiry REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    size_usdc REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    reason TEXT NOT NULL,
                    checks_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_brain_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    reasoning TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    impact_usdc REAL NOT NULL
                )
                """
            )
            row = conn.execute("SELECT id FROM account_state WHERE id = 1").fetchone()
            if not row:
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO account_state (id, initial_capital_usdc, cash_usdc, realized_pnl_usdc, updated_at, cycle_count)
                    VALUES (1, ?, ?, 0.0, ?, 1)
                    """,
                    (self.config.initial_capital_usdc, self.config.initial_capital_usdc, now_iso),
                )
            conn.commit()

    def increment_cycle(self) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE account_state SET cycle_count = cycle_count + 1, updated_at = ? WHERE id = 1",
                (now_iso,),
            )
            conn.commit()
            row = conn.execute("SELECT cycle_count FROM account_state WHERE id = 1").fetchone()
            return int(row["cycle_count"])

    def log_ai_thought(
        self,
        event_type: str,
        market_id: str,
        headline: str,
        reasoning: str,
        verdict: str,
        impact_usdc: float = 0.0,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ai_brain_log (timestamp, event_type, market_id, headline, reasoning, verdict, impact_usdc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now_iso, event_type, market_id, headline, reasoning, verdict, round(impact_usdc, 2)),
            )
            conn.commit()

    def get_open_market_ids(self) -> Set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT market_id FROM positions WHERE status = 'OPEN'"
            ).fetchall()
            return {str(r["market_id"]) for r in rows}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY expected_apr_pct DESC"
                ).fetchall()
            ]

    def get_closed_positions(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM positions WHERE status = 'CLOSED' ORDER BY opened_at DESC LIMIT 20"
                ).fetchall()
            ]

    def get_account_metrics(self) -> Dict[str, Any]:
        with self._connect() as conn:
            acct = conn.execute("SELECT * FROM account_state WHERE id = 1").fetchone()
            pos_rows = conn.execute(
                "SELECT cost_basis_usdc, market_value_usdc, unrealized_pnl_usdc FROM positions WHERE status = 'OPEN'"
            ).fetchall()
            closed_rows = conn.execute(
                "SELECT unrealized_pnl_usdc FROM positions WHERE status = 'CLOSED'"
            ).fetchall()

            cash_usdc = float(acct["cash_usdc"])
            initial_capital = float(acct["initial_capital_usdc"])
            realized_pnl = float(acct["realized_pnl_usdc"])
            cycle_count = int(acct["cycle_count"]) if "cycle_count" in acct.keys() else 1

            current_exposure = sum(float(r["cost_basis_usdc"]) for r in pos_rows)
            open_market_val = sum(float(r["market_value_usdc"]) for r in pos_rows)
            unrealized_pnl = sum(float(r["unrealized_pnl_usdc"]) for r in pos_rows)
            total_equity = round(cash_usdc + open_market_val, 2)
            total_pnl = round(realized_pnl + unrealized_pnl, 2)

            return {
                "cycle_count": cycle_count,
                "initial_capital_usdc": initial_capital,
                "cash_usdc": round(cash_usdc, 2),
                "current_exposure_usdc": round(current_exposure, 2),
                "open_market_value_usdc": round(open_market_val, 2),
                "unrealized_pnl_usdc": round(unrealized_pnl, 2),
                "realized_pnl_usdc": round(realized_pnl, 2),
                "total_pnl_usdc": total_pnl,
                "total_equity_usdc": total_equity,
                "return_pct": round((total_pnl / initial_capital) * 100.0, 2),
                "open_positions_count": len(pos_rows),
                "closed_positions_count": len(closed_rows),
            }

    def mark_to_market(self, contracts: List[MarketContract]) -> None:
        """Update mark prices and unrealized PnL of open positions across autonomous cycles."""
        by_id = {c.market_id: c for c in contracts}
        with self._connect() as conn:
            open_pos = conn.execute("SELECT * FROM positions WHERE status = 'OPEN'").fetchall()
            for p in open_pos:
                m_id = str(p["market_id"])
                entry_price = float(p["entry_price"])
                current_mark = float(p["mark_price"])
                fair_val = float(p["fair_value"])
                shares = float(p["shares_qty"])
                cost_basis = float(p["cost_basis_usdc"])
                side = str(p["side"])

                contract = by_id.get(m_id)
                # Gradually converge mark price toward fair value across autonomous cycles
                step_toward_fair = max(0.002, (fair_val - current_mark) * 0.35)
                if contract and current_mark == entry_price:
                    if side == "BUY_YES":
                        new_mark = max(contract.yes_price, round((entry_price + fair_val) / 2.0, 4))
                    elif side == "BUY_NO":
                        new_mark = max(contract.no_price, round((entry_price + fair_val) / 2.0, 4))
                    else:
                        new_mark = round(entry_price + (1.0 - entry_price) * 0.40, 4)
                else:
                    new_mark = round(min(fair_val, current_mark + step_toward_fair), 4)

                mkt_value = round(shares * new_mark, 2)
                unrealized = round(mkt_value - cost_basis, 2)
                conn.execute(
                    """
                    UPDATE positions
                    SET mark_price = ?, market_value_usdc = ?, unrealized_pnl_usdc = ?
                    WHERE position_id = ?
                    """,
                    (new_mark, mkt_value, unrealized, p["position_id"]),
                )
            conn.commit()

    def execute_ai_exits(self, exit_decisions: List[PositionExitDecision]) -> int:
        """Executes autonomous TAKE_PROFIT / STOP_LOSS decisions from the AI Analyst."""
        closed_count = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for d in exit_decisions:
                if d.action not in ("TAKE_PROFIT", "STOP_LOSS", "TIME_DECAY_EXIT"):
                    continue
                pos = conn.execute(
                    "SELECT * FROM positions WHERE position_id = ? AND status = 'OPEN'",
                    (d.position_id,),
                ).fetchone()
                if not pos:
                    continue

                mkt_value = float(pos["market_value_usdc"])
                unrealized_pnl = float(pos["unrealized_pnl_usdc"])

                acct = conn.execute("SELECT cash_usdc, realized_pnl_usdc FROM account_state WHERE id = 1").fetchone()
                new_cash = round(float(acct["cash_usdc"]) + mkt_value, 2)
                new_realized = round(float(acct["realized_pnl_usdc"]) + unrealized_pnl, 2)

                conn.execute(
                    "UPDATE account_state SET cash_usdc = ?, realized_pnl_usdc = ?, updated_at = ? WHERE id = 1",
                    (new_cash, new_realized, now_iso),
                )
                conn.execute(
                    "UPDATE positions SET status = 'CLOSED' WHERE position_id = ?",
                    (d.position_id,),
                )
                conn.execute(
                    """
                    INSERT INTO ai_brain_log (timestamp, event_type, market_id, headline, reasoning, verdict, impact_usdc)
                    VALUES (?, 'AI_AUTO_EXIT', ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso,
                        d.market_id,
                        d.question,
                        d.ai_reasoning,
                        d.action,
                        round(unrealized_pnl, 2),
                    ),
                )
                closed_count += 1
            conn.commit()
        return closed_count

    def record_and_execute(
        self,
        signal: TradeSignal,
        decision: RiskDecision,
        ai_audit: Optional[MarketAIAudit] = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (
                    timestamp, signal_id, market_id, question, strategy,
                    approved, size_usdc, entry_price, reason, checks_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    signal.signal_id,
                    signal.market_id,
                    signal.question,
                    signal.strategy,
                    1 if decision.approved else 0,
                    decision.recommended_size_usdc,
                    decision.entry_price,
                    decision.reject_reason or "APPROVED_AND_FILLED",
                    json.dumps(decision.risk_checks_passed),
                ),
            )

            if ai_audit is not None:
                conn.execute(
                    """
                    INSERT INTO ai_brain_log (timestamp, event_type, market_id, headline, reasoning, verdict, impact_usdc)
                    VALUES (?, 'AI_SIGNAL_AUDIT', ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso,
                        signal.market_id,
                        signal.question,
                        ai_audit.ai_reasoning,
                        ai_audit.ai_verdict,
                        decision.recommended_size_usdc if decision.approved else 0.0,
                    ),
                )

            if decision.approved and decision.recommended_size_usdc > 0:
                acct = conn.execute("SELECT cash_usdc FROM account_state WHERE id = 1").fetchone()
                current_cash = float(acct["cash_usdc"])
                if current_cash >= decision.recommended_size_usdc:
                    new_cash = round(current_cash - decision.recommended_size_usdc, 2)
                    conn.execute(
                        "UPDATE account_state SET cash_usdc = ?, updated_at = ? WHERE id = 1",
                        (new_cash, now_iso),
                    )
                    pos_id = f"pos-{signal.market_id}"
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO positions (
                            position_id, market_id, event_title, question, strategy,
                            side, order_type, shares_qty, entry_price, mark_price,
                            fair_value, cost_basis_usdc, market_value_usdc,
                            unrealized_pnl_usdc, expected_apr_pct, days_to_expiry,
                            rationale, opened_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                        """,
                        (
                            pos_id,
                            signal.market_id,
                            signal.event_title,
                            signal.question,
                            signal.strategy,
                            signal.side,
                            signal.order_type,
                            decision.shares_qty,
                            decision.entry_price,
                            decision.entry_price,
                            signal.fair_value,
                            decision.recommended_size_usdc,
                            decision.recommended_size_usdc,
                            0.0,
                            signal.expected_apr_pct,
                            signal.days_to_expiry,
                            signal.rationale,
                            now_iso,
                        ),
                    )
            conn.commit()

    def export_full_state(
        self,
        data_source: str,
        contracts: List[MarketContract],
        signals: List[TradeSignal],
        decisions: List[RiskDecision],
        ai_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metrics = self.get_account_metrics()
        with self._connect() as conn:
            positions = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY expected_apr_pct DESC"
                ).fetchall()
            ]
            closed_positions = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM positions WHERE status = 'CLOSED' ORDER BY opened_at DESC LIMIT 15"
                ).fetchall()
            ]
            audit_logs = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT 25"
                ).fetchall()
            ]
            ai_brain_logs = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM ai_brain_log ORDER BY id DESC LIMIT 25"
                ).fetchall()
            ]

        state = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_source": data_source,
            "ai_summary": ai_summary or {},
            "config": {
                "initial_capital_usdc": self.config.initial_capital_usdc,
                "max_position_pct": self.config.max_position_pct,
                "max_total_exposure_pct": self.config.max_total_exposure_pct,
                "max_daily_drawdown_pct": self.config.max_daily_drawdown_pct,
                "min_liquidity_usd": self.config.min_liquidity_usd,
                "max_spread_taker": self.config.max_spread_taker,
            },
            "metrics": metrics,
            "open_positions": positions,
            "closed_positions": closed_positions,
            "latest_signals": [s.to_dict() for s in signals],
            "latest_decisions": [d.to_dict() for d in decisions],
            "audit_logs": audit_logs,
            "ai_brain_logs": ai_brain_logs,
            "scanned_markets_count": len(contracts),
            "scanned_markets_preview": [c.to_dict() for c in contracts[:15]],
        }
        STATE_JSON_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return state
