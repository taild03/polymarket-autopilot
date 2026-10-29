import { cache } from "react";
import { promises as fs } from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";
import type { AccountRouterState, AutopilotState } from "@/types/autopilot";

const execFileAsync = promisify(execFile);

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const STATE_FILE = path.join(PROJECT_ROOT, "data", "portfolio_state.json");
const ROUTER_FILE = path.join(PROJECT_ROOT, "data", "account_router_state.json");
const RUN_SCRIPT = path.join(PROJECT_ROOT, "run_autopilot.py");
const MANAGE_ACCOUNTS_SCRIPT = path.join(PROJECT_ROOT, "manage_accounts.py");

/**
 * Per-request deduplicated loader using React.cache() (`server-cache-react`)
 * and `Promise.all()` (`async-parallel`) to eliminate I/O waterfalls.
 */
export const getAutopilotServerState = cache(async (): Promise<AutopilotState> => {
  const [rawPortfolio, rawRouter] = await Promise.all([
    fs.readFile(STATE_FILE, "utf-8").catch(() => null),
    fs.readFile(ROUTER_FILE, "utf-8").catch(() => null),
  ]);

  if (!rawPortfolio) {
    await triggerPythonCycle();
    const freshPortfolio = await fs.readFile(STATE_FILE, "utf-8");
    return JSON.parse(freshPortfolio) as AutopilotState;
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
  return parsed;
});

export async function triggerPythonCycle(): Promise<AutopilotState> {
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
  return parsed;
}

export async function switchArgonAccountServer(
  mode: "account_1" | "account_2" | "failover"
): Promise<AutopilotState> {
  const args =
    mode === "failover"
      ? [MANAGE_ACCOUNTS_SCRIPT, "simulate-failover"]
      : [MANAGE_ACCOUNTS_SCRIPT, "switch", mode];

  await execFileAsync("python3", args, { cwd: PROJECT_ROOT, timeout: 15000 });
  return triggerPythonCycle();
}
