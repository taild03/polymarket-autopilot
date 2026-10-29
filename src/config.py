"""
Configuration and hard risk parameters for Polymarket Autopilot.
All risk thresholds are enforced at the execution layer before any order is recorded.
"""
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "autopilot.db"
STATE_JSON_PATH = DATA_DIR / "portfolio_state.json"


@dataclass(frozen=True)
class TradingConfig:
    # Paper Trading Capital
    initial_capital_usdc: float = 1000.00

    # Hard Risk Guardrails
    max_position_pct: float = 0.05          # Max 5% of total equity per trade ($50 on $1,000)
    max_total_exposure_pct: float = 0.50    # Max 50% of equity deployed across all open positions
    max_daily_drawdown_pct: float = 0.03    # 3% daily drawdown triggers automatic Kill Switch
    kelly_fraction: float = 0.25            # Quarter-Kelly conservative sizing

    # Market Quality & Liquidity Filters
    min_liquidity_usd: float = 5000.0       # Minimum market liquidity in USD
    min_volume_24h_usd: float = 1500.0      # Minimum 24h trading volume in USD
    max_spread_taker: float = 0.045         # Maximum acceptable bid-ask spread (4.5 cents)
    min_resolution_text_len: int = 40       # Minimum characters in resolution rules to avoid vague markets

    # Strategy Thresholds
    bundle_arb_max_sum: float = 0.985       # Multi-outcome YES sum threshold (< $0.985 -> >=1.5% arb)
    bond_carry_min_prob: float = 0.88       # High-probability floor (88c)
    bond_carry_max_prob: float = 0.975      # High-probability ceiling (97.5c)
    bond_carry_max_days: float = 30.0       # Max days to resolution for short-term bond carry
    maker_min_spread: float = 0.020         # Minimum spread (2c) to provide maker liquidity

    # API Endpoints
    gamma_events_url: str = "https://gamma-api.polymarket.com/events"
    gamma_markets_url: str = "https://gamma-api.polymarket.com/markets"
    clob_book_url: str = "https://clob.polymarket.com/book"
    http_timeout_sec: int = 10


DEFAULT_CONFIG = TradingConfig()
