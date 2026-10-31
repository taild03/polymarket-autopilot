"use client";

import React from "react";
import { useAutopilot } from "./autopilot-provider";
import type { EntryReviewItem } from "@/types/autopilot";

// Truthful labels for each terminal entry-review status. Only APPROVE opens a trade; every
// other status (including UNAVAILABLE) blocks new entries. We never imply an inference
// happened when the gate only reported availability.
function statusMeta(status: string): { label: string; cardBg: string; badgeBg: string } {
  switch (status) {
    case "APPROVE":
      return { label: "ARGON DUYỆT VÀO LỆNH", cardBg: "bg-[#B8F397]", badgeBg: "bg-[#111111] text-[#B8F397]" };
    case "REJECT":
      return { label: "ARGON TỪ CHỐI", cardBg: "bg-[#FFD6D6]", badgeBg: "bg-[#FF3B30] text-white" };
    case "INSUFFICIENT_DATA":
      return { label: "THIẾU BẰNG CHỨNG — KHÔNG VÀO", cardBg: "bg-[#FFE8C2]", badgeBg: "bg-[#111111] text-white" };
    default:
      return { label: "ARGON KHÔNG SẴN SÀNG — KHÓA LỆNH", cardBg: "bg-[#EDEDED]", badgeBg: "bg-[#52514E] text-white" };
  }
}

export function EntryReviewStatus() {
  const { state } = useAutopilot();
  const er = state.data.entry_review;
  if (!er) return null;

  const required = er.mode === "ARGON_REQUIRED";
  const reviews = (er.reviews || []).slice(0, 6);

  return (
    <section className="rounded-[20px] border-2 border-[#111111] bg-white p-6 shadow-[6px_6px_0px_#111111] sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-[20px] font-bold uppercase tracking-[-0.02em] text-[#111111] sm:text-[24px]">
            CỔNG KIỂM DUYỆT ARGON TRƯỚC KHI VÀO LỆNH
          </h2>
          <p className="mt-1 text-[15px] font-semibold text-[#52514E]">
            Mặc định: mọi lệnh mua mới phải được Argon ({er.model}) đánh giá thật và DUYỆT thì mới được giữ chỗ hay xuống tiền.
            Thoát lệnh dùng quy tắc xác định, không phải suy luận AI.
          </p>
        </div>
        <span
          className={`rounded-[8px] border-2 border-[#111111] px-3 py-1.5 text-[12px] font-extrabold uppercase ${
            required ? "bg-[#B8F397] text-[#111111]" : "bg-[#FFD166] text-[#111111]"
          }`}
        >
          {required ? "BẮT BUỘC ARGON" : "CHẾ ĐỘ XÁC ĐỊNH (TEST)"}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="CLI ARGON" value={er.cli_available ? "ĐÃ TÌM THẤY" : "KHÔNG TÌM THẤY"} warn={!er.cli_available} />
        <Stat label="LẦN GỌI CHU KỲ" value={`${er.calls_made ?? 0}/${er.max_calls_per_cycle ?? 0}`} />
        <Stat label="DUYỆT / CHẶN" value={`${er.approved_count ?? 0} / ${er.blocked_count ?? 0}`} />
        <Stat
          label="HOÀN TIỀN LỆNH CHỜ"
          value={`${(er.legacy_pending_refunded ?? 0) + (er.expired_pending_refunded ?? 0)}`}
        />
      </div>

      <div className="mt-5 space-y-3">
        {reviews.length === 0 ? (
          <p className="rounded-[10px] border-2 border-[#111111] bg-[#F4F0EA] p-3 text-[14px] font-bold text-[#111111]">
            Chu kỳ này không có lệnh mới nào được đưa qua Argon.
          </p>
        ) : (
          reviews.map((r: EntryReviewItem, i: number) => {
            const meta = statusMeta(r.status);
            return (
              <div
                key={`${r.timestamp}-${i}`}
                className={`rounded-[12px] border-2 border-[#111111] p-3.5 shadow-[3px_3px_0px_#111111] ${meta.cardBg}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className={`rounded-[6px] px-2.5 py-1 text-[12px] font-extrabold uppercase ${meta.badgeBg}`}>
                    {meta.label}
                  </span>
                  <span className="text-[12px] font-extrabold uppercase text-[#111111]">
                    {r.account_slot || "—"} • {r.model}
                    {r.cache_hit ? " • CACHE" : ""}
                  </span>
                </div>
                <p className="mt-2 text-[14px] font-semibold leading-relaxed text-[#111111]">
                  {r.question && <strong className="block">{r.question} · {r.chosen_side}</strong>}
                  {r.reasoning || r.reject_reason || "—"}
                </p>
                {r.risks && r.risks.length > 0 && (
                  <p className="mt-1.5 text-[13px] font-bold text-[#111111]/80">Rủi ro: {r.risks.join("; ")}</p>
                )}
              </div>
            );
          })
        )}
      </div>

      <p className="mt-4 text-[13px] font-semibold text-[#52514E]">
        Chưa nối nguồn tin tức/nghiên cứu độc lập: khi không đủ bằng chứng, Argon trả &quot;thiếu bằng chứng&quot; và hệ thống
        không vào lệnh. Số liệu lịch sử trước khi có cổng này không được coi là đã qua kiểm duyệt AI.
      </p>
    </section>
  );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div
      className={`rounded-[10px] border-2 border-[#111111] p-3 ${warn ? "bg-[#FFD6D6]" : "bg-[#FAF8F5]"}`}
    >
      <span className="block text-[11px] font-extrabold uppercase text-[#52514E]">{label}</span>
      <span className="mt-1 block font-mono text-[16px] font-extrabold text-[#111111] tabular-nums">{value}</span>
    </div>
  );
}
