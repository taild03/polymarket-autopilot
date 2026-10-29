"use client";

import React from "react";
import { BrainCircuit } from "lucide-react";
import { useAutopilot } from "@/components/autopilot-provider";

export function AiBrainFeed() {
  const { state } = useAutopilot();
  const logs = state.data.ai_brain_logs ?? [];

  return (
    <section className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-4 h-4 text-emerald-400" />
            <h2 className="text-base font-semibold text-slate-100">
              Live AI Brain Feed — Nhật Ký Suy Luận & Quyết Định Tự Hành
            </h2>
          </div>
          <p className="text-xs text-slate-400">
            Ghi nhận trực tiếp từ SQLite Ledger: Kiểm toán luật phân xử UMA Oracle, phủ quyết bẫy (Veto) và tự động chốt lời (Take-Profit)
          </p>
        </div>
        <span className="px-2.5 py-1 rounded-lg text-xs font-mono bg-slate-950 border border-slate-800 text-slate-300">
          Hiển thị {Math.min(6, logs.length)} quyết định gần nhất
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        {logs.slice(0, 6).map((item) => {
          const isVeto = item.verdict === "VETO_TRAP";
          const isTakeProfit = item.verdict === "TAKE_PROFIT";

          const cardStyle = isVeto
            ? "border-rose-500/40 bg-rose-500/5"
            : isTakeProfit
              ? "border-emerald-500/40 bg-emerald-500/5"
              : "border-slate-800 bg-slate-950/70";

          const badgeStyle = isVeto
            ? "bg-rose-500/20 text-rose-300"
            : isTakeProfit
              ? "bg-emerald-500/20 text-emerald-300"
              : "bg-indigo-500/20 text-indigo-300";

          return (
            <div key={item.id} className={`p-3.5 rounded-xl border ${cardStyle} space-y-1.5`}>
              <div className="flex items-center justify-between gap-2">
                <span className={`px-2 py-0.5 rounded font-semibold ${badgeStyle}`}>
                  {item.verdict}
                </span>
                <span className="font-mono font-semibold text-slate-200">
                  {isTakeProfit
                    ? `+$${item.impact_usdc.toFixed(2)} USDC`
                    : isVeto
                      ? "CHẶN BẪY ($0.00)"
                      : `Size: $${item.impact_usdc.toFixed(2)}`}
                </span>
              </div>
              <div className="font-semibold text-slate-100">{item.headline}</div>
              <div className="text-slate-400 leading-relaxed">{item.reasoning}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
