"""
Hard-coded Risk Manager & Position Sizer for Polymarket Autopilot.
Enforces strict capital preservation rules before any paper or live order is placed.
"""
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Set

from .config import DEFAULT_CONFIG, TradingConfig
from .strategy_engine import TradeSignal


@dataclass
class RiskDecision:
    signal_id: str
    market_id: str
    question: str
    strategy: str
    approved: bool
    recommended_size_usdc: float
    shares_qty: float
    entry_price: float
    reject_reason: str
    risk_checks_passed: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RiskManager:
    """Evaluates trade signals against quantitative risk guardrails and sizes positions via Quarter-Kelly."""

    def __init__(self, config: TradingConfig = DEFAULT_CONFIG):
        self.config = config

    def evaluate_signal(
        self,
        signal: TradeSignal,
        total_equity_usdc: float,
        available_cash_usdc: float,
        current_exposure_usdc: float,
        daily_pnl_usdc: float,
        open_market_ids: Set[str],
    ) -> RiskDecision:
        checks_passed: List[str] = []

        # 1. Kill-Switch Check: Daily Drawdown
        max_loss_usdc = -abs(total_equity_usdc * self.config.max_daily_drawdown_pct)
        if daily_pnl_usdc <= max_loss_usdc:
            return self._reject(
                signal,
                f"KILL_SWITCH_ACTIVE: Lỗ trong ngày (${daily_pnl_usdc:.2f}) vượt ngưỡng {self.config.max_daily_drawdown_pct * 100:.1f}%",
                checks_passed,
            )
        checks_passed.append("KILL_SWITCH_OK")

        # 2. Duplicate Position Check
        if signal.market_id in open_market_ids:
            return self._reject(
                signal,
                "DUPLICATE_POSITION: Đã có vị thế đang mở trên thị trường này",
                checks_passed,
            )
        checks_passed.append("NO_DUPLICATE")

        # 3. Market Liquidity & Volume Check
        if signal.liquidity_usd < self.config.min_liquidity_usd:
            return self._reject(
                signal,
                f"LOW_LIQUIDITY: Thanh khoản ${signal.liquidity_usd:,.0f} < mức tối thiểu ${self.config.min_liquidity_usd:,.0f}",
                checks_passed,
            )
        if signal.volume_24h_usd < self.config.min_volume_24h_usd:
            return self._reject(
                signal,
                f"LOW_VOLUME: Volume 24h ${signal.volume_24h_usd:,.0f} < mức tối thiểu ${self.config.min_volume_24h_usd:,.0f}",
                checks_passed,
            )
        checks_passed.append("LIQUIDITY_OK")

        # 4. Spread / Slippage Check
        if signal.spread > self.config.max_spread_taker:
            return self._reject(
                signal,
                f"WIDE_SPREAD: Chênh lệch Bid-Ask ({signal.spread * 100:.1f}¢) vượt trần cho phép ({self.config.max_spread_taker * 100:.1f}¢)",
                checks_passed,
            )
        checks_passed.append("SPREAD_OK")

        # 5. Resolution Rules Clarity Check (Oracle Trap Filter)
        if signal.resolution_rules_len < self.config.min_resolution_text_len:
            return self._reject(
                signal,
                f"ORACLE_TRAP_RISK: Luật phân xử quá ngắn/mơ hồ ({signal.resolution_rules_len} ký tự)",
                checks_passed,
            )
        checks_passed.append("ORACLE_RULES_CLEAR")

        # 6. Portfolio Exposure Ceiling Check
        max_total_exposure = total_equity_usdc * self.config.max_total_exposure_pct
        remaining_exposure_budget = max_total_exposure - current_exposure_usdc
        if remaining_exposure_budget < 10.0 or available_cash_usdc < 10.0:
            return self._reject(
                signal,
                f"EXPOSURE_LIMIT: Đã chạm trần phân bổ vốn ({self.config.max_total_exposure_pct * 100:.0f}% tổng tài sản)",
                checks_passed,
            )
        checks_passed.append("EXPOSURE_BUDGET_OK")

        # 7. Quarter-Kelly Position Sizing Capped at max_position_pct (5%)
        max_single_trade_usdc = total_equity_usdc * self.config.max_position_pct
        edge_decimal = max(0.005, signal.edge_bps / 10000.0)
        odds_b = max(0.03, (1.0 - signal.entry_price) / max(0.05, signal.entry_price))
        raw_kelly_pct = edge_decimal / odds_b
        fractional_kelly_usdc = total_equity_usdc * min(0.20, raw_kelly_pct * self.config.kelly_fraction)

        # Bound position size between $15 min and $50 max (5% of $1,000)
        target_usdc = max(15.0, min(max_single_trade_usdc, fractional_kelly_usdc))
        final_size_usdc = round(min(target_usdc, remaining_exposure_budget, available_cash_usdc), 2)
        shares_qty = round(final_size_usdc / signal.entry_price, 2)

        checks_passed.append(f"KELLY_SIZED_${final_size_usdc:.2f}")

        return RiskDecision(
            signal_id=signal.signal_id,
            market_id=signal.market_id,
            question=signal.question,
            strategy=signal.strategy,
            approved=True,
            recommended_size_usdc=final_size_usdc,
            shares_qty=shares_qty,
            entry_price=signal.entry_price,
            reject_reason="",
            risk_checks_passed=checks_passed,
        )

    @staticmethod
    def _reject(signal: TradeSignal, reason: str, checks_passed: List[str]) -> RiskDecision:
        return RiskDecision(
            signal_id=signal.signal_id,
            market_id=signal.market_id,
            question=signal.question,
            strategy=signal.strategy,
            approved=False,
            recommended_size_usdc=0.0,
            shares_qty=0.0,
            entry_price=signal.entry_price,
            reject_reason=reason,
            risk_checks_passed=checks_passed,
        )
