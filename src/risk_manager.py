"""
Hard-coded Risk Manager & Position Sizer for Polymarket Autopilot.
Enforces strict capital preservation rules and exact Binary Kelly sizing:
    f* = (p - c) / (1 - c)
before any paper or live order is placed.
"""
import math
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
    """Evaluates trade signals against quantitative risk guardrails and sizes positions via Binary Quarter-Kelly."""

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
        strategy_exposure_usdc: float = 0.0,
        daily_risk_reference_usdc: float = None,
    ) -> RiskDecision:
        checks_passed: List[str] = []

        values = (signal.entry_price, signal.fair_value, total_equity_usdc, available_cash_usdc,
                  current_exposure_usdc, daily_pnl_usdc, strategy_exposure_usdc)
        if not all(math.isfinite(v) for v in values) or total_equity_usdc <= 0 or not 0 < signal.fair_value <= 1:
            return self._reject(signal, "INVALID_NUMERIC_INPUT", checks_passed)

        # 1. Kill-Switch Check: Daily Drawdown against start-of-day / peak equity
        max_loss_usdc = -abs((daily_risk_reference_usdc or total_equity_usdc) * self.config.max_daily_drawdown_pct)
        if daily_pnl_usdc <= max_loss_usdc:
            return self._reject(
                signal,
                f"KILL_SWITCH_ACTIVE: Sụt giảm trong ngày (${daily_pnl_usdc:.2f}) vượt ngưỡng {self.config.max_daily_drawdown_pct * 100:.1f}%",
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
        max_allowed_spread = (
            self.config.maker_max_spread
            if signal.strategy == "MAKER_SPREAD"
            else self.config.max_spread_taker
        )
        if signal.spread > max_allowed_spread:
            return self._reject(
                signal,
                f"WIDE_SPREAD: Chênh lệch Bid-Ask ({signal.spread * 100:.1f}¢) vượt trần cho phép ({max_allowed_spread * 100:.1f}¢)",
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
        remaining_exposure_budget = min(max_total_exposure - current_exposure_usdc,
                                        total_equity_usdc * self.config.max_strategy_bucket_pct - strategy_exposure_usdc)
        if (
            remaining_exposure_budget < self.config.min_order_size_usdc
            or available_cash_usdc < self.config.min_order_size_usdc
        ):
            return self._reject(
                signal,
                f"EXPOSURE_LIMIT: Đã chạm trần phân bổ vốn ({self.config.max_total_exposure_pct * 100:.0f}% tổng tài sản)",
                checks_passed,
            )
        checks_passed.append("EXPOSURE_BUDGET_OK")

        # 7. Exact Binary Kelly Position Sizing: f* = (p - c) / (1 - c)
        p = signal.fair_value
        c = signal.entry_price
        if p <= c or c <= 0.0 or c >= 0.999:
            return self._reject(
                signal,
                f"NEGATIVE_OR_ZERO_EDGE: Xác suất kỳ vọng ({p:.4f}) không lớn hơn giá mua ({c:.4f})",
                checks_passed,
            )

        raw_binary_kelly = (p - c) / (1.0 - c)
        quarter_kelly_pct = raw_binary_kelly * self.config.kelly_fraction
        max_single_trade_usdc = total_equity_usdc * self.config.max_position_pct

        kelly_usdc = total_equity_usdc * quarter_kelly_pct
        target_usdc = min(max_single_trade_usdc, kelly_usdc)
        final_size_usdc = round(
            min(target_usdc, remaining_exposure_budget, available_cash_usdc), 2
        )

        if final_size_usdc < self.config.min_order_size_usdc:
            return self._reject(
                signal,
                f"KELLY_SIZE_TOO_SMALL: Quy mô Kelly (${final_size_usdc:.2f}) nhỏ hơn lệnh tối thiểu (${self.config.min_order_size_usdc:.2f})",
                checks_passed,
            )

        shares_qty = final_size_usdc / signal.entry_price
        checks_passed.append(f"BINARY_KELLY_SIZED_${final_size_usdc:.2f}")

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
    def _reject(
        signal: TradeSignal, reason: str, checks_passed: List[str]
    ) -> RiskDecision:
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
