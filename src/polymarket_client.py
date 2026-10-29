"""
Polymarket Data Client (Gamma API + CLOB Orderbook normalizer).
Fetches active events and markets without requiring wallet credentials.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import DEFAULT_CONFIG, TradingConfig


@dataclass
class MarketContract:
    market_id: str
    event_id: str
    event_title: str
    question: str
    slug: str
    yes_price: float
    no_price: float
    best_bid: float
    best_ask: float
    spread: float
    liquidity_usd: float
    volume_24h_usd: float
    end_date_iso: str
    days_to_expiry: float
    resolution_rules: str
    neg_risk: bool
    outcomes_count_in_event: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PolymarketClient:
    """Client for querying Polymarket public Gamma and CLOB endpoints."""

    def __init__(self, config: TradingConfig = DEFAULT_CONFIG):
        self.config = config
        self.last_source: str = "unknown"

    def fetch_active_markets(self, limit: int = 35) -> List[MarketContract]:
        """
        Attempt to pull live markets from Polymarket Gamma API.
        Falls back to curated snapshot only if network is unreachable.
        """
        params = urllib.parse.urlencode({
            "active": "true",
            "closed": "false",
            "limit": str(limit),
            "order": "volume24hr",
            "ascending": "false",
        })
        url = f"{self.config.gamma_events_url}?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "PolymarketAutopilot/1.0 (Quantitative Research Engine)",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.http_timeout_sec) as resp:
                raw_data = json.loads(resp.read().decode("utf-8"))
                contracts = self._parse_events_payload(raw_data)
                if contracts:
                    self.last_source = "LIVE_POLYMARKET_GAMMA_API"
                    return contracts
        except Exception as exc:
            self.last_source = f"SNAPSHOT_FALLBACK ({type(exc).__name__})"

        return self._get_fallback_contracts()

    def _parse_events_payload(self, events: List[Dict[str, Any]]) -> List[MarketContract]:
        now = datetime.now(timezone.utc)
        contracts: List[MarketContract] = []

        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("id", ""))
            event_title = str(event.get("title", "Unknown Event")).strip()
            neg_risk = bool(event.get("negRisk", False))
            raw_markets = event.get("markets") or []
            active_markets = [
                m for m in raw_markets
                if isinstance(m, dict) and m.get("active") is not False and not m.get("closed", False)
            ]
            outcomes_count = len(active_markets)

            for m in active_markets:
                try:
                    market_id = str(m.get("id", ""))
                    question = str(m.get("question") or event_title).strip()
                    slug = str(m.get("slug") or event.get("slug") or market_id)

                    # Parse outcomePrices JSON string e.g. '["0.62", "0.38"]'
                    raw_prices = m.get("outcomePrices", '["0.5", "0.5"]')
                    if isinstance(raw_prices, str):
                        prices = json.loads(raw_prices)
                    else:
                        prices = raw_prices

                    yes_price = float(prices[0]) if len(prices) > 0 else 0.5
                    no_price = float(prices[1]) if len(prices) > 1 else round(1.0 - yes_price, 4)

                    if yes_price <= 0.001 or yes_price >= 0.999:
                        continue

                    best_bid = float(m.get("bestBid") or max(0.01, yes_price - 0.01))
                    best_ask = float(m.get("bestAsk") or min(0.99, yes_price + 0.01))
                    if best_ask < best_bid:
                        best_bid, best_ask = yes_price - 0.005, yes_price + 0.005
                    spread = round(max(0.001, best_ask - best_bid), 4)

                    liquidity_usd = float(m.get("liquidityNum") or m.get("liquidity") or 0.0)
                    volume_24h_usd = float(m.get("volume24hr") or m.get("volumeNum") or 0.0)

                    end_date_iso = str(m.get("endDate") or event.get("endDate") or "")
                    days_to_expiry = self._compute_days_to_expiry(end_date_iso, now)

                    resolution_rules = str(
                        m.get("description") or event.get("description") or ""
                    ).strip()

                    contracts.append(
                        MarketContract(
                            market_id=market_id,
                            event_id=event_id,
                            event_title=event_title,
                            question=question,
                            slug=slug,
                            yes_price=round(yes_price, 4),
                            no_price=round(no_price, 4),
                            best_bid=round(best_bid, 4),
                            best_ask=round(best_ask, 4),
                            spread=spread,
                            liquidity_usd=round(liquidity_usd, 2),
                            volume_24h_usd=round(volume_24h_usd, 2),
                            end_date_iso=end_date_iso,
                            days_to_expiry=round(days_to_expiry, 2),
                            resolution_rules=resolution_rules,
                            neg_risk=neg_risk,
                            outcomes_count_in_event=outcomes_count,
                        )
                    )
                except (ValueError, TypeError, KeyError, IndexError):
                    continue

        return contracts

    @staticmethod
    def _compute_days_to_expiry(end_date_iso: str, now: datetime) -> float:
        if not end_date_iso:
            return 14.0
        try:
            clean_iso = end_date_iso.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta_days = (dt - now).total_seconds() / 86400.0
            return max(0.5, delta_days)
        except ValueError:
            return 14.0

    def _get_fallback_contracts(self) -> List[MarketContract]:
        """High-fidelity snapshot of representative Polymarket contracts for offline/sandbox testing."""
        return [
            # Event 1: Multi-outcome mutually exclusive event with bundle arbitrage (< $1.00 sum)
            MarketContract(
                market_id="pm-fed-nov-hold",
                event_id="evt-fed-rate-decision",
                event_title="Fed Interest Rate Decision - Next FOMC Meeting",
                question="Will the Fed cut rates by 25 bps at the upcoming FOMC meeting?",
                slug="fed-cut-25bps-next-fomc",
                yes_price=0.680,
                no_price=0.320,
                best_bid=0.675,
                best_ask=0.685,
                spread=0.010,
                liquidity_usd=425000.0,
                volume_24h_usd=189000.0,
                end_date_iso="2026-11-07T19:00:00Z",
                days_to_expiry=9.0,
                resolution_rules="Resolves to YES if the Federal Open Market Committee lowers the target federal funds rate range by exactly 25 basis points in its official statement.",
                neg_risk=True,
                outcomes_count_in_event=3,
            ),
            MarketContract(
                market_id="pm-fed-nov-nochange",
                event_id="evt-fed-rate-decision",
                event_title="Fed Interest Rate Decision - Next FOMC Meeting",
                question="Will the Fed leave interest rates unchanged at the upcoming FOMC meeting?",
                slug="fed-no-change-next-fomc",
                yes_price=0.255,
                no_price=0.745,
                best_bid=0.250,
                best_ask=0.260,
                spread=0.010,
                liquidity_usd=310000.0,
                volume_24h_usd=112000.0,
                end_date_iso="2026-11-07T19:00:00Z",
                days_to_expiry=9.0,
                resolution_rules="Resolves to YES if the Federal Open Market Committee maintains the current target federal funds rate range in its official FOMC statement.",
                neg_risk=True,
                outcomes_count_in_event=3,
            ),
            MarketContract(
                market_id="pm-fed-nov-50bps",
                event_id="evt-fed-rate-decision",
                event_title="Fed Interest Rate Decision - Next FOMC Meeting",
                question="Will the Fed cut rates by 50+ bps or hike at the upcoming FOMC meeting?",
                slug="fed-50bps-or-hike-next-fomc",
                yes_price=0.032,
                no_price=0.968,
                best_bid=0.028,
                best_ask=0.034,
                spread=0.006,
                liquidity_usd=145000.0,
                volume_24h_usd=44000.0,
                end_date_iso="2026-11-07T19:00:00Z",
                days_to_expiry=9.0,
                resolution_rules="Resolves to YES if the FOMC cuts rates by 50 bps or more, or increases rates, according to the official Federal Reserve press release.",
                neg_risk=True,
                outcomes_count_in_event=3,
            ),
            # Event 2: High-Probability Near-Resolution Carry (Bond Carry)
            MarketContract(
                market_id="pm-btc-above-55k-week",
                event_id="evt-btc-weekly-floor",
                event_title="Bitcoin Weekly Milestone Check",
                question="Will Bitcoin close above $55,000 this Friday 23:59 UTC?",
                slug="btc-close-above-55k-friday",
                yes_price=0.942,
                no_price=0.058,
                best_bid=0.938,
                best_ask=0.945,
                spread=0.007,
                liquidity_usd=198000.0,
                volume_24h_usd=94500.0,
                end_date_iso="2026-11-02T23:59:00Z",
                days_to_expiry=4.5,
                resolution_rules="Resolves to YES if the Coinbase BTC-USD 1-minute candle close at 23:59 UTC on Friday is strictly greater than $55,000.00.",
                neg_risk=False,
                outcomes_count_in_event=1,
            ),
            MarketContract(
                market_id="pm-us-gov-shutdown-week",
                event_id="evt-us-funding-oct",
                event_title="US Government Operations Status This Week",
                question="Will the US Federal Government remain open through November 5?",
                slug="us-gov-remain-open-nov-5",
                yes_price=0.954,
                no_price=0.046,
                best_bid=0.950,
                best_ask=0.958,
                spread=0.008,
                liquidity_usd=276000.0,
                volume_24h_usd=83200.0,
                end_date_iso="2026-11-05T23:59:00Z",
                days_to_expiry=7.0,
                resolution_rules="Resolves to YES if no partial or full lapse in federal appropriations occurs before November 5, 2026 11:59 PM ET per OPM announcements.",
                neg_risk=False,
                outcomes_count_in_event=1,
            ),
            # Event 3: Orderbook Maker Spread Capture
            MarketContract(
                market_id="pm-eth-etf-inflows-pos",
                event_id="evt-eth-weekly-flows",
                event_title="Spot ETH ETF Weekly Net Flows",
                question="Will US Spot Ethereum ETFs record positive net inflows this week?",
                slug="eth-etf-positive-net-inflows-week",
                yes_price=0.610,
                no_price=0.390,
                best_bid=0.594,
                best_ask=0.626,
                spread=0.032,
                liquidity_usd=84000.0,
                volume_24h_usd=52000.0,
                end_date_iso="2026-11-04T20:00:00Z",
                days_to_expiry=6.0,
                resolution_rules="Resolves to YES if aggregate net flows across all US-listed spot Ethereum ETFs for the trading week are strictly greater than $0 per Farside Investors data.",
                neg_risk=False,
                outcomes_count_in_event=1,
            ),
            MarketContract(
                market_id="pm-nyc-temp-bracket",
                event_id="evt-nyc-daily-weather",
                event_title="NYC Central Park Daily High Temperature",
                question="Will NYC Central Park high temperature exceed 58°F tomorrow?",
                slug="nyc-central-park-high-above-58f",
                yes_price=0.720,
                no_price=0.280,
                best_bid=0.705,
                best_ask=0.733,
                spread=0.028,
                liquidity_usd=38500.0,
                volume_24h_usd=27400.0,
                end_date_iso="2026-10-31T12:00:00Z",
                days_to_expiry=2.0,
                resolution_rules="Resolves to YES if the National Weather Service (NWS) Daily Climate Report (CLI) for Central Park (KNYC) reports a maximum temperature >= 59°F.",
                neg_risk=False,
                outcomes_count_in_event=1,
            ),
            # Event 4: Low-liquidity / wide-spread trap (should be REJECTED by Risk Manager)
            MarketContract(
                market_id="pm-illiquid-meme-trap",
                event_id="evt-obscure-pop-culture",
                event_title="Viral Social Media Poll Outcome",
                question="Will X account post a meme coin ticker before midnight?",
                slug="viral-meme-ticker-midnight",
                yes_price=0.890,
                no_price=0.110,
                best_bid=0.820,
                best_ask=0.940,
                spread=0.120,
                liquidity_usd=1200.0,
                volume_24h_usd=450.0,
                end_date_iso="2026-11-01T00:00:00Z",
                days_to_expiry=2.5,
                resolution_rules="Short vague rule.",
                neg_risk=False,
                outcomes_count_in_event=1,
            ),
        ]
