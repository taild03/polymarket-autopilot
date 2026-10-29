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
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string>(initialData.generated_at);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        setCustomApiUrlState(saved);
      }
    } catch {
      // ignore storage errors in restricted environments
    }
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

  const fetchLatestState = useCallback(async (apiBase: string) => {
    setIsPolling(true);
    try {
      const endpoint = apiBase ? `${apiBase}/api/state` : "/api/autopilot";
      const res = await fetch(endpoint, { cache: "no-store" });
      if (!res.ok) return;
      const nextState = (await res.json()) as AutopilotState;
      setData(nextState);
      setLastRefreshedAt(new Date().toISOString());
    } catch {
      // keep previous state if transient network glitch occurs
    } finally {
      setIsPolling(false);
    }
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      void fetchLatestState(customApiUrl);
    }, 5000);
    return () => clearInterval(timer);
  }, [customApiUrl, fetchLatestState]);

  const runAiScanNow = useCallback(() => {
    startTransition(async () => {
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
        }
      } catch {
        // ignore error
      }
    });
  }, [customApiUrl]);

  const switchArgonAccount = useCallback(
    (slot: "account_1" | "account_2" | "failover") => {
      startTransition(async () => {
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
          }
        } catch {
          // ignore error
        }
      });
    },
    [customApiUrl]
  );

  const value = useMemo<AutopilotContextValue>(
    () => ({
      state: { data, filterMode, customApiUrl, lastRefreshedAt },
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
      setCustomApiUrl,
      runAiScanNow,
      switchArgonAccount,
      isPending,
      isPolling,
    ]
  );

  return <AutopilotContext value={value}>{children}</AutopilotContext>;
}
