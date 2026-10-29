"use client";

import React from "react";
import { useAutopilot, type FilterMode } from "./autopilot-provider";
import type { OpenPosition, RiskDecisionItem, StrategyType } from "@/types/autopilot";

function getStrategyMeta(strategy: StrategyType) {
  switch (strategy) {
    case "BUNDLE_ARB":
      return {
        label: "GOM TRỌN GIỎ (CHẮC THẮNG)",
        badgeClass: "bg-[#D8E6FF] text-[#111111]",
      };
    case "BOND_CARRY":
      return {
        label: "KÈO RÕ KẾT QUẢ 95%+",
        badgeClass: "bg-[#B8F397] text-[#111111]",
      };
    case "MAKER_SPREAD":
      return {
        label: "ĐẶT GIÁ RẺ CHỜ KHỚP",
        badgeClass: "bg-[#FFD166] text-[#111111]",
      };
  }
}

function getSideVietnamese(side: string): string {
  if (side === "YES_NO_BUNDLE") return "MUA CẢ 2 CỬA CÓ + KHÔNG";
  if (side === "YES") return "CHỌN CỬA CÓ (YES)";
  if (side === "NO") return "CHỌN CỬA KHÔNG (NO)";
  return side;
}

function buildPlainVietnameseExplanation(pos: OpenPosition): string {
  const entryCents = (pos.entry_price * 100).toFixed(1);
  const fairCents = (pos.fair_value * 100).toFixed(1);
  const days = Math.max(1, Math.round(pos.days_to_expiry));

  if (pos.strategy === "BUNDLE_ARB") {
    return `Tổng giá mua trọn bộ các cửa chỉ tốn ${entryCents} xu (rẻ hơn mức trả thưởng 100 xu). Bất kể kết quả sự kiện ra sao, khi đóng sổ cũng thu về đủ 100 xu.`;
  }
  if (pos.strategy === "BOND_CARRY") {
    return `Kèo này đã ngã ngũ tới ${fairCents}% ngoài thực tế. Máy mua ở giá ${entryCents} xu và giữ ${days} ngày tới lúc kết thúc để nhận 100 xu.`;
  }
  return `Máy đặt giá chờ mua rẻ ở mức ${entryCents} xu (trong khi giá thị trường là ${fairCents} xu) để ăn ngay chênh lệch khi khớp lệnh.`;
}

