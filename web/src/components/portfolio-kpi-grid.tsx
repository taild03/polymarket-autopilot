"use client";

import React from "react";
import { DollarSign, Layers, ShieldCheck, TrendingUp } from "lucide-react";
import { useAutopilot } from "@/components/autopilot-provider";

export function PortfolioKpiGrid() {
  const { state } = useAutopilot();
  const m = state.data.metrics;
  const utilizationPct =
    m.total_equity_usdc > 0
      ? ((m.current_exposure_usdc / m.total_equity_usdc) * 100).toFixed(1)
      : "0.0";

  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-lg">
        <div className="flex items-center justify-between text-xs text-slate-400 uppercase tracking-wider">
          <span>Tổng Tài Sản (Total Equity)</span>
          <DollarSign className="w-4 h-4 text-emerald-400" />
        </div>
        <div className="text-2xl font-bold text-slate-100 mt-1.5 font-mono">
          ${m.total_equity_usdc.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className="text-xs font-semibold text-emerald-400 mt-1">
          +${m.total_pnl_usdc.toFixed(2)} (+{m.return_pct.toFixed(2)}%) Tổng Lãi Ròng
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-lg">
        <div className="flex items-center justify-between text-xs text-slate-400 uppercase tracking-wider">
          <span>Lãi Đã Chốt / Đang Mở</span>
          <TrendingUp className="w-4 h-4 text-indigo-400" />
        </div>
        <div className="text-2xl font-bold text-emerald-400 mt-1.5 font-mono">
          +${m.realized_pnl_usdc.toFixed(2)} / +${m.unrealized_pnl_usdc.toFixed(2)}
        </div>
        <div className="text-xs text-slate-400 mt-1">
          Đã chốt lời tự động {m.closed_positions_count} vị thế hội tụ
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-lg">
        <div className="flex items-center justify-between text-xs text-slate-400 uppercase tracking-wider">
          <span>Tiền Mặt / Vốn Đang Đánh</span>
          <Layers className="w-4 h-4 text-amber-400" />
        </div>
        <div className="text-2xl font-bold text-slate-100 mt-1.5 font-mono">
          ${m.cash_usdc.toFixed(2)} / ${m.current_exposure_usdc.toFixed(2)}
        </div>
        <div className="text-xs text-slate-400 mt-1">
          Đang mở {m.open_positions_count} lệnh • Tỷ lệ vốn {utilizationPct}% (Trần 50%)
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-lg">
        <div className="flex items-center justify-between text-xs text-slate-400 uppercase tracking-wider">
          <span>Cầu Dao & Kiểm Toán AI</span>
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
        </div>
        <div className="text-2xl font-bold text-emerald-400 mt-1.5">
          7/7 Cổng An Toàn
        </div>
        <div className="text-xs text-slate-400 mt-1">
          Ngắt mạch tự động nếu lỗ ngày vượt -3.0% (-$30.00)
        </div>
      </div>
    </section>
  );
}
