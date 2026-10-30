"""
Core configuration and risk guardrails for the Polymarket Quantitative Paper-Trading Engine.
"""
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AUTOPILOT_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
DB_PATH = DATA_DIR / "autopilot.db"
STATE_JSON_PATH = DATA_DIR / "portfolio_state.json"
LOCK_FILE_PATH = DATA_DIR / "autopilot.lock"
AI_CACHE_FILE_PATH = DATA_DIR / "ai_rules_cache.json"


@dataclass(frozen=True)
class TradingConfig:
    # Capital & Position Sizing Guardrails
    initial_capital_usdc: float = 1000.0
    max_position_pct: float = 0.08          # Max 8% of equity per single market ($80 on $1k)
    max_strategy_bucket_pct: float = 0.30   # Max 30% of equity per strategy type
    max_total_exposure_pct: float = 0.60    # Always keep >= 40% in cash reserve
    max_daily_drawdown_pct: float = 0.03    # 3% daily drawdown kill-switch from day start / peak
    kelly_fraction: float = 0.25            # Quarter-Kelly conservative multiplier
    min_order_size_usdc: float = 5.0        # Minimum order size ($5 USDC); smaller Kelly sizes are skipped

    # Market Quality & Trap Filters
    min_liquidity_usd: float = 5000.0       # Reject markets with < $5,000 liquidity
    min_volume_24h_usd: float = 1500.0      # Reject dead markets with < $1,500 24h volume
    max_spread_taker: float = 0.030         # Max 3.0 cents bid-ask spread for taker orders
    min_resolution_text_len: int = 80       # Minimum characters in resolution rules to avoid vague markets

    # Strategy 1: Bundle Arbitrage (Sum of executable ASK prices < $1.00)
    bundle_max_sum_cost: float = 0.990      # Require at least 1.0% gross arbitrage edge on ASK prices
    taker_fee_bps: float = 10.0             # 10 bps per-leg execution/slippage buffer

    # Strategy 2: High-Probability Bond Carry (Endgame)
    bond_min_prob: float = 0.94             # 94.0% minimum implied probability (matches UI)
    bond_max_prob: float = 0.992            # 99.2% maximum price
    bond_max_days_to_expiry: float = 14.0   # Must resolve within 14 days
    bond_min_annualized_yield: float = 0.12 # Minimum 12% annualized yield after tail-risk haircut

    # Strategy 3: Maker Spread Capture
    maker_min_spread: float = 0.020         # Minimum 2.0 cents spread to quote inside
    maker_max_spread: float = 0.100         # Avoid broken orderbooks with > 10c spread
    tick_size: float = 0.01                 # Standard Polymarket 1-cent tick size

    # Execution Honesty & Network Controls
    allow_snapshot_trading: bool = False    # Do not open new trades on offline fallback unless in unit tests
    http_timeout_sec: float = 10.0

    # API Endpoints (Public Read-Only)
    gamma_events_url: str = "https://gamma-api.polymarket.com/events"
    clob_book_url: str = "https://clob.polymarket.com/book"


DEFAULT_CONFIG = TradingConfig()
