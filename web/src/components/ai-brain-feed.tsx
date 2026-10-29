"use client";

import React from "react";
import { useAutopilot } from "./autopilot-provider";
import type { AiBrainLogItem } from "@/types/autopilot";

function cleanHeadline(raw: string): { accountTag: string | null; title: string } {
  const match = raw.match(/^\[(.*?)\]\s*(.*)$/);
  if (match) {
    const rawTag = match[1].replace(/\s*\(Chính\)|\s*\(Dự phòng\)/g, "").trim();
    return { accountTag: rawTag, title: match[2] };
  }
  return { accountTag: null, title: raw };
}

function translateLogReasoning(log: AiBrainLogItem): string {
  const r = log.reasoning || "";
  if (log.verdict === "TAKE_PROFIT") {
    const match = r.match(/mark=([0-9.]+)\s+vs\s+entry=([0-9.]+)/i);
    if (match) {
      const markCents = (parseFloat(match[1]) * 100).toFixed(1);
      const entryCents = (parseFloat(match[2]) * 100).toFixed(1);
      return `Giá tăng từ lúc mua ${entryCents}¢ lên ${markCents}¢. Máy tự bán thu hồi vốn gốc và bỏ két +$${Math.abs(log.impact_usdc).toFixed(2)} tiền lãi thật.`;
    }
    return `Giá chạm mục tiêu chốt lời. Máy tự động bán thu về +$${Math.abs(log.impact_usdc).toFixed(2)} tiền lãi thật.`;
  }

  if (log.verdict === "VETO_TRAP") {
    if (r.toLowerCase().includes("liquidity")) {
      return "Phát hiện thanh khoản quá mỏng (dưới $5,000). Đã chặn mua để không bị kẹt vốn.";
    }
    if (r.toLowerCase().includes("spread")) {
      return "Chênh lệch giá mua và bán quá rộng. Máy bỏ qua để không bị thiệt giá.";
    }
    return "Kèo không đạt chuẩn an toàn nên máy đã từ chối xuống tiền.";
  }

  if (log.verdict === "STRONG_BUY") {
    return `Kèo đạt chuẩn thanh khoản lớn và luật chơi rõ ràng. Máy tự trích $${Math.abs(log.impact_usdc).toFixed(2)} từ két để vào lệnh.`;
  }

  return r;
}

function getVerdictStyle(verdict: string, impact: number) {
  switch (verdict) {
    case "TAKE_PROFIT":
      return {
        label: "ĐÃ CHỐT LỜI VỀ KÉT",
        cardBg: "bg-[#B8F397]",
        badgeBg: "bg-[#111111] text-[#B8F397]",
        amountText: `+$${Math.abs(impact).toFixed(2)} LÃI`,
      };
    case "STRONG_BUY":
      return {
        label: "MUA VÀO KÈO MỚI",
        cardBg: "bg-[#D8E6FF]",
        badgeBg: "bg-[#111111] text-white",
        amountText: `ĐẶT $${Math.abs(impact).toFixed(2)}`,
      };
    case "VETO_TRAP":
      return {
        label: "ĐÃ CHẶN KÈO BẪY",
        cardBg: "bg-[#FFD6D6]",
        badgeBg: "bg-[#FF3B30] text-white",
        amountText: "GIỮ TIỀN",
      };
    default:
      return {
        label: "QUÉT ĐỊNH KỲ",
        cardBg: "bg-[#FAF8F5]",
        badgeBg: "bg-[#111111] text-white",
        amountText: "AN TOÀN",
      };
  }
}

export function AiBrainFeed() {
  const { state } = useAutopilot();
  const { data, secondsToNextSync } = state;
  const logs = (data.ai_brain_logs || []).slice(0, 8);

  return (
    <div className="rounded-[20px] border-2 border-[#111111] bg-white p-5 shadow-[6px_6px_0px_#111111] sm:p-7">
      {/* Header */}
      <div className="border-b-2 border-[#111111] pb-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-display text-[22px] font-bold uppercase tracking-[-0.02em] text-[#111111] sm:text-[26px]">
            NHẬT KÝ MÁY VỪA TỰ LÀM
          </h2>
          <span className="inline-flex items-center gap-1.5 rounded-[8px] border-2 border-[#111111] bg-[#111111] px-3 py-1 text-[12px] font-extrabold uppercase text-[#B8F397] tabular-nums">
            <span className="h-2.5 w-2.5 rounded-full bg-[#22C55E] live-beacon" />
            <span>{secondsToNextSync}s</span>
          </span>
        </div>
        <p className="mt-1 text-[15px] font-semibold text-[#52514E]">
          Cập nhật liên tục từng giây mọi lệnh chốt lời, mua mới và né bẫy
        </p>
      </div>

      {/* Activity Cards Stream */}
      <div className="mt-5 space-y-4">
        {logs.length === 0 ? (
          <p className="py-6 text-center text-[16px] font-bold text-[#52514E]">
            Chưa có nhật ký hoạt động nào.
          </p>
        ) : (
          logs.map((log: AiBrainLogItem) => {
            const style = getVerdictStyle(log.verdict, log.impact_usdc);
            const { title } = cleanHeadline(log.headline);
            const timeStr = (() => {
              try {
                return new Date(log.timestamp).toLocaleTimeString("vi-VN", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                });
              } catch {
                return "";
              }
            })();

            return (
              <div
                key={log.id}
                className={`rounded-[14px] border-2 border-[#111111] p-4 shadow-[3px_3px_0px_#111111] ${style.cardBg}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span
                    className={`rounded-[6px] px-2.5 py-1 text-[12px] font-extrabold uppercase ${style.badgeBg}`}
                  >
                    {style.label}
                  </span>

                  <div className="flex items-center gap-2 tabular-nums">
                    <span className="rounded-[6px] border-2 border-[#111111] bg-white px-2.5 py-0.5 text-[15px] font-extrabold text-[#111111]">
                      {style.amountText}
                    </span>
                    {timeStr && (
                      <span className="font-mono text-[12px] font-bold text-[#111111]">
                        {timeStr}
                      </span>
                    )}
                  </div>
                </div>

                <h3 className="mt-2.5 text-[17px] font-extrabold leading-snug text-[#111111]">
                  {title}
                </h3>

                <p className="mt-1.5 text-[14.5px] font-semibold leading-relaxed text-[#111111]/85">
                  {translateLogReasoning(log)}
                </p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
