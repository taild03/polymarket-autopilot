"use client";

import React, { useMemo } from "react";
import { Filter } from "lucide-react";
import { type FilterMode, useAutopilot } from "@/components/autopilot-provider";
import type { StrategyType } from "@/types/autopilot";

// Hoisted static JSX map per `rendering-hoist-jsx`
const STRATEGY_BADGE: Record<StrategyType, React.ReactNode> = {
  BUNDLE_ARB: (
    <span className="px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 font-semibold">
      BUNDLE_ARB
    </span>
  ),
  BOND_CARRY: (
    <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 font-semibold">
      BOND_CARRY
    </span>
  ),
  MAKER_SPREAD: (
    <span className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 font-semibold">
      MAKER_SPREAD
    </span>
  ),
};

const FILTER_OPTIONS: { mode: FilterMode; label: string }[] = [
  { mode: "ALL", label: "Tất cả tín hiệu" },
  { mode: "BUNDLE_ARB", label: "Bundle Arbitrage" },
  { mode: "BOND_CARRY", label: "Bond Carry" },
  { mode: "MAKER_SPREAD", label: "Maker Spread" },
  { mode: "REJECTED", label: "Bẫy Đã Chặn" },
];

export function StrategyPositionsTable() {
  const { state, actions } = useAutopilot();
  const { data, filterMode } = state;

  // Derived rows computed during render via Map O(1) lookup (`js-set-map-lookups` & `rerender-derived-state-no-effect`)
  const rows = useMemo(() => {
    const openByMarket = new Map(
      (data.open_positions ?? []).map((p) => [p.market_id, p])
    );
    const decisionBySignal = new Map(
      (data.latest_decisions ?? []).map((d) => [d.signal_id, d])
    );

    return (data.latest_signals ?? [])
      .map((sig) => {
        const openPos = openByMarket.get(sig.market_id);
        const decision = decisionBySignal.get(sig.signal_id);
        const isTrap = sig.liquidity_usd < data.config.min_liquidity_usd;
        const isOpenOrApproved = Boolean(openPos) || Boolean(decision?.approved);
        return {
          sig,
          openPos,
          decision,
          isTrap,
          isOpenOrApproved,
        };
      })
      .filter((row) => {
        if (filterMode === "ALL") return true;
        if (filterMode === "REJECTED") return row.isTrap || !row.isOpenOrApproved;
        return row.isOpenOrApproved && row.sig.strategy === filterMode;
      });
  }, [data, filterMode]);

  return (
    <section className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-indigo-400" />
            <h2 className="text-base font-semibold text-slate-100">
              Danh Mục Vị Thế Đang Mở & Bộ Lọc Tín Hiệu Định Lượng
            </h2>
          </div>
          <p className="text-xs text-slate-400">
            Kết hợp dữ liệu Sổ lệnh Polymarket, Giá trị hợp lý (Fair Value) và trạng thái kiểm duyệt 7 cổng
          </p>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {FILTER_OPTIONS.map((opt) => {
            const active = filterMode === opt.mode;
            return (
              <button
                key={opt.mode}
                type="button"
                onClick={() => actions.setFilterMode(opt.mode)}
                className={
                  active
                    ? "px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-500 text-slate-950 cursor-pointer"
                    : "px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200 cursor-pointer"
                }
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400">
              <th className="py-2.5 pr-3">Thị trường & Lý do Định lượng</th>
              <th className="py-2.5 px-3">Chiến lược</th>
              <th className="py-2.5 px-3">Hướng / Lệnh</th>
              <th className="py-2.5 px-3">Giá Vào → Hiện Tại → Fair</th>
              <th className="py-2.5 px-3">Vốn / Lãi Tạm Tính</th>
              <th className="py-2.5 px-3">APR Kỳ vọng</th>
              <th className="py-2.5 pl-3 text-right">Trạng thái Kiểm toán</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {rows.map(({ sig, openPos, decision, isTrap, isOpenOrApproved }) => {
              const markPrice = openPos ? openPos.mark_price : sig.entry_price;
              const sizeUsdc = openPos
                ? openPos.cost_basis_usdc
                : decision?.recommended_size_usdc ?? 0;
              const unrealized = openPos ? openPos.unrealized_pnl_usdc : 0;

              return (
                <tr
                  key={sig.signal_id}
                  className={isOpenOrApproved ? "hover:bg-slate-800/30" : "bg-rose-500/5"}
                >
                  <td className="py-3 pr-3">
                    <div className="font-semibold text-slate-100">{sig.question}</div>
                    <div className="text-slate-400 mt-0.5">{sig.rationale}</div>
                  </td>
                  <td className="py-3 px-3 whitespace-nowrap">
                    {STRATEGY_BADGE[sig.strategy]}
                  </td>
                  <td className="py-3 px-3 whitespace-nowrap font-mono text-slate-300">
                    {sig.side} ({sig.order_type})
                  </td>
                  <td className="py-3 px-3 whitespace-nowrap font-mono text-slate-200">
                    ${sig.entry_price.toFixed(3)} → ${markPrice.toFixed(3)} → $
                    {sig.fair_value.toFixed(3)}
                  </td>
                  <td className="py-3 px-3 whitespace-nowrap font-mono">
                    {isOpenOrApproved ? (
                      <div>
                        <span className="font-semibold text-slate-100">
                          ${sizeUsdc.toFixed(2)}
                        </span>
                        <span className="text-emerald-400 ml-1.5">
                          (+${unrealized.toFixed(2)})
                        </span>
                      </div>
                    ) : (
                      <span className="text-slate-500">$0.00</span>
                    )}
                  </td>
                  <td className="py-3 px-3 whitespace-nowrap font-mono font-bold">
                    {isOpenOrApproved ? (
                      <span className="text-emerald-400">
                        {sig.expected_apr_pct.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-slate-500 line-through">
                        {sig.expected_apr_pct.toFixed(1)}%
                      </span>
                    )}
                  </td>
                  <td className="py-3 pl-3 text-right whitespace-nowrap">
                    {isOpenOrApproved ? (
                      <div>
                        <div className="font-semibold text-emerald-400">
                          ĐANG MỞ VỊ THẾ
                        </div>
                        <div className="text-slate-400">
                          Liq: ${sig.liquidity_usd.toLocaleString("en-US")}
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="font-semibold text-rose-400">
                          {isTrap ? "ĐÃ CHẶN BẪY (VETO)" : "ĐÃ KIỂM DUYỆT"}
                        </div>
                        <div className="text-slate-400">
                          {decision?.reject_reason || "LOW_LIQUIDITY"}
                        </div>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
