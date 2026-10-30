"use client";

import React, {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import type { AutopilotState, StrategyType } from "@/types/autopilot";

export type FilterMode = "ALL" | StrategyType | "REJECTED";

export interface AutopilotContextValue {
  state: {
    data: AutopilotState;
    filterMode: FilterMode;
    customApiUrl: string;
    lastRefreshedAt: string;
    secondsToNextSync: number;
    liveClock: string;
    justUpdated: boolean;
    error: string | null;
  };
  actions: {
    setFilterMode: (mode: FilterMode) => void;
    setCustomApiUrl: (url: string) => void;
    runAiScanNow: () => void;
    switchArgonAccount: (slot: "account_1" | "account_2" | "failover") => void;
  };
  meta: {
    isPending: boolean;
    isPolling: boolean;
  };
}

const AutopilotContext = createContext<AutopilotContextValue | null>(null);

const STORAGE_KEY = "polymarket_autopilot_api_v1";
const POLL_INTERVAL_SECONDS = 5;

export function useAutopilot(): AutopilotContextValue {
  const ctx = use(AutopilotContext);
  if (!ctx) {
    throw new Error("useAutopilot must be used within an AutopilotProvider");
  }
  return ctx;
}

export function AutopilotProvider({
  initialData,
  children,
}: {
  initialData: AutopilotState;
  children: React.ReactNode;
}) {
  const [data, setData] = useState<AutopilotState>(initialData);
  const [filterMode, setFilterMode] = useState<FilterMode>("ALL");
  const [customApiUrl, setCustomApiUrlState] = useState<string>("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string>(
    initialData.generated_at
  );
  const [secondsToNextSync, setSecondsToNextSync] = useState<number>(
    POLL_INTERVAL_SECONDS
  );
  const [liveClock, setLiveClock] = useState<string>("--:--:--");
  const [justUpdated, setJustUpdated] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const requestGeneration = useRef(0);
  const latestTimestamp = useRef(initialData.generated_at);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        setCustomApiUrlState(saved);
      }
    } catch {
      // ignore storage errors
    }
  }, []);

  const triggerFlash = useCallback(() => {
    setJustUpdated(true);
    setTimeout(() => setJustUpdated(false), 900);
  }, []);

  const setCustomApiUrl = useCallback((url: string) => {
    const clean = url.trim().replace(/\/$/, "");
    if (clean) {
      try { const u = new URL(clean); if (!["http:", "https:"].includes(u.protocol)) throw new Error(); }
      catch { setError("URL backend phải bắt đầu bằng http:// hoặc https://"); return; }
    }
    requestGeneration.current += 1;
    setCustomApiUrlState(clean);
    try {
      localStorage.setItem(STORAGE_KEY, clean);
    } catch {
      // ignore storage errors
    }
  }, []);

  const fetchLatestState = useCallback(
    async (apiBase: string) => {
      if (inFlight.current) return;
      inFlight.current = true;
      const generation = requestGeneration.current;
      setIsPolling(true);
      try {
        const endpoint = apiBase ? `${apiBase}/api/state` : "/api/autopilot";
        const res = await fetch(endpoint, { cache: "no-store", signal: AbortSignal.timeout(10000) });
        if (!res.ok) throw new Error(`Không đọc được backend (HTTP ${res.status})`);
        const nextState = (await res.json()) as AutopilotState;
        if (!nextState.metrics || !Array.isArray(nextState.open_positions)) throw new Error("Dữ liệu backend không hợp lệ");
        if (generation !== requestGeneration.current) return;
        setError(null);
        setData(nextState);
        setLastRefreshedAt(nextState.generated_at);
        if (latestTimestamp.current !== nextState.generated_at) {
          latestTimestamp.current = nextState.generated_at;
          triggerFlash();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Mất kết nối backend");
      } finally {
        inFlight.current = false;
        setIsPolling(false);
        setSecondsToNextSync(POLL_INTERVAL_SECONDS);
      }
    },
    [triggerFlash]
  );

  // 1-second real-time heartbeat ticker
  useEffect(() => {
    const updateClock = () => {
      setLiveClock(
        new Date().toLocaleTimeString("vi-VN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      );
    };
    updateClock();

    const tick = setInterval(() => {
      updateClock();
      setSecondsToNextSync((prev) => prev <= 1 ? POLL_INTERVAL_SECONDS : prev - 1);
    }, 1000);
    const poll = setInterval(() => { void fetchLatestState(customApiUrl); }, POLL_INTERVAL_SECONDS * 1000);
    void fetchLatestState(customApiUrl);
    return () => { clearInterval(tick); clearInterval(poll); requestGeneration.current += 1; };
  }, [customApiUrl, fetchLatestState]);

  const runAiScanNow = useCallback(() => {
    if (inFlight.current) return;
    inFlight.current = true;
    startTransition(async () => {
      setIsPolling(true);
      try {
        const endpoint = customApiUrl ? `${customApiUrl}/api/scan` : "/api/autopilot";
        const res = await fetch(endpoint, {
          method: "POST",
          signal: AbortSignal.timeout(120000),
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "scan" }),
        });
        if (!res.ok) throw new Error((await res.json()).error || `HTTP ${res.status}`);
        if (res.ok) {
          setError(null);
          const updated = (await res.json()) as AutopilotState;
          setData(updated);
          setLastRefreshedAt(updated.generated_at);
          setSecondsToNextSync(POLL_INTERVAL_SECONDS);
          triggerFlash();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Không chạy được vòng quét");
      } finally {
        inFlight.current = false;
        setIsPolling(false);
      }
    });
  }, [customApiUrl, triggerFlash]);

  const switchArgonAccount = useCallback(() => {
    setError("Quản lý tài khoản bằng manage_accounts.py trên máy chạy backend.");
  }, []);

  const value = useMemo<AutopilotContextValue>(
    () => ({
      state: {
        data,
        filterMode,
        customApiUrl,
        lastRefreshedAt,
        secondsToNextSync,
        liveClock,
        justUpdated,
        error,
      },
      actions: {
        setFilterMode,
        setCustomApiUrl,
        runAiScanNow,
        switchArgonAccount,
      },
      meta: { isPending, isPolling },
    }),
    [
      data,
      filterMode,
      customApiUrl,
      lastRefreshedAt,
      secondsToNextSync,
      liveClock,
      justUpdated,
      error,
      setCustomApiUrl,
      runAiScanNow,
      switchArgonAccount,
      isPending,
      isPolling,
    ]
  );

  return <AutopilotContext value={value}>{children}</AutopilotContext>;
}
