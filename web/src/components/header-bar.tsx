"use client";

import React, { useState } from "react";
import { Activity, Play, RefreshCw, Server } from "lucide-react";
import { useAutopilot } from "@/components/autopilot-provider";

export function HeaderBar() {
  const { state, actions, meta } = useAutopilot();
  const [urlInput, setUrlInput] = useState<string>(state.customApiUrl);

  const cycleCount = state.data.metrics.cycle_count ?? 1;
  const aiMode = state.data.ai_summary?.ai_mode ?? "AGY_CLI_AGENT";
  const executiveNote =
    state.data.ai_summary?.executive_summary ??
    "Hệ thống AI tự hành 24/7 đang quét Polymarket và tự động chốt lời.";

  return (
    <header className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="inline-flex h-3 w-3 rounded-full bg-emerald-400 animate-pulse" />
          <h1 className="text-xl font-bold tracking-tight text-slate-100">
            Polymarket AI Autopilot
          </h1>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            {aiMode} • CYCLE #{cycleCount}
          </span>
          {meta.isPolling ? (
            <span className="inline-flex items-center gap-1 text-xs text-slate-400">
              <RefreshCw className="w-3 h-3 animate-spin" />
              Live Sync
            </span>
          ) : null}
        </div>
        <p className="text-slate-400 text-sm max-w-3xl">{executiveNote}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2.5">
        <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 gap-2">
          <Server className="w-3.5 h-3.5 text-slate-400" />
          <input
            type="text"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="Backend API (mặc định: Next API)"
            aria-label="Backend API URL"
            className="bg-transparent text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none w-48"
          />
          <button
            type="button"
            onClick={() => actions.setCustomApiUrl(urlInput)}
            className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 cursor-pointer"
          >
            Lưu
          </button>
        </div>

        <button
          type="button"
          disabled={meta.isPending}
          onClick={actions.runAiScanNow}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500 hover:bg-emerald-400 text-slate-950 transition disabled:opacity-50 cursor-pointer"
        >
          {meta.isPending ? (
            <Activity className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current" />
          )}
          <span>{meta.isPending ? "Đang chạy chu kỳ AI..." : "Quét & Giao dịch Ngay"}</span>
        </button>
      </div>
    </header>
  );
}
