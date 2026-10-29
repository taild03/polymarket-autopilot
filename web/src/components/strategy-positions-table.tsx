"use client";

import React from "react";
import { useAutopilot, type FilterMode } from "./autopilot-provider";
import type { OpenPosition, RiskDecisionItem, StrategyType } from "@/types/autopilot";

function getStrategyMeta(strategy: StrategyType) {
  switch (strategy) {
    case "BUNDLE_ARB":
      return {
        label: "Gom trọn giỏ (Chắc thắng)",
        shortDesc: "Mua cả 2 cửa dưới $1.00",
        badgeClass: "bg-[#E1F3FE] text-[#1F6C9F]",
      };
    case "BOND_CARRY":
      return {
        label: "Kèo rõ kết quả 95%+",
        shortDesc: "Sự kiện gần như đã ngã ngũ",
        badgeClass: "bg-[#EDF3EC] text-[#346538]",
      };
    case "MAKER_SPREAD":
      return {
        label: "Đặt giá thấp chờ khớp",
        shortDesc: "Mua rẻ hơn giá đang giao dịch",
        badgeClass: "bg-[#FBF3DB] text-[#956400]",
      };
  }
}

function getSideVietnamese(side: string): string {
  if (side === "YES_NO_BUNDLE") return "Mua cả 2 cửa Có + Không";
  if (side === "YES") return "Cửa Có (YES)";
  if (side === "NO") return "Cửa Không (NO)";
  return side;
}

function buildPlainVietnameseExplanation(pos: OpenPosition): string {
  const entryCents = (pos.entry_price * 100).toFixed(1);
  const fairCents = (pos.fair_value * 100).toFixed(1);
  const days = Math.max(1, Math.round(pos.days_to_expiry));

  if (pos.strategy === "BUNDLE_ARB") {
    return `Máy phát hiện tổng giá mua trọn bộ các cửa chỉ tốn ${entryCents} xu (rẻ hơn mức trả thưởng cố định 100 xu). Bất kể kết quả sự kiện ra sao, khi đóng sổ cũng thu về 100 xu cho mỗi phần.`;
  }
  if (pos.strategy === "BOND_CARRY") {
    return `Kèo này đã rõ kết quả tới ${fairCents}% trên thị trường. Máy mua vào ở giá ${entryCents} xu và giữ thêm khoảng ${days} ngày tới lúc kết thúc để nhận đủ 100 xu.`;
  }
  return `Máy đặt lệnh chờ mua ở giá rẻ ${entryCents} xu trong khi giá hợp lý trên sàn đang là ${fairCents} xu, giúp ăn ngay phần chênh lệch giá khi có người bán vội.`;
}

function translateRejectReason(reason: string): string {
  const lower = reason.toLowerCase();
  if (lower.includes("liquidity")) {
    return "Chặn tự động: Kèo này có quá ít người giao dịch (thanh khoản dưới $5,000). Nếu mua vào sẽ khó bán ra khi cần chốt lời.";
  }
  if (lower.includes("spread")) {
    return "Chặn tự động: Khoảng cách giữa giá mua và giá bán quá rộng, vào lệnh sẽ bị thiệt giá ngay lập tức.";
  }
  if (lower.includes("rule") || lower.includes("ambigu") || lower.includes("clarity")) {
    return "Chặn tự động: Luật phân định thắng thua của kèo này viết quá ngắn hoặc mập mờ, có nguy cơ tranh chấp khi đóng sổ.";
  }
  if (lower.includes("exposure") || lower.includes("cap")) {
    return "Chặn tự động: Đã chạm trần giới hạn an toàn cho nhóm kèo này, máy giữ lại tiền mặt để bảo vệ vốn.";
  }
  return `Chặn tự động để bảo vệ vốn: ${reason}`;
}

