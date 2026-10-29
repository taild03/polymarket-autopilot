"use client";

import React, {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
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
    setCustomApiUrlState(clean);
    try {
      localStorage.setItem(STORAGE_KEY, clean);
    } catch {
      // ignore storage errors
    }
  }, []);

  const fetchLatestState = useCallback(
    async (apiBase: string) => {
      setIsPolling(true);
      try {
        const endpoint = apiBase ? `${apiBase}/api/state` : "/api/autopilot";
        const res = await fetch(endpoint, { cache: "no-store" });
        if (!res.ok) return;
        const nextState = (await res.json()) as AutopilotState;
        setData(nextState);
        setLastRefreshedAt(new Date().toISOString());
        triggerFlash();
      } catch {
        // keep previous state if network glitch occurs
      } finally {
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
      setSecondsToNextSync((prev) => {
        if (prev <= 1) {
          void fetchLatestState(customApiUrl);
          return POLL_INTERVAL_SECONDS;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(tick);
  }, [customApiUrl, fetchLatestState]);

  const runAiScanNow = useCallback(() => {
    startTransition(async () => {
      setIsPolling(true);
      try {
        const endpoint = customApiUrl ? `${customApiUrl}/api/scan` : "/api/autopilot";
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "scan" }),
        });
        if (res.ok) {
          const updated = (await res.json()) as AutopilotState;
          setData(updated);
          setLastRefreshedAt(new Date().toISOString());
          setSecondsToNextSync(POLL_INTERVAL_SECONDS);
          triggerFlash();
        }
      } catch {
        // ignore error
      } finally {
        setIsPolling(false);
      }
    });
  }, [customApiUrl, triggerFlash]);

  const switchArgonAccount = useCallback(
    (slot: "account_1" | "account_2" | "failover") => {
      startTransition(async () => {
        setIsPolling(true);
        try {
          const endpoint = customApiUrl
            ? `${customApiUrl}/api/switch-account`
            : "/api/autopilot";
          const res = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "switch_account", slot }),
          });
          if (res.ok) {
            const updated = (await res.json()) as AutopilotState;
            setData(updated);
            setLastRefreshedAt(new Date().toISOString());
            setSecondsToNextSync(POLL_INTERVAL_SECONDS);
            triggerFlash();
          }
        } catch {
          // ignore error
        } finally {
          setIsPolling(false);
        }
      });
    },
    [customApiUrl, triggerFlash]
  );

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
      setCustomApiUrl,
      runAiScanNow,
      switchArgonAccount,
      isPending,
      isPolling,
    ]
  );

  return <AutopilotContext value={value}>{children}</AutopilotContext>;
}
