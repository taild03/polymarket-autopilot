"""
Strategy Engine for Polymarket Autopilot.
Implements three quantitative strategies without fake mid-price or +2.8c assumptions:
1. BUNDLE_ARB: Multi-outcome mutually exclusive Dutch-book arbitrage using executable ASK prices + fee buffer.
2. BOND_CARRY: High-probability near-resolution yield capture (94c - 99c) with UMA tail-risk haircut.
3. MAKER_SPREAD: Passive limit order spread capture aligned to valid 1-cent tick sizes with adverse-selection haircut.
"""
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List

from .config import DEFAULT_CONFIG, TradingConfig
from .polymarket_client import MarketContract


@dataclass
class TradeSignal:
    signal_id: str
    market_id: str
    event_title: str
    question: str
    strategy: str               # BUNDLE_ARB | BOND_CARRY | MAKER_SPREAD
    side: str                   # BUY_YES | BUY_NO | BUY_BUNDLE
    order_type: str             # LIMIT_MAKER | LIMIT_IOC
    entry_price: float          # Executable entry price ($0.01 - $0.99)
    fair_value: float           # Calibrated settlement expectation
    edge_bps: float             # Net expected edge in basis points after fees/haircut
    expected_apr_pct: float     # Annualized return percentage (non-compounded simple APR)
    confidence_score: float     # 0.0 to 1.0
    liquidity_usd: float
    volume_24h_usd: float
    spread: float
    days_to_expiry: float
    resolution_rules_len: int
    rationale: str

    leg_market_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyEngine:
    """Scans normalized Polymarket contracts and generates quantitative trade signals."""

    def __init__(self, config: TradingConfig = DEFAULT_CONFIG):
        self.config = config

    def evaluate_markets(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []

        # 1. Multi-Outcome Event Bundle Arbitrage (strictly on executable best_ask)
        signals.extend(self._scan_bundle_arbitrage(contracts))

        # 2. High-Probability Near-Resolution Carry (Bond Carry)
        signals.extend(self._scan_bond_carry(contracts))

        # 3. Orderbook Maker Spread Capture (tick-aligned)
        signals.extend(self._scan_maker_spread(contracts))

        signals.sort(key=lambda s: (s.edge_bps, s.expected_apr_pct), reverse=True)
        return signals

    def _scan_bundle_arbitrage(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        by_event: Dict[str, List[MarketContract]] = defaultdict(list)
        for c in contracts:
            if c.neg_risk and c.outcomes_count_in_event >= 2 and not c.closed:
                by_event[c.event_id].append(c)

        signals: List[TradeSignal] = []
        for event_id, group in by_event.items():
            if len(group) < 2 or len(group) != group[0].outcomes_count_in_event:
                continue

            # Strictly use executable best_ask (never mid price) plus per-leg fee/slippage buffer
            if any(m.best_ask <= 0.001 or m.best_ask >= 0.999 for m in group):
                continue

            sum_yes_ask = sum(m.best_ask for m in group)
            fee_buffer = len(group) * (self.config.taker_fee_bps / 10000.0)
            executable_bundle_cost = round(sum_yes_ask + fee_buffer, 4)

            if 0.80 < executable_bundle_cost <= self.config.bundle_max_sum_cost:
                net_edge = round(1.0 - executable_bundle_cost, 4)
                edge_bps = round(net_edge * 10000, 1)
                min_liq = min(m.liquidity_usd for m in group)
                total_vol = sum(m.volume_24h_usd for m in group)
                avg_spread = sum(m.spread for m in group) / len(group)
                days = max(0.5, min(m.days_to_expiry for m in group))
                apr = round((net_edge / executable_bundle_cost) * (365.0 / days) * 100.0, 1)
                min_rules_len = min(len(m.resolution_rules) for m in group)

                anchor = group[0]
                signals.append(
                    TradeSignal(
                        signal_id=f"sig-arb-{event_id}",
                        market_id=f"bundle-{event_id}",
                        leg_market_ids=[m.market_id for m in group],
                        event_title=anchor.event_title,
                        question=f"[Giỏ {len(group)} cửa] {anchor.event_title}",
                        strategy="BUNDLE_ARB",
                        side="BUY_BUNDLE",
                        order_type="LIMIT_IOC",
                        entry_price=executable_bundle_cost,
                        fair_value=1.0000,
                        edge_bps=edge_bps,
                        expected_apr_pct=apr,
                        confidence_score=0.96,
                        liquidity_usd=round(min_liq, 2),
                        volume_24h_usd=round(total_vol, 2),
                        spread=round(avg_spread, 4),
                        days_to_expiry=days,
                        resolution_rules_len=min_rules_len,
                        rationale=(
                            f"Tổng giá Ask thực thi của toàn bộ {len(group)} cửa cộng phí là "
                            f"${executable_bundle_cost:.3f} (< $1.00). Chênh lệch ròng +{edge_bps / 100:.2f}% "
                            f"khi sự kiện phân xử sau {days:.1f} ngày."
                        ),
                    )
                )
        return signals

    def _scan_bond_carry(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []
        for c in contracts:
            if c.closed or c.days_to_expiry > self.config.bond_max_days_to_expiry or c.days_to_expiry <= 0.1:
                continue

            side = ""
            exec_ask = 0.0
            no_exec_ask = round(1.0 - c.best_bid, 4)

            if self.config.bond_min_prob <= c.best_ask <= self.config.bond_max_prob:
                side = "BUY_YES"
                exec_ask = c.best_ask
            elif self.config.bond_min_prob <= no_exec_ask <= self.config.bond_max_prob:
                side = "BUY_NO"
                exec_ask = no_exec_ask

            if not side or exec_ask <= 0.0 or exec_ask >= 0.993:
                continue

            # Empirical tail-risk & UMA dispute haircut based on market depth and rule clarity
            if c.liquidity_usd >= 100000.0 and len(c.resolution_rules) >= 120:
                tail_haircut = 0.012
            elif c.liquidity_usd >= 25000.0 and len(c.resolution_rules) >= 80:
                tail_haircut = 0.018
            else:
                tail_haircut = 0.030

            calibrated_settlement = round(1.0 - tail_haircut, 4)
            fee_cost = self.config.taker_fee_bps / 10000.0
            net_expected_edge = round(calibrated_settlement - exec_ask - fee_cost, 4)
            if net_expected_edge <= 0.005:
                continue

            edge_bps = round(net_expected_edge * 10000, 1)
            net_yield = net_expected_edge / exec_ask
            apr = round(net_yield * (365.0 / max(1.0, c.days_to_expiry)) * 100.0, 1)
            if apr < self.config.bond_min_annualized_yield * 100.0:
                continue

            signals.append(
                TradeSignal(
                    signal_id=f"sig-bond-{c.market_id}",
                    market_id=c.market_id,
                    event_title=c.event_title,
                    question=c.question,
                    strategy="BOND_CARRY",
                    side=side,
                    order_type="LIMIT_IOC",
                    entry_price=round(exec_ask + fee_cost, 4),
                    fair_value=calibrated_settlement,
                    edge_bps=edge_bps,
                    expected_apr_pct=apr,
                    confidence_score=0.88,
                    liquidity_usd=c.liquidity_usd,
                    volume_24h_usd=c.volume_24h_usd,
                    spread=c.spread,
                    days_to_expiry=c.days_to_expiry,
                    resolution_rules_len=len(c.resolution_rules),
                    rationale=(
                        f"Kèo xác suất cao (giá Ask {exec_ask * 100:.1f}¢) đáo hạn sau {c.days_to_expiry:.1f} ngày. "
                        f"Sau khi trừ dự phòng rủi ro đuôi UMA ({tail_haircut * 100:.1f}¢), kỳ vọng lãi ròng +{net_expected_edge * 100:.2f}%."
                    ),
                )
            )
        return signals

    def _scan_maker_spread(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []
        tick = self.config.tick_size
        for c in contracts:
            if c.closed or c.days_to_expiry <= 0 or not (0.25 <= c.yes_price <= 0.80):
                continue
            if not (self.config.maker_min_spread <= c.spread <= self.config.maker_max_spread):
                continue

            # Round passive bid strictly to 1-cent tick size (0.01)
            snapped_bid = round(round(c.best_bid / tick) * tick, 2)
            maker_bid = round(snapped_bid + tick, 2)
            if maker_bid >= c.best_ask - 0.005:
                continue

            fair_mid = round((c.best_bid + c.best_ask) / 2.0, 4)
            adverse_selection_haircut = 0.002
            net_edge = round(fair_mid - maker_bid - adverse_selection_haircut, 4)
            if net_edge < 0.0025:
                continue

            edge_bps = round(net_edge * 10000, 1)
            apr = round((net_edge / maker_bid) * (365.0 / max(1.0, min(c.days_to_expiry, 14.0))) * 100.0, 1)

            signals.append(
                TradeSignal(
                    signal_id=f"sig-maker-{c.market_id}",
                    market_id=c.market_id,
                    event_title=c.event_title,
                    question=c.question,
                    strategy="MAKER_SPREAD",
                    side="BUY_YES",
                    order_type="LIMIT_MAKER",
                    entry_price=maker_bid,
                    fair_value=round(fair_mid - adverse_selection_haircut, 4),
                    edge_bps=edge_bps,
                    expected_apr_pct=apr,
                    confidence_score=0.82,
                    liquidity_usd=c.liquidity_usd,
                    volume_24h_usd=c.volume_24h_usd,
                    spread=c.spread,
                    days_to_expiry=c.days_to_expiry,
                    resolution_rules_len=len(c.resolution_rules),
                    rationale=(
                        f"Sổ lệnh giãn Spread {c.spread * 100:.1f}¢ trên thị trường thanh khoản ${c.liquidity_usd:,.0f}. "
                        f"Đặt lệnh chờ mua đúng bước giá ${maker_bid:.2f} (dưới giá Mid ${fair_mid:.3f})."
                    ),
                )
            )
        return signals
