"""
Polymarket Data Client (Gamma API + CLOB Orderbook normalizer).
Fetches active events and markets without requiring wallet credentials.
"""
from __future__ import annotations

import email.utils
import json
import math
import ipaddress
import subprocess
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
    yes_token_id: str = ""
    no_token_id: str = ""
    settlement_yes: Optional[float] = None
    closed: bool = False
    resolved_outcome: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PolymarketClient:
    """Client for querying Polymarket public Gamma and CLOB endpoints."""

    def __init__(self, config: TradingConfig = DEFAULT_CONFIG):
        self.config = config
        self.last_source: str = "unknown"
        self.server_now: Optional[datetime] = None
        self._dns_cache = {}

    def fetch_active_markets(self, limit: int = 40) -> List[MarketContract]:
        """
        Pulls live active markets from Polymarket Gamma API.
        Marks `last_source = "LIVE_POLYMARKET_GAMMA_API"` on success.
        """
        params = urllib.parse.urlencode({
            "active": "true",
            "closed": "false",
            "limit": str(limit),
            "order": "volume24hr",
            "ascending": "false",
        })
        base_url = self.config.gamma_events_url.split("?")[0]
        url = f"{base_url}?{params}"
        try:
            raw_bytes, server_now = self._http_get_with_clock_skew_tolerance(url)
            self.server_now = server_now
            raw_data = json.loads(raw_bytes.decode("utf-8"))
            contracts = self._parse_events_payload(raw_data, reference_now=server_now)
            if contracts:
                self.last_source = "LIVE_POLYMARKET_GAMMA_API"
                return contracts
        except Exception as exc:
            self.last_source = f"SNAPSHOT_FALLBACK ({type(exc).__name__}: {exc})"

        if self.last_source == "unknown":
            self.last_source = "SNAPSHOT_FALLBACK (empty Gamma response)"
        return self._get_fallback_contracts()

    def _http_get_with_clock_skew_tolerance(self, url: str) -> tuple[bytes, datetime]:
        """
        Performs HTTP GET and extracts the authoritative server `Date` header so
        days-to-expiry math remains accurate even if the local host clock is skewed.
        If local ISP DNS sinkholes `gamma-api.polymarket.com` to 127.0.0.1 (Errno 61),
        automatically resolves the real Cloudflare IP via Google/Cloudflare DoH and uses `curl --resolve`. TLS verification stays enabled.
        """
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) PolymarketAutopilot/2.0",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.http_timeout_sec) as resp:
                server_now = self._extract_server_time(resp.headers.get("Date"))
                return resp.read(), server_now
        except Exception as initial_error:
            errors = [f"system resolver/HTTPS: {initial_error}"]
            parsed_url = urllib.parse.urlparse(url)
            host = parsed_url.hostname or "gamma-api.polymarket.com"
            if host not in self._dns_cache:
                self._dns_cache[host] = self._resolve_host_via_doh(host)
            doh_ip = self._dns_cache[host]

            curl_cmds = []
            if doh_ip:
                curl_cmds.append(
                    ["curl", "-f", "-sS", "--resolve", f"{host}:443:{doh_ip}", "--max-time", "10", "-D", "-", url]
                )
            curl_cmds.append(["curl", "-f", "-sS", "--max-time", "8", "-D", "-", url])

            for cmd in curl_cmds:
                proc = subprocess.run(cmd, capture_output=True, timeout=12, check=False)
                if proc.returncode != 0:
                    stderr = proc.stderr.decode("utf-8", errors="replace").strip() if isinstance(proc.stderr, bytes) else "request failed"
                    route = "DoH address" if "--resolve" in cmd else "system address"
                    errors.append(f"{route}: curl {proc.returncode}: {stderr[:240]}")
                if proc.returncode == 0 and proc.stdout:
                    parts = proc.stdout.split(b"\r\n\r\n")
                    body = parts[-1]
                    headers_raw = b"\r\n\r\n".join(parts[:-1]).decode("utf-8", errors="ignore")
                    date_str = None
                    for line in headers_raw.splitlines():
                        if line.lower().startswith("date:"):
                            date_str = line.split(":", 1)[1].strip()
                    if body.strip().startswith(b"[") or body.strip().startswith(b"{"):
                        return body, self._extract_server_time(date_str)
            raise urllib.error.URLError(f"{host} unreachable; " + "; ".join(errors)) from initial_error

    @staticmethod
    def _resolve_host_via_doh(hostname: str) -> Optional[str]:
        """Resolves a hostname via public DNS-over-HTTPS (Google / Cloudflare) when local ISP DNS returns 127.0.0.1."""
        doh_endpoints = [
            f"https://dns.google/resolve?name={urllib.parse.quote(hostname)}&type=A",
            f"https://1.1.1.1/dns-query?name={urllib.parse.quote(hostname)}&type=A",
        ]
        for endpoint in doh_endpoints:
            proc = subprocess.run(
                ["curl", "-sS", "-H", "Accept: application/dns-json", "--max-time", "5", endpoint],
                capture_output=True,
                timeout=7,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                try:
                    data = json.loads(proc.stdout.decode("utf-8"))
                    for ans in data.get("Answer", []):
                        ip = str(ans.get("data", "")).strip()
                        if ans.get("type") == 1 and ip and ipaddress.ip_address(ip).is_global:
                            return ip
                except Exception:
                    continue
        return None

    @staticmethod
    def _extract_server_time(date_header: Optional[str]) -> datetime:
        if date_header:
            try:
                dt = email.utils.parsedate_to_datetime(date_header)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
        return datetime.now(timezone.utc)

    def fetch_clob_book_top(self, token_id: str) -> Optional[Dict[str, float]]:
        """
        Queries Polymarket CLOB `/book` endpoint for a token_id to verify
        executable best_bid, best_ask, and top-of-book depth in USD.
        """
        if not token_id:
            return None
        url = f"{self.config.clob_book_url}?token_id={urllib.parse.quote(token_id)}"
        try:
            raw, _ = self._http_get_with_clock_skew_tolerance(url)
            return self.normalize_book(json.loads(raw))
        except Exception:
            return None

    @staticmethod
    def normalize_book(book: Dict[str, Any]) -> Dict[str, Any]:
        def levels(side, reverse):
            result = [(float(x["price"]), float(x["size"])) for x in book.get(side, [])]
            if any(not math.isfinite(p) or not math.isfinite(q) or not 0 < p < 1 or q <= 0 for p, q in result):
                raise ValueError("Invalid orderbook level")
            return sorted(result, reverse=reverse)[:5]
        bids, asks = levels("bids", True), levels("asks", False)
        if bids and asks and bids[0][0] >= asks[0][0]:
            raise ValueError("Crossed orderbook")
        tick = float(book.get("tick_size", "0.01"))
        minimum = float(book.get("min_order_size", "0"))
        if not math.isfinite(tick) or tick <= 0 or not math.isfinite(minimum) or minimum < 0:
            raise ValueError("Invalid book metadata")
        return {"bids": bids, "asks": asks, "tick_size": tick, "min_order_size": minimum,
                "best_bid": bids[0][0] if bids else 0.0,
                "best_ask": asks[0][0] if asks else 1.0,
                "bid_depth_usd": sum(p*q for p,q in bids),
                "ask_depth_usd": sum(p*q for p,q in asks)}

    def fetch_market(self, market_id: str) -> Optional[MarketContract]:
        try:
            base = self.config.gamma_events_url.split("/events")[0]
            raw, now = self._http_get_with_clock_skew_tolerance(
                f"{base}/markets/{urllib.parse.quote(market_id, safe='')}")
            market = json.loads(raw)
            event = (market.get("events") or [{}])[0]
            rows = self._parse_events_payload([{**event, "markets": [market]}], now, include_closed=True)
            return rows[0] if rows else None
        except Exception:
            return None

    def _parse_events_payload(
        self,
        events: List[Dict[str, Any]],
        reference_now: Optional[datetime] = None,
        include_closed: bool = False,
    ) -> List[MarketContract]:
        now = reference_now or datetime.now(timezone.utc)
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
                if isinstance(m, dict) and (include_closed or (m.get("active") is not False and not m.get("closed", False)))
            ]
            outcomes_count = len(raw_markets)

            for m in active_markets:
                try:
                    market_id = str(m.get("id", ""))
                    question = str(m.get("question") or event_title).strip()
                    slug = str(m.get("slug") or event.get("slug") or market_id)

                    raw_prices = m.get("outcomePrices", '["0.5", "0.5"]')
                    prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices

                    yes_price = float(prices[0]) if len(prices) > 0 else 0.5
                    no_price = float(prices[1]) if len(prices) > 1 else round(1.0 - yes_price, 4)

                    outcomes = m.get("outcomes", '["Yes", "No"]')
                    outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
                    if [str(x).lower() for x in outcomes] != ["yes", "no"]:
                        continue
                    settlement_yes = None
                    if m.get("closed") and m.get("umaResolutionStatus") == "resolved":
                        if (yes_price, no_price) in ((1.0, 0.0), (0.0, 1.0), (0.5, 0.5)):
                            settlement_yes = yes_price

                    raw_bid = m.get("bestBid")
                    raw_ask = m.get("bestAsk")
                    best_bid = float(raw_bid) if raw_bid is not None else 0.0
                    best_ask = float(raw_ask) if raw_ask is not None else 1.0
                    if not all(math.isfinite(x) and 0 <= x <= 1 for x in (yes_price, no_price, best_bid, best_ask)):
                        continue
                    spread = round(max(0.0, best_ask - best_bid), 4)

                    liquidity_usd = float(m.get("liquidityNum") or m.get("liquidity") or 0.0)
                    volume_24h_usd = float(m.get("volume24hr") or m.get("volumeNum") or 0.0)

                    end_date_iso = str(m.get("endDate") or event.get("endDate") or "")
                    days_to_expiry = self._compute_days_to_expiry(end_date_iso, now)

                    resolution_rules = str(
                        m.get("description") or event.get("description") or ""
                    ).strip()

                    raw_tokens = m.get("clobTokenIds", "[]")
                    token_ids = json.loads(raw_tokens) if isinstance(raw_tokens, str) else (raw_tokens or [])
                    yes_token_id = str(token_ids[0]) if token_ids else ""

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
                            yes_token_id=yes_token_id,
                            no_token_id=str(token_ids[1]) if len(token_ids) > 1 else "",
                            settlement_yes=settlement_yes,
                            closed=bool(m.get("closed", False)),
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
            return delta_days
        except ValueError:
            return 14.0

    def _get_fallback_contracts(self) -> List[MarketContract]:
        """Offline test fixture contracts (used only when network is unreachable or in unit tests)."""
        return [
            MarketContract(
                market_id="pm-fed-nov-hold",
                event_id="evt-fed-rate-decision",
                event_title="Fed Interest Rate Decision - Next FOMC Meeting",
                question="Will the Fed cut rates by 25 bps at the upcoming FOMC meeting?",
                slug="fed-cut-25bps-next-fomc",
                yes_price=0.670,
                no_price=0.330,
                best_bid=0.665,
                best_ask=0.675,
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
                yes_price=0.250,
                no_price=0.750,
                best_bid=0.245,
                best_ask=0.255,
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
                yes_price=0.030,
                no_price=0.970,
                best_bid=0.028,
                best_ask=0.032,
                spread=0.004,
                liquidity_usd=145000.0,
                volume_24h_usd=44000.0,
                end_date_iso="2026-11-07T19:00:00Z",
                days_to_expiry=9.0,
                resolution_rules="Resolves to YES if the FOMC cuts rates by 50 bps or more, or increases rates, according to the official Federal Reserve press release.",
                neg_risk=True,
                outcomes_count_in_event=3,
            ),
            MarketContract(
                market_id="pm-btc-above-55k-week",
                event_id="evt-btc-weekly-floor",
                event_title="Bitcoin Weekly Milestone Check",
                question="Will Bitcoin close above $55,000 this Friday 23:59 UTC?",
                slug="btc-close-above-55k-friday",
                yes_price=0.952,
                no_price=0.048,
                best_bid=0.948,
                best_ask=0.955,
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
                yes_price=0.962,
                no_price=0.038,
                best_bid=0.958,
                best_ask=0.965,
                spread=0.007,
                liquidity_usd=276000.0,
                volume_24h_usd=83200.0,
                end_date_iso="2026-11-05T23:59:00Z",
                days_to_expiry=7.0,
                resolution_rules="Resolves to YES if no partial or full lapse in federal appropriations occurs before November 5, 2026 11:59 PM ET per OPM announcements.",
                neg_risk=False,
                outcomes_count_in_event=1,
            ),
            MarketContract(
                market_id="pm-eth-etf-inflows-pos",
                event_id="evt-eth-weekly-flows",
                event_title="Spot ETH ETF Weekly Net Flows",
                question="Will US Spot Ethereum ETFs record positive net inflows this week?",
                slug="eth-etf-positive-net-inflows-week",
                yes_price=0.610,
                no_price=0.390,
                best_bid=0.590,
                best_ask=0.620,
                spread=0.030,
                liquidity_usd=84000.0,
                volume_24h_usd=52000.0,
                end_date_iso="2026-11-04T20:00:00Z",
                days_to_expiry=6.0,
                resolution_rules="Resolves to YES if aggregate net flows across all US-listed spot Ethereum ETFs for the trading week are strictly greater than $0 per Farside Investors data.",
                neg_risk=False,
                outcomes_count_in_event=1,
            ),
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
