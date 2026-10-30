"use client";

import React from "react";
import { useAutopilot } from "./autopilot-provider";

export function HeaderBar() {
  const { state, actions, meta } = useAutopilot();
  const { data, secondsToNextSync, liveClock, justUpdated } = state;
  const m = data.metrics;

  const router = data.ai_summary?.account_router;
  const activeSlot = router?.active_slot ?? "account_1";
  const activeAccount = router?.accounts?.[activeSlot];
  const accountLabel =
    activeAccount?.label ||
    (activeSlot === "account_1"
      ? "Nick Google #1 (leductai21204@gmail.com)"
      : "Nick Google #2 (taoyeumaygianga@gmail.com)");

  const stale = !data.generated_at || Date.now() - Date.parse(data.generated_at) > 120000;
  const live = data.data_source === "LIVE_POLYMARKET_GAMMA_API" && !stale && !state.error;
  const progressPct = ((5 - secondsToNextSync) / 5) * 100;

  return (
    <header className="sticky top-0 z-30 border-b-2 border-[#111111] bg-[#F4F0EA]">
      {/* 1. Real-Time Live Telemetry Strip (High-Contrast Black Bar) */}
      <div className="border-b-2 border-[#111111] bg-[#111111] px-4 py-2.5 text-white sm:px-8">
        <div className="mx-auto flex max-w-[1360px] flex-wrap items-center justify-between gap-3">
          {/* Left: Live Radar + Cycle + Ticking Clock */}
          <div className="flex flex-wrap items-center gap-3 sm:gap-4">
            <div className="inline-flex items-center gap-2 rounded-full bg-[#1E2923] px-3 py-1 border border-[#B8F397]/40">
              <span className="h-3 w-3 rounded-full bg-[#22C55E] live-beacon" />
              <span className="text-[13px] font-bold uppercase tracking-[0.04em] text-[#B8F397]">
                {meta.isPolling || justUpdated
                  ? "ĐANG CẬP NHẬT DỮ LIỆU..."
                  : live ? "DỮ LIỆU LIVE · PAPER TRADING" : "DỮ LIỆU CŨ / CHỈ XEM"}
              </span>
            </div>

            <div className="flex items-center gap-2 text-[14px] sm:text-[15px] font-bold tabular-nums">
              <span className="rounded-[6px] bg-white/15 px-2.5 py-0.5 text-white">
                VÒNG QUÉT #{m.cycle_count}
              </span>
              <span className="text-white/40">•</span>
              <span
                className={`rounded-[6px] px-2.5 py-0.5 text-[12px] font-extrabold uppercase ${
                  live
                    ? "bg-[#B8F397]/20 text-[#B8F397]"
                    : "bg-[#FFD166]/20 text-[#FFD166]"
                }`}
              >
                {live
                  ? `POLYMARKET LIVE (${data.scanned_markets_count} KÈO)`
                  : "CHẾ ĐỘ SNAPSHOT (TẠM KHÓA VÀO LỆNH)"}
              </span>
              <span className="text-white/40">•</span>
              <span className="font-mono text-[#FFD166]">{liveClock}</span>
            </div>
          </div>

          {/* Right: 5-Second Countdown Bar + Active Google Argon Account */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2.5">
              <span className="text-[13px] font-semibold text-white/80 tabular-nums">
                Tự làm mới sau:{" "}
                <strong className="text-[15px] font-extrabold text-white">
                  {secondsToNextSync}s
                </strong>
              </span>
              <div className="h-2.5 w-24 overflow-hidden rounded-full bg-white/20 p-0.5">
                <div
                  className="h-full rounded-full bg-[#B8F397] transition-all duration-500"
                  style={{ width: `${Math.max(15, progressPct)}%` }}
                />
              </div>
            </div>

            <div className="hidden items-center gap-2 rounded-[6px] bg-white/10 px-3 py-1 text-[13px] font-bold text-[#B8F397] lg:flex">
              <span>AI ĐANG TRỰC:</span>
              <span className="text-white">{accountLabel}</span>
            </div>
          </div>
        </div>
      </div>

      {state.error && <p role="alert" className="bg-[#FFD6D6] px-4 py-3 font-semibold">{state.error}</p>}
      {(!live) && <p className="px-4 py-2 text-sm">Nguồn: {data.data_source}. Lần ghi dữ liệu: {data.generated_at || "chưa có"}.</p>}
      {/* 2. Main Oversized MetaMask-Style Brand & Action Bar */}
      <div className="mx-auto flex max-w-[1360px] flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-8">
        <div className="flex items-center gap-3.5">
          <div className="flex h-12 w-12 items-center justify-center rounded-[12px] border-2 border-[#111111] bg-[#FF5C16] text-white shadow-[3px_3px_0px_#111111]">
            <svg
              className="h-6 w-6"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
              <polyline points="16 7 22 7 22 13" />
            </svg>
          </div>
          <div>
            <h1 className="font-display text-[22px] font-bold uppercase leading-none tracking-[-0.03em] text-[#111111] sm:text-[28px]">
              SỔ ĐẦU TƯ POLYMARKET
            </h1>
            <p className="mt-1 text-[14px] font-semibold text-[#52514E] sm:text-[15px]">
              Mô phỏng giao dịch • Không gửi lệnh tiền thật
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={actions.runAiScanNow}
          disabled={meta.isPending || meta.isPolling || data.runtime?.can_scan === false}
          className="inline-flex items-center gap-2.5 rounded-[12px] border-2 border-[#111111] bg-[#FF5C16] px-5 py-3 text-[15px] font-extrabold uppercase tracking-[0.02em] text-white shadow-[4px_4px_0px_#111111] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:bg-[#E04809] hover:shadow-[2px_2px_0px_#111111] active:translate-x-[3px] active:translate-y-[3px] active:shadow-none disabled:opacity-60 cursor-pointer sm:text-[16px]"
        >
          <svg
            className={`h-5 w-5 ${meta.isPending || meta.isPolling ? "animate-spin" : ""}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
          </svg>
          <span>
            {meta.isPending ? "ĐANG QUÉT THỊ TRƯỜNG..." : "QUÉT KÈO NGAY BÂY GIỜ"}
          </span>
        </button>
      </div>
    </header>
  );
}
