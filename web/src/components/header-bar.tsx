"use client";

import React from "react";
import { useAutopilot } from "./autopilot-provider";

export function HeaderBar() {
  const { state, actions, meta } = useAutopilot();
  const { data, lastRefreshedAt } = state;

  const router = data.ai_summary?.account_router;
  const activeSlot = router?.active_slot ?? "account_1";
  const activeAccount = router?.accounts?.[activeSlot];
  const accountName =
    activeSlot === "account_1" ? "Nick Google #1" : "Nick Google #2";

  const formattedTime = React.useMemo(() => {
    try {
      const date = new Date(lastRefreshedAt || data.generated_at);
      return date.toLocaleTimeString("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return "--:--:--";
    }
  }, [lastRefreshedAt, data.generated_at]);

  return (
    <header className="sticky top-0 z-30 border-b border-[#EAEAEA] bg-[#F7F6F3]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1200px] items-center justify-between px-4 py-3.5 sm:px-8">
        {/* Left: Brand Identity */}
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-[6px] border border-[#111111] bg-[#111111] text-white">
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
              <polyline points="16 7 22 7 22 13" />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[15px] font-semibold tracking-[-0.02em] text-[#111111]">
                Sổ Đầu Tư Polymarket
              </span>
              <span className="rounded-[4px] bg-[#EDF3EC] px-2 py-0.5 text-[11px] font-medium text-[#346538]">
                Tự hành 24/7
              </span>
            </div>
            <p className="text-[12px] text-[#787774]">
              Máy tự tìm kèo chênh lệch giá và tự chốt lời về két cho bạn
            </p>
          </div>
        </div>

        {/* Right: Plain status + Primary Action */}
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-[6px] border border-[#EAEAEA] bg-white px-3 py-1.5 text-[12px] text-[#787774] md:flex">
            <span
              className={`h-2 w-2 rounded-full ${
                meta.isPolling
                  ? "bg-[#956400] animate-pulse"
                  : "bg-[#346538]"
              }`}
            />
            <span className="font-medium text-[#111111]">{accountName}</span>
            <span className="text-[#D4D4D0]">|</span>
            <span>
              {activeAccount?.model_tier
                ? "Đang trực chiến"
                : "Sẵn sàng"}
            </span>
            <span className="text-[#D4D4D0]">|</span>
            <span className="tabular-nums">Cập nhật {formattedTime}</span>
          </div>

          <button
            type="button"
            onClick={actions.runAiScanNow}
            disabled={meta.isPending}
            className="inline-flex items-center gap-2 rounded-[6px] bg-[#111111] px-3.5 py-2 text-[13px] font-medium text-white transition-colors hover:bg-[#2C2C2B] active:scale-[0.99] disabled:opacity-50 cursor-pointer"
          >
            <svg
              className={`h-3.5 w-3.5 ${meta.isPending ? "animate-spin" : ""}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
            </svg>
            <span>{meta.isPending ? "Đang quét thị trường..." : "Quét kèo ngay"}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