function translateRejectReason(reason: string): string {
  const lower = reason.toLowerCase();
  if (lower.includes("liquidity")) {
    return "ĐÃ CHẶN TỰ ĐỘNG: Kèo này có quá ít người giao dịch (thanh khoản dưới $5,000). Mua vào sẽ dễ bị kẹt tiền không bán ra được.";
  }
  if (lower.includes("spread")) {
    return "ĐÃ CHẶN TỰ ĐỘNG: Chênh lệch giá mua và bán quá rộng, vào lệnh sẽ bị thiệt giá ngay.";
  }
  if (lower.includes("rule") || lower.includes("ambigu") || lower.includes("clarity")) {
    return "ĐÃ CHẶN TỰ ĐỘNG: Luật phân xử thắng thua của kèo này viết mập mờ, có nguy cơ tranh chấp.";
  }
  return `ĐÃ CHẶN ĐỂ BẢO VỆ VỐN: ${reason}`;
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
    { id: "ALL", label: "ĐANG GIỮ TIỀN", count: openPositions.length },
    {
      id: "BUNDLE_ARB",
      label: "GOM TRỌN GIỎ",
      count: openPositions.filter((p) => p.strategy === "BUNDLE_ARB").length,
    },
    {
      id: "BOND_CARRY",
      label: "THẮNG 95%+",
      count: openPositions.filter((p) => p.strategy === "BOND_CARRY").length,
    },
    {
      id: "MAKER_SPREAD",
      label: "CHỜ GIÁ RẺ",
      count: openPositions.filter((p) => p.strategy === "MAKER_SPREAD").length,
    },
    {
      id: "REJECTED",
      label: "KÈO BẪY ĐÃ NÉ",
      count: rejectedDecisions.length,
    },
  ];

  return (
    <div className="rounded-[20px] border-2 border-[#111111] bg-white p-5 shadow-[6px_6px_0px_#111111] sm:p-7">
      {/* Header */}
      <div className="border-b-2 border-[#111111] pb-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-display text-[22px] font-bold uppercase tracking-[-0.02em] text-[#111111] sm:text-[26px]">
              CÁC KÈO ĐANG GIỮ TIỀN CỦA BẠN
            </h2>
            <p className="mt-1 text-[15px] font-semibold text-[#52514E]">
              Nhìn nhanh từng kèo: Mua giá nào, hiện tại bao nhiêu và đang lời bao nhiêu đô
            </p>
          </div>
          <span className="rounded-[8px] border-2 border-[#111111] bg-[#B8F397] px-3 py-1.5 text-[13px] font-extrabold uppercase text-[#111111]">
            ĐANG MỞ {openPositions.length} KÈO
          </span>
        </div>

        {/* Chunky MetaMask Filter Tabs */}
        <div className="mt-4 flex flex-wrap gap-2">
          {filterTabs.map((tab) => {
            const active = filterMode === tab.id;
            const isRejectedTab = tab.id === "REJECTED";
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => actions.setFilterMode(tab.id)}
                className={`inline-flex items-center gap-2 rounded-[10px] border-2 border-[#111111] px-3.5 py-2 text-[13px] font-extrabold uppercase transition-all cursor-pointer ${
                  active
                    ? isRejectedTab
                      ? "bg-[#FF3B30] text-white shadow-[3px_3px_0px_#111111]"
                      : "bg-[#111111] text-white shadow-[3px_3px_0px_#FF5C16]"
                    : "bg-[#F4F0EA] text-[#111111] hover:bg-[#E7E2D8]"
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`rounded-[6px] px-2 py-0.5 text-[12px] tabular-nums ${
                    active
                      ? "bg-white text-[#111111]"
                      : "bg-[#111111] text-white"
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Content */}
      {filterMode === "REJECTED" ? (
        <div className="mt-5 space-y-4">
          {rejectedDecisions.length === 0 ? (
            <div className="p-8 text-center text-[16px] font-bold text-[#52514E]">
              Chưa có kèo rủi ro nào bị chặn trong vòng quét này.
            </div>
          ) : (
            rejectedDecisions.map((item: RiskDecisionItem) => {
              const meta = getStrategyMeta(item.strategy);
              return (
                <div
                  key={item.signal_id}
                  className="rounded-[16px] border-2 border-[#111111] bg-[#FFD6D6] p-5 shadow-[4px_4px_0px_#111111]"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="rounded-[6px] border-2 border-[#111111] bg-[#FF3B30] px-3 py-1 text-[12px] font-extrabold uppercase text-white">
                      ĐÃ TỪ CHỐI XUỐNG TIỀN
                    </span>
                    <span className="text-[13px] font-bold text-[#111111]">
                      {meta.label}
                    </span>
                  </div>
                  <h3 className="mt-3 text-[19px] font-extrabold leading-snug text-[#111111]">
                    {item.question}
                  </h3>
                  <div className="mt-3 rounded-[10px] border-2 border-[#111111] bg-white p-3.5 text-[15px] font-bold leading-relaxed text-[#9F1D1D]">
                    {translateRejectReason(item.reject_reason)}
                  </div>
                </div>
              );
            })
          )}
        </div>
      ) : (
        <div className="mt-5 space-y-5">
          {filteredPositions.length === 0 ? (
            <div className="p-8 text-center text-[16px] font-bold text-[#52514E]">
              Không có kèo nào trong nhóm này.
            </div>
          ) : (
            filteredPositions.map((pos: OpenPosition) => {
              const meta = getStrategyMeta(pos.strategy);
              const isProfit = pos.unrealized_pnl_usdc >= 0;
              const entryCents = pos.entry_price * 100;
              const markCents = pos.mark_price * 100;
              const progressTo100 = Math.min(
                98,
                Math.max(15, Math.round(markCents))
              );

              return (
                <article
                  key={pos.position_id}
                  className="rounded-[16px] border-2 border-[#111111] bg-[#FAF8F5] p-5 shadow-[4px_4px_0px_#111111] sm:p-6"
                >
                  {/* Top Badges */}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-[8px] border-2 border-[#111111] px-3 py-1 text-[12px] font-extrabold uppercase ${meta.badgeClass}`}
                      >
                        {meta.label}
                      </span>
                      <span className="rounded-[8px] border-2 border-[#111111] bg-white px-3 py-1 text-[12px] font-extrabold uppercase text-[#111111]">
                        {getSideVietnamese(pos.side)}
                      </span>
                    </div>
                    <span className="rounded-[8px] border-2 border-[#111111] bg-[#111111] px-3 py-1 text-[12px] font-extrabold uppercase text-[#FFD166] tabular-nums">
                      CÒN {Math.max(1, Math.round(pos.days_to_expiry))} NGÀY CHỐT SỔ
                    </span>
                  </div>

                  {/* Big Question Title */}
                  <h3 className="mt-3.5 text-[20px] font-extrabold leading-snug text-[#111111] sm:text-[22px]">
                    {pos.question}
                  </h3>

                  {/* Real-Time Price Progress Bar toward 100 cents */}
                  <div className="mt-4 rounded-[12px] border-2 border-[#111111] bg-white p-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[14px] font-extrabold tabular-nums">
                      <span>LÚC MUA: {entryCents.toFixed(1)}¢</span>
                      <span className="text-[#15803D]">
                        GIÁ HIỆN TẠI: {markCents.toFixed(1)}¢
                      </span>
                      <span>ĐÍCH TRẢ THƯỞNG: 100.0¢ ($1.00)</span>
                    </div>
                    <div className="mt-2 h-3.5 w-full overflow-hidden rounded-full border-2 border-[#111111] bg-[#F4F0EA]">
                      <div
                        className="h-full bg-[#B8F397] transition-all duration-500"
                        style={{ width: `${progressTo100}%` }}
                      />
                    </div>
                  </div>

                  {/* Plain Vietnamese Explanation */}
                  <div className="mt-3.5 rounded-[12px] border-2 border-[#111111] bg-[#F4F0EA] p-3.5 text-[15px] font-semibold leading-relaxed text-[#111111]">
                    <span className="font-extrabold uppercase underline decoration-2">
                      Lý do thắng:{" "}
                    </span>
                    {buildPlainVietnameseExplanation(pos)}
                  </div>

                  {/* 3 Giant Financial Numbers */}
                  <div className="mt-4 grid grid-cols-1 gap-3 border-t-2 border-[#111111] pt-4 sm:grid-cols-3">
                    <div className="rounded-[10px] border-2 border-[#111111] bg-white p-3">
                      <span className="block text-[12px] font-extrabold uppercase text-[#52514E]">
                        GIÁ MUA -&gt; GIÁ HIỆN TẠI
                      </span>
                      <span className="mt-1 block font-mono text-[20px] font-extrabold text-[#111111] tabular-nums">
                        {entryCents.toFixed(1)}¢ -&gt; {markCents.toFixed(1)}¢
                      </span>
                    </div>

                    <div className="rounded-[10px] border-2 border-[#111111] bg-white p-3">
                      <span className="block text-[12px] font-extrabold uppercase text-[#52514E]">
                        VỐN ĐÃ BỎ VÀO KÈO
                      </span>
                      <span className="mt-1 block font-display text-[24px] font-bold text-[#111111] tabular-nums">
                        ${pos.cost_basis_usdc.toFixed(2)}
                      </span>
                    </div>

                    <div
                      className={`rounded-[10px] border-2 border-[#111111] p-3 ${
                        isProfit ? "bg-[#B8F397]" : "bg-[#FFD6D6]"
                      }`}
                    >
                      <span className="block text-[12px] font-extrabold uppercase text-[#111111]">
                        THÀNH TIỀN &amp; LỜI HIỆN TẠI
                      </span>
                      <div className="mt-1 flex items-baseline justify-between tabular-nums">
                        <span className="font-display text-[24px] font-bold text-[#111111]">
                          ${pos.market_value_usdc.toFixed(2)}
                        </span>
                        <span className="rounded-[6px] bg-[#111111] px-2 py-0.5 text-[14px] font-extrabold text-[#B8F397]">
                          {isProfit ? "+" : "-"}$
                          {Math.abs(pos.unrealized_pnl_usdc).toFixed(2)}
                        </span>
                      </div>
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
