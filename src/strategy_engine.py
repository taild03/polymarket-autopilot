"""
Strategy Engine for Polymarket Autopilot.
Implements three quantitative strategies:
1. BUNDLE_ARB: Multi-outcome mutually exclusive Dutch-book / rebalancing arbitrage.
2. BOND_CARRY: High-probability near-resolution yield capture (annualized APR optimization).
3. MAKER_SPREAD: Orderbook spread capture via passive limit orders on high-volume markets.
"""
from collections import defaultdict
from dataclasses import dataclass, asdict
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
    entry_price: float          # Target execution price ($0.01 - $0.99)
    fair_value: float           # Estimated true probability / settlement value
    edge_bps: float             # Expected edge in basis points (100 bps = 1.0%)
    expected_apr_pct: float     # Annualized return percentage
    confidence_score: float     # 0.0 to 1.0
    liquidity_usd: float
    volume_24h_usd: float
    spread: float
    days_to_expiry: float
    resolution_rules_len: int
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyEngine:
    """Scans normalized Polymarket contracts and generates quantitative trade signals."""

    def __init__(self, config: TradingConfig = DEFAULT_CONFIG):
        self.config = config

    def evaluate_markets(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []

        # 1. Check Multi-Outcome Event Bundle Arbitrage
        signals.extend(self._scan_bundle_arbitrage(contracts))

        # 2. Check High-Probability Near-Resolution Carry (Bond Carry)
        signals.extend(self._scan_bond_carry(contracts))

        # 3. Check Orderbook Maker Spread Capture
        signals.extend(self._scan_maker_spread(contracts))

        # Sort signals by expected APR and edge_bps descending
        signals.sort(key=lambda s: (s.edge_bps, s.expected_apr_pct), reverse=True)
        return signals

    def _scan_bundle_arbitrage(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        by_event: Dict[str, List[MarketContract]] = defaultdict(list)
        for c in contracts:
            if c.neg_risk and c.outcomes_count_in_event >= 2:
                by_event[c.event_id].append(c)

        signals: List[TradeSignal] = []
        for event_id, group in by_event.items():
            if len(group) < 2 or len(group) != group[0].outcomes_count_in_event:
                continue

            sum_yes_ask = sum(m.best_ask for m in group)
            sum_yes_mid = sum(m.yes_price for m in group)
            effective_sum = min(sum_yes_ask, sum_yes_mid)

            if 0.80 < effective_sum <= self.config.bundle_arb_max_sum:
                net_edge = 1.0 - effective_sum
                edge_bps = round(net_edge * 10000, 1)
                min_liq = min(m.liquidity_usd for m in group)
                total_vol = sum(m.volume_24h_usd for m in group)
                avg_spread = sum(m.spread for m in group) / len(group)
                days = max(0.5, min(m.days_to_expiry for m in group))
                apr = round((net_edge / effective_sum) * (365.0 / days) * 100.0, 1)
                min_rules_len = min(len(m.resolution_rules) for m in group)

                anchor = group[0]
                signals.append(
                    TradeSignal(
                        signal_id=f"sig-arb-{event_id}",
                        market_id=anchor.market_id,
                        event_title=anchor.event_title,
                        question=f"[Giỏ {len(group)} cửa] {anchor.event_title}",
                        strategy="BUNDLE_ARB",
                        side="BUY_BUNDLE",
                        order_type="LIMIT_IOC",
                        entry_price=round(effective_sum, 4),
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
                            f"Tổng giá mua toàn bộ {len(group)} cửa loại trừ nhau chỉ bằng "
                            f"${effective_sum:.3f} (< $1.00). Khóa lợi nhuận toán học +{edge_bps / 100:.2f}% "
                            f"khi sự kiện phân xử sau {days:.1f} ngày."
                        ),
                    )
                )
        return signals

    def _scan_bond_carry(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []
        for c in contracts:
            if c.days_to_expiry > self.config.bond_carry_max_days or c.days_to_expiry <= 0.1:
                continue

            # Determine if either YES or NO is in the high-probability carry zone (88c - 97.5c)
            side = ""
            price = 0.0
            if self.config.bond_carry_min_prob <= c.yes_price <= self.config.bond_carry_max_prob:
                side = "BUY_YES"
                price = c.best_ask if c.best_ask <= self.config.bond_carry_max_prob else c.yes_price
            elif self.config.bond_carry_min_prob <= c.no_price <= self.config.bond_carry_max_prob:
                side = "BUY_NO"
                price = round(1.0 - c.best_bid, 4) if (1.0 - c.best_bid) <= self.config.bond_carry_max_prob else c.no_price

            if not side or price <= 0.0 or price >= 0.99:
                continue

            # Estimate conservative true probability boost for liquid near-expiry contracts
            est_win_prob = min(0.992, price + 0.028)
            expected_val = est_win_prob - price
            if expected_val <= 0.008:
                continue

            edge_bps = round(expected_val * 10000, 1)
            gross_yield = (1.0 - price) / price
            apr = round(gross_yield * (365.0 / max(1.0, c.days_to_expiry)) * 100.0, 1)

            signals.append(
                TradeSignal(
                    signal_id=f"sig-bond-{c.market_id}",
                    market_id=c.market_id,
                    event_title=c.event_title,
                    question=c.question,
                    strategy="BOND_CARRY",
                    side=side,
                    order_type="LIMIT_MAKER",
                    entry_price=round(price, 4),
                    fair_value=round(est_win_prob, 4),
                    edge_bps=edge_bps,
                    expected_apr_pct=apr,
                    confidence_score=0.88,
                    liquidity_usd=c.liquidity_usd,
                    volume_24h_usd=c.volume_24h_usd,
                    spread=c.spread,
                    days_to_expiry=c.days_to_expiry,
                    resolution_rules_len=len(c.resolution_rules),
                    rationale=(
                        f"Kèo xác suất cao ({price * 100:.1f}%) đáo hạn ngắn ({c.days_to_expiry:.1f} ngày). "
                        f"Lợi suất đáo hạn +{(1.0 - price) / price * 100:.2f}% (tương đương ~{apr:.0f}% APR)."
                    ),
                )
            )
        return signals

    def _scan_maker_spread(self, contracts: List[MarketContract]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []
        for c in contracts:
            # Look for mid-probability active markets where spread >= 2.0c
            if not (0.25 <= c.yes_price <= 0.80):
                continue
            if c.spread < self.config.maker_min_spread:
                continue

            # Place passive bid slightly above current best_bid to capture half-spread
            maker_bid = round(c.best_bid + 0.004, 4)
            fair_mid = round((c.best_bid + c.best_ask) / 2.0, 4)
            edge = fair_mid - maker_bid
            if edge <= 0.006:
                continue

            edge_bps = round(edge * 10000, 1)
            apr = round((edge / maker_bid) * (365.0 / max(1.0, min(c.days_to_expiry, 14.0))) * 100.0, 1)

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
                    fair_value=fair_mid,
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
                        f"Đặt lệnh Limit Maker tại ${maker_bid:.3f} (Fair Mid ${fair_mid:.3f}), hưởng lợi thế +{edge_bps:.0f} bps."
                    ),
                )
            )
        return signals
