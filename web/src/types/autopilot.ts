export type StrategyType = "BUNDLE_ARB" | "BOND_CARRY" | "MAKER_SPREAD";

export interface AccountSlotInfo {
  slot_id: "account_1" | "account_2";
  label: string;
  model_tier: string;
  configured: boolean;
  status: "ACTIVE" | "STANDBY" | "COOLDOWN" | "READY_TO_LINK";
  calls_succeeded: number;
  quota_hits: number;
  cooldown_until_iso: string;
  last_used_iso: string;
}

export interface AccountRouterState {
  active_slot: "account_1" | "account_2";
  total_switches: number;
  last_switch_reason: string;
  last_switch_at: string;
  accounts: {
    account_1: AccountSlotInfo;
    account_2: AccountSlotInfo;
  };
}

export interface PortfolioMetrics {
  cycle_count: number;
  initial_capital_usdc: number;
  cash_usdc: number;
  current_exposure_usdc: number;
  open_market_value_usdc: number;
  unrealized_pnl_usdc: number;
  realized_pnl_usdc: number;
  total_pnl_usdc: number;
  total_equity_usdc: number;
  return_pct: number;
  open_positions_count: number;
  closed_positions_count: number;
  reserved_cash_usdc?: number;
  pending_orders_count?: number;
}

export interface OpenPosition {
  position_id: string;
  market_id: string;
  event_title: string;
  question: string;
  strategy: StrategyType;
  side: string;
  order_type: string;
  shares_qty: number;
  entry_price: number;
  mark_price: number;
  fair_value: number;
  cost_basis_usdc: number;
  market_value_usdc: number;
  unrealized_pnl_usdc: number;
  expected_apr_pct: number;
  days_to_expiry: number;
  rationale: string;
  opened_at: string;
  status: string;
}

export interface TradeSignalItem {
  signal_id: string;
  market_id: string;
  event_title: string;
  question: string;
  strategy: StrategyType;
  side: string;
  order_type: string;
  entry_price: number;
  fair_value: number;
  edge_bps: number;
  expected_apr_pct: number;
  confidence_score: number;
  liquidity_usd: number;
  volume_24h_usd: number;
  spread: number;
  days_to_expiry: number;
  resolution_rules_len: number;
  rationale: string;
}

export interface RiskDecisionItem {
  signal_id: string;
  market_id: string;
  question: string;
  strategy: StrategyType;
  approved: boolean;
  recommended_size_usdc: number;
  shares_qty: number;
  entry_price: number;
  reject_reason: string;
  risk_checks_passed: string[];
}

export interface AiBrainLogItem {
  id: number;
  timestamp: string;
  event_type: string;
  market_id: string;
  headline: string;
  reasoning: string;
  verdict: string;
  impact_usdc: number;
}

export interface AutopilotState {
  generated_at: string;
  data_source: string;
  ai_summary: {
    timestamp?: string;
    ai_mode?: string;
    agy_cli_path?: string;
    regime?: string;
    capital_utilization_pct?: number;
    executive_summary?: string;
    account_router?: AccountRouterState;
  };
  config: {
    initial_capital_usdc: number;
    max_position_pct: number;
    max_total_exposure_pct: number;
    max_daily_drawdown_pct: number;
    min_liquidity_usd: number;
    max_spread_taker: number;
  };
  metrics: PortfolioMetrics;
  open_positions: OpenPosition[];
  pending_orders?: OpenPosition[];
  closed_positions: OpenPosition[];
  latest_signals: TradeSignalItem[];
  latest_decisions: RiskDecisionItem[];
  ai_brain_logs: AiBrainLogItem[];
  scanned_markets_count: number;
}
