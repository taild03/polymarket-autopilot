import { cache } from "react";
import { promises as fs } from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";
import type { AutopilotState, ScanStatus } from "@/types/autopilot";
import fallbackSnapshot from "@/data/initial-state.json";

const jobs = globalThis as typeof globalThis & { paperScan?: ScanStatus };
const execFileAsync = promisify(execFile);
const PROJECT_ROOT = process.env.AUTOPILOT_PROJECT_ROOT || path.resolve(process.cwd(), "..");
const DATA_DIR = process.env.AUTOPILOT_DATA_DIR || path.join(PROJECT_ROOT, "data");
const STATE_FILE = path.join(DATA_DIR, "portfolio_state.json");
const RUN_SCRIPT = path.join(PROJECT_ROOT, "run_autopilot.py");
const BACKEND_URL = process.env.AUTOPILOT_BACKEND_URL?.replace(/\/$/, "");
const localControl = !process.env.VERCEL && process.env.AUTOPILOT_ENABLE_LOCAL_CONTROL === "1";

async function backendRequest(route: string): Promise<AutopilotState> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.AUTOPILOT_API_TOKEN) headers.Authorization = `Bearer ${process.env.AUTOPILOT_API_TOKEN}`;
  const res = await fetch(`${BACKEND_URL}${route}`, {
    headers, cache: "no-store", signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`Backend unavailable (${res.status})`);
  const state = await res.json() as AutopilotState;
  if (!state.metrics || !Array.isArray(state.open_positions)) throw new Error("Invalid backend state");
  return { ...state, runtime: { mode: "paper", can_scan: !process.env.VERCEL, can_switch_accounts: false } };
}

export const getAutopilotServerState = cache(async (): Promise<AutopilotState> => {
  if (BACKEND_URL) {
    try { return await backendRequest("/api/state"); }
    catch {
      return { ...fallbackSnapshot, data_source: "BACKEND_UNAVAILABLE", runtime: { mode: "snapshot", can_scan: false, can_switch_accounts: false } } as unknown as AutopilotState;
    }
  }
  try {
    const state = JSON.parse(await fs.readFile(STATE_FILE, "utf-8")) as AutopilotState;
    return { ...state, scan_status: jobs.paperScan, runtime: { mode: "paper", can_scan: localControl, can_switch_accounts: false } };
  } catch {
    return { ...fallbackSnapshot, data_source: "READONLY_SNAPSHOT", runtime: { mode: "snapshot", can_scan: false, can_switch_accounts: false } } as unknown as AutopilotState;
  }
});

export async function triggerPythonCycle(): Promise<{ scan_status: ScanStatus }> {
  if (BACKEND_URL) {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (process.env.AUTOPILOT_API_TOKEN) headers.Authorization = `Bearer ${process.env.AUTOPILOT_API_TOKEN}`;
    const response = await fetch(`${BACKEND_URL}/api/scan`, {
      method: "POST", headers, body: JSON.stringify({ action: "scan_async" }),
      cache: "no-store", signal: AbortSignal.timeout(8000),
    });
    if (response.status !== 202) throw new Error("Backend did not accept async scan");
    return await response.json();
  }
  if (!localControl) throw new Error("Read-only dashboard");
  if (jobs.paperScan?.phase !== "running") {
    const status: ScanStatus = { phase: "running", started_at: Date.now() / 1000 };
    jobs.paperScan = status;
    void execFileAsync(process.env.AUTOPILOT_PYTHON || "python3", [RUN_SCRIPT], { cwd: PROJECT_ROOT })
      .then(() => { status.phase = "completed"; }, () => { status.phase = "failed"; });
  }
  return { scan_status: jobs.paperScan! };
}