export function StrategyPositionsTable() {
  const { state, actions } = useAutopilot();
  const { data, filterMode } = state;

  const openPositions = data.open_positions || [];
  const rejectedDecisions = React.useMemo(
    () => (data.latest_decisions || []).filter((d) => !d.approved),
    [data.latest_decisions]
  );

  const filteredPositions = React.useMemo(() => {
    if (filterMode === "REJECTED") return [];
    if (filterMode === "ALL") return openPositions;
    return openPositions.filter((p) => p.strategy === filterMode);
  }, [openPositions, filterMode]);

  const filterTabs: { id: FilterMode; label: string; count: number }[] = [
    { id: "ALL", label: "Đang giữ tiền", count: openPositions.length },
    {
      id: "BUNDLE_ARB",
      label: "Gom trọn giỏ",
      count: openPositions.filter((p) => p.strategy === "BUNDLE_ARB").length,
    },
    {
      id: "BOND_CARRY",
      label: "Thắng 95%+",
      count: openPositions.filter((p) => p.strategy === "BOND_CARRY").length,
    },
    {
      id: "MAKER_SPREAD",
      label: "Chờ giá rẻ",
      count: openPositions.filter((p) => p.strategy === "MAKER_SPREAD").length,
    },
    {
      id: "REJECTED",
      label: "Kèo bẫy đã né",
      count: rejectedDecisions.length,
    },
  ];

  return (
    <div className="rounded-[8px] border border-[#EAEAEA] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      {/* Section Header */}
      <div className="border-b border-[#EAEAEA] p-5 sm:px-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-[16px] font-semibold tracking-[-0.01em] text-[#111111]">
              Các kèo đang giữ tiền của bạn
            </h2>
            <p className="mt-0.5 text-[13px] text-[#787774]">
              Danh sách chi tiết từng kèo máy đã chọn mua, số tiền bỏ vào và lý do vì sao sẽ có lời
            </p>
          </div>
          <span className="inline-flex items-center self-start rounded-[4px] bg-[#FAF9F6] px-2.5 py-1 text-[12px] font-medium text-[#787774] border border-[#EAEAEA]">
            Đã quét {data.scanned_markets_count || 60} thị trường
          </span>
        </div>

        {/* Minimalist Filter Tabs */}
        <div className="mt-4 flex flex-wrap gap-1.5">
          {filterTabs.map((tab) => {
            const active = filterMode === tab.id;
            const isRejectedTab = tab.id === "REJECTED";
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => actions.setFilterMode(tab.id)}
                className={`inline-flex items-center gap-1.5 rounded-[6px] px-3 py-1.5 text-[12px] font-medium transition-colors cursor-pointer ${
                  active
                    ? isRejectedTab
                      ? "bg-[#9F2F2D] text-white"
                      : "bg-[#111111] text-white"
                    : "bg-[#FAF9F6] text-[#787774] hover:bg-[#F0EFEA] hover:text-[#111111]"
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`rounded-[4px] px-1.5 py-0.2 text-[11px] tabular-nums ${
                    active
                      ? "bg-white/20 text-white"
                      : "bg-[#EAE9E4] text-[#111111]"
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Content List */}
      {filterMode === "REJECTED" ? (
        <div className="divide-y divide-[#EAEAEA]">
          {rejectedDecisions.length === 0 ? (
            <div className="p-8 text-center text-[13px] text-[#787774]">
              Chưa có kèo rủi ro nào bị chặn trong vòng quét này.
            </div>
          ) : (
            rejectedDecisions.map((item: RiskDecisionItem) => {
              const meta = getStrategyMeta(item.strategy);
              return (
                <div key={item.signal_id} className="p-5 sm:px-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="inline-flex items-center rounded-[4px] bg-[#FDEBEC] px-2 py-0.5 text-[11px] font-medium text-[#9F2F2D]">
                      Đã từ chối xuống tiền
                    </span>
                    <span className="text-[12px] text-[#787774]">
                      Nhóm phát hiện: {meta.label}
                    </span>
                  </div>
                  <h3 className="mt-2 text-[14px] font-medium text-[#111111]">
                    {item.question}
                  </h3>
                  <div className="mt-2.5 rounded-[6px] border border-[#F5D0D2] bg-[#FDEBEC]/50 p-3 text-[12px] leading-relaxed text-[#9F2F2D]">
                    {translateRejectReason(item.reject_reason)}
                  </div>
                </div>
              );
            })
          )}
        </div>
      ) : (
        <div className="divide-y divide-[#EAEAEA]">
          {filteredPositions.length === 0 ? (
            <div className="p-8 text-center text-[13px] text-[#787774]">
              Không có kèo nào trong nhóm này.
            </div>
          ) : (
            filteredPositions.map((pos: OpenPosition) => {
              const meta = getStrategyMeta(pos.strategy);
              const isProfit = pos.unrealized_pnl_usdc >= 0;
              const pnlPct =
                pos.cost_basis_usdc > 0
                  ? (pos.unrealized_pnl_usdc / pos.cost_basis_usdc) * 100
                  : 0;

              return (
                <article
                  key={pos.position_id}
                  className="p-5 transition-colors hover:bg-[#FAF9F6]/60 sm:px-6"
                >
                  {/* Top Badges Row */}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`inline-flex items-center rounded-[4px] px-2 py-0.5 text-[11px] font-medium ${meta.badgeClass}`}
                      >
                        {meta.label}
                      </span>
                      <span className="inline-flex items-center rounded-[4px] bg-[#F4F3EF] px-2 py-0.5 text-[11px] font-medium text-[#111111]">
                        {getSideVietnamese(pos.side)}
                      </span>
                    </div>
                    <span className="text-[12px] text-[#787774] tabular-nums">
                      Đáo hạn sau {Math.max(1, Math.round(pos.days_to_expiry))} ngày
                    </span>
                  </div>

                  {/* Question & Event Name */}
                  <h3 className="mt-2.5 text-[15px] font-semibold leading-snug text-[#111111]">
                    {pos.question}
                  </h3>
                  {pos.event_title && pos.event_title !== pos.question && (
                    <p className="mt-0.5 text-[12px] text-[#787774]">
                      Chủ đề: {pos.event_title}
                    </p>
                  )}

                  {/* Plain Vietnamese Explanation Box */}
                  <div className="mt-3 rounded-[6px] bg-[#FAF9F6] p-3 text-[12.5px] leading-relaxed text-[#4A4946] border border-[#EFECE6]">
                    <strong className="font-medium text-[#111111]">
                      Vì sao máy mua kèo này:{" "}
                    </strong>
                    {buildPlainVietnameseExplanation(pos)}
                  </div>

                  {/* Bottom Financial Numbers Strip */}
                  <div className="mt-3.5 grid grid-cols-3 gap-3 pt-1 text-[12px]">
                    <div>
                      <span className="block text-[#787774]">
                        Giá mua -&gt; Hiện tại
                      </span>
                      <span className="mt-0.5 block font-mono text-[13px] font-medium text-[#111111] tabular-nums">
                        {(pos.entry_price * 100).toFixed(1)}¢ -&gt;{" "}
                        {(pos.mark_price * 100).toFixed(1)}¢
                      </span>
                    </div>

                    <div>
                      <span className="block text-[#787774]">
                        Tiền đã bỏ vào
                      </span>
                      <span className="mt-0.5 block text-[14px] font-semibold text-[#111111] tabular-nums">
                        ${pos.cost_basis_usdc.toFixed(2)}
                      </span>
                    </div>

                    <div className="text-right">
                      <span className="block text-[#787774]">
                        Giá trị hiện tại (Lời/Lỗ)
                      </span>
                      <span className="mt-0.5 inline-flex items-baseline gap-1.5 tabular-nums">
                        <strong className="text-[14px] font-semibold text-[#111111]">
                          ${pos.market_value_usdc.toFixed(2)}
                        </strong>
                        <span
                          className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-medium ${
                            isProfit
                              ? "bg-[#EDF3EC] text-[#346538]"
                              : "bg-[#FDEBEC] text-[#9F2F2D]"
                          }`}
                        >
                          {isProfit ? "+" : "-"}$
                          {Math.abs(pos.unrealized_pnl_usdc).toFixed(2)} (
                          {isProfit ? "+" : ""}
                          {pnlPct.toFixed(1)}%)
                        </span>
                      </span>
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
