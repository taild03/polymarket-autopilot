import { cache } from "react";
import { promises as fs } from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";
import type { AccountRouterState, AutopilotState } from "@/types/autopilot";
import fallbackSnapshot from "@/data/initial-state.json";

const execFileAsync = promisify(execFile);

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const STATE_FILE = path.join(PROJECT_ROOT, "data", "portfolio_state.json");
const ROUTER_FILE = path.join(PROJECT_ROOT, "data", "account_router_state.json");
const RUN_SCRIPT = path.join(PROJECT_ROOT, "run_autopilot.py");
const MANAGE_ACCOUNTS_SCRIPT = path.join(PROJECT_ROOT, "manage_accounts.py");

// In-memory state for serverless environments (e.g. Vercel) where local Python daemon is remote
let serverlessStateCache: AutopilotState = fallbackSnapshot as unknown as AutopilotState;

/**
 * Fetches live active markets from Polymarket Gamma API when running in a serverless
 * environment (e.g. Vercel) and marks open positions honestly to live bestBid prices.
 * Never fabricates synthetic profits.
 */
async function syncWithLiveGammaApiOnServerless(state: AutopilotState): Promise<AutopilotState> {
  try {
    const res = await fetch(
      "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=35",
      { cache: "no-store", signal: AbortSignal.timeout(8000) }
    );
    if (!res.ok) {
      return { ...state, data_source: "STALE_SNAPSHOT" };
    }
    const events = (await res.json()) as Array<{
      id?: string;
      title?: string;
      markets?: Array<{
        id?: string;
        question?: string;
        bestBid?: number | string;
        bestAsk?: number | string;
        outcomePrices?: string | number[];
      }>;
    }>;

    const livePriceMap = new Map<string, { bestBid: number; bestAsk: number }>();
    let scannedCount = 0;

    for (const ev of events) {
      for (const m of ev.markets ?? []) {
        if (!m.id) continue;
        scannedCount += 1;
        const rawBid = Number(m.bestBid ?? 0);
        const rawAsk = Number(m.bestAsk ?? 0);
        if (Number.isFinite(rawBid) && Number.isFinite(rawAsk) && rawBid >= 0 && rawAsk <= 1 && rawBid < rawAsk) {
          livePriceMap.set(String(m.id), {
            bestBid: rawBid,
            bestAsk: rawAsk,
          });
        }
      }
    }

    const updatedPositions = state.open_positions.map((pos) => {
      const live = livePriceMap.get(pos.market_id);
      if (!live || pos.side === "BUY_BUNDLE") return pos;
      const newMark =
        pos.side === "BUY_NO"
          ? Number(Math.max(0, 1 - live.bestAsk).toFixed(4))
          : Number(live.bestBid.toFixed(4));
      const mktVal = Number((pos.shares_qty * newMark).toFixed(2));
      const unrealized = Number((mktVal - pos.cost_basis_usdc).toFixed(2));
      return {
        ...pos,
        mark_price: newMark,
        market_value_usdc: mktVal,
        unrealized_pnl_usdc: unrealized,
      };
    });

    const openMarketVal = Number(
      updatedPositions.reduce((acc, p) => acc + p.market_value_usdc, 0).toFixed(2)
    );
    const unrealizedPnl = Number(
      updatedPositions.reduce((acc, p) => acc + p.unrealized_pnl_usdc, 0).toFixed(2)
    );
    const totalEquity = Number((state.metrics.cash_usdc + openMarketVal + (state.metrics.reserved_cash_usdc ?? 0)).toFixed(2));
    const totalPnl = Number((state.metrics.realized_pnl_usdc + unrealizedPnl).toFixed(2));
    const initialCap = state.metrics.initial_capital_usdc || 1000;

    return {
      ...state,
      generated_at: new Date().toISOString(),
      data_source: "GAMMA_QUOTE_REFRESH_ONLY",
      scanned_markets_count: scannedCount > 0 ? scannedCount : state.scanned_markets_count,
      open_positions: updatedPositions,
      metrics: {
        ...state.metrics,
        open_market_value_usdc: openMarketVal,
        unrealized_pnl_usdc: unrealizedPnl,
        total_pnl_usdc: totalPnl,
        total_equity_usdc: totalEquity,
        return_pct: Number(((totalPnl / initialCap) * 100).toFixed(2)),
      },
    };
  } catch {
    return { ...state, data_source: "STALE_SNAPSHOT" };
  }
}

export const getAutopilotServerState = cache(async (): Promise<AutopilotState> => {
  const [rawPortfolio, rawRouter] = await Promise.all([
    fs.readFile(STATE_FILE, "utf-8").catch(() => null),
    fs.readFile(ROUTER_FILE, "utf-8").catch(() => null),
  ]);

  if (!rawPortfolio) {
    serverlessStateCache = await syncWithLiveGammaApiOnServerless(serverlessStateCache);
    return serverlessStateCache;
  }

  const parsed = JSON.parse(rawPortfolio) as AutopilotState;
  if (rawRouter) {
    try {
      const routerState = JSON.parse(rawRouter) as AccountRouterState;
      parsed.ai_summary = {
        ...parsed.ai_summary,
        account_router: routerState,
      };
    } catch {
      // keep existing ai_summary
    }
  }
  serverlessStateCache = parsed;
  return parsed;
});

export async function triggerPythonCycle(): Promise<AutopilotState> {
  try {
    await execFileAsync("python3", [RUN_SCRIPT], { cwd: PROJECT_ROOT, timeout: 25000 });
    const [rawPortfolio, rawRouter] = await Promise.all([
      fs.readFile(STATE_FILE, "utf-8"),
      fs.readFile(ROUTER_FILE, "utf-8").catch(() => null),
    ]);
    const parsed = JSON.parse(rawPortfolio) as AutopilotState;
    if (rawRouter) {
      parsed.ai_summary = {
        ...parsed.ai_summary,
        account_router: JSON.parse(rawRouter) as AccountRouterState,
      };
    }
    serverlessStateCache = parsed;
    return parsed;
  } catch {
    // On Vercel Serverless without local Python runtime, sync open positions with live Polymarket Gamma API
    serverlessStateCache = await syncWithLiveGammaApiOnServerless(serverlessStateCache);
    return serverlessStateCache;
  }
}

export async function switchArgonAccountServer(
  mode: "account_1" | "account_2" | "failover"
): Promise<AutopilotState> {
  try {
    const args =
      mode === "failover"
        ? [MANAGE_ACCOUNTS_SCRIPT, "simulate-failover"]
        : [MANAGE_ACCOUNTS_SCRIPT, "switch", mode];

    await execFileAsync("python3", args, { cwd: PROJECT_ROOT, timeout: 15000 });
    return await triggerPythonCycle();
  } catch {
    throw new Error("Account switching requires the connected Python backend.");
  }
}
