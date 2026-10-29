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
      const markCents = ( parseFloat(match[1]) * 100 ).toFixed(1);
      const entryCents = ( parseFloat(match[2]) * 100 ).toFixed(1);
      return `Giá kèo đã tăng từ lúc mua ${entryCents} xu lên ${markCents} xu. Máy tự động bán thu hồi vốn gốc và đút túi +$${Math.abs(log.impact_usdc).toFixed(2)} tiền lãi vào két.`;
    }
    return `Giá đã tăng đạt mục tiêu. Máy tự động bán chốt lời và thu về +$${Math.abs(log.impact_usdc).toFixed(2)} tiền lãi thật.`;
  }

  if (log.verdict === "VETO_TRAP") {
    if (r.toLowerCase().includes("liquidity")) {
      return "Máy phát hiện kèo này có quá ít người mua bán (dưới mức an toàn $5,000). Đã chặn không mua để tránh bị kẹt vốn.";
    }
    if (r.toLowerCase().includes("spread")) {
      return "Chênh lệch giữa giá mua và giá bán trên sàn quá rộng. Máy tự động bỏ qua để không bị thiệt giá.";
    }
    return "Điều kiện kèo không đạt chuẩn an toàn của hệ thống kiểm soát rủi ro nên máy đã từ chối xuống tiền.";
  }

  if (log.verdict === "STRONG_BUY") {
    return `Kèo đạt chuẩn thanh khoản cao và luật phân xử rõ ràng. Máy đã tự động trích $${Math.abs(log.impact_usdc).toFixed(2)} từ két để mua vào.`;
  }

  return r;
}

function getVerdictStyle(verdict: string, impact: number) {
  switch (verdict) {
    case "TAKE_PROFIT":
      return {
        label: "Chốt lời thu tiền về",
        badgeClass: "bg-[#EDF3EC] text-[#346538]",
        dotClass: "bg-[#346538]",
        amountText: `+$${Math.abs(impact).toFixed(2)} lãi`,
        amountClass: "text-[#346538] font-semibold",
      };
    case "STRONG_BUY":
      return {
        label: "Mua vào kèo mới",
        badgeClass: "bg-[#E1F3FE] text-[#1F6C9F]",
        dotClass: "bg-[#1F6C9F]",
        amountText: `Đặt $${Math.abs(impact).toFixed(2)}`,
        amountClass: "text-[#111111] font-medium",
      };
    case "VETO_TRAP":
      return {
        label: "Né kèo bẫy rủi ro",
        badgeClass: "bg-[#FDEBEC] text-[#9F2F2D]",
        dotClass: "bg-[#9F2F2D]",
        amountText: "Đã giữ tiền",
        amountClass: "text-[#9F2F2D] font-medium",
      };
    default:
      return {
        label: "Kiểm tra định kỳ",
        badgeClass: "bg-[#F4F3EF] text-[#787774]",
        dotClass: "bg-[#787774]",
        amountText: "An toàn",
        amountClass: "text-[#787774]",
      };
  }
}

export function AiBrainFeed() {
  const { state } = useAutopilot();
  const { data } = state;
  const logs = (data.ai_brain_logs || []).slice(0, 10);

  return (
    <div className="rounded-[8px] border border-[#EAEAEA] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      {/* Header */}
      <div className="border-b border-[#EAEAEA] p-5 sm:px-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[16px] font-semibold tracking-[-0.01em] text-[#111111]">
              Nhật ký máy vừa tự làm gì
            </h2>
            <p className="mt-0.5 text-[13px] text-[#787774]">
              Mọi quyết định mua mới, chốt lời hay né bẫy đều được ghi lại rõ ràng
            </p>
          </div>
          <span className="rounded-[4px] bg-[#EDF3EC] px-2 py-0.5 text-[11px] font-medium text-[#346538]">
            Trực tiếp
          </span>
        </div>
      </div>

      {/* Plain-Vietnamese Daily Summary Box */}
      <div className="border-b border-[#EAEAEA] bg-[#FAF9F6] px-5 py-3.5 sm:px-6">
        <div className="text-[12px] font-medium text-[#111111]">
          Tình trạng vận hành hiện tại
        </div>
        <p className="mt-1 text-[12.5px] leading-relaxed text-[#787774]">
          Hệ thống đang duy trì chế độ bảo toàn vốn: giữ{" "}
          <strong className="font-medium text-[#111111]">
            ${data.metrics.cash_usdc.toFixed(2)}
          </strong>{" "}
          tiền mặt trong két, đồng thời tự động chốt lời ngay khi các kèo đang giữ tăng chạm đích.
        </p>
      </div>

      {/* Vertical Timeline List */}
      <div className="p-5 sm:px-6">
        {logs.length === 0 ? (
          <p className="py-6 text-center text-[13px] text-[#787774]">
            Chưa có nhật ký hoạt động nào.
          </p>
        ) : (
          <ol className="relative border-l border-[#EAEAEA] ml-2 space-y-5">
            {logs.map((log: AiBrainLogItem) => {
              const style = getVerdictStyle(log.verdict, log.impact_usdc);
              const { accountTag, title } = cleanHeadline(log.headline);
              const timeStr = (() => {
                try {
                  return new Date(log.timestamp).toLocaleTimeString("vi-VN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  });
                } catch {
                  return "";
                }
              })();

              return (
                <li key={log.id} className="ml-4">
                  <span
                    className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-white ${style.dotClass}`}
                  />

                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`rounded-[4px] px-2 py-0.5 text-[11px] font-medium ${style.badgeClass}`}
                      >
                        {style.label}
                      </span>
                      {accountTag && (
                        <span className="text-[11px] text-[#787774]">
                          • {accountTag}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 text-[12px] tabular-nums">
                      <span className={style.amountClass}>
                        {style.amountText}
                      </span>
                      {timeStr && (
                        <span className="text-[#787774]">{timeStr}</span>
                      )}
                    </div>
                  </div>

                  <h3 className="mt-1.5 text-[13.5px] font-medium leading-snug text-[#111111]">
                    {title}
                  </h3>

                  <p className="mt-1 text-[12.5px] leading-relaxed text-[#787774]">
                    {translateLogReasoning(log)}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
