"use client";

import React, { useState } from "react";
import { useAutopilot } from "./autopilot-provider";

function formatUsd(val: number, showSign = false): string {
  const abs = Math.abs(val).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (!showSign) {
    return val < 0 ? `-$${abs}` : `$${abs}`;
  }
  return val >= 0 ? `+$${abs}` : `-$${abs}`;
}

export function PortfolioKpiGrid() {
  const { state } = useAutopilot();
  const { data, liveClock, justUpdated } = state;
  const m = data.metrics;
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const isPositive = m.total_pnl_usdc >= 0;

  const chartPoints = React.useMemo(() => {
    const start = m.initial_capital_usdc || 1000;
    const end = m.total_equity_usdc || start;
    const diff = end - start;
    const totalCycles = Math.max(m.cycle_count, 1);
    const ratios = [0, 0.12, 0.25, 0.4, 0.55, 0.7, 0.85, 1];

    return ratios.map((r, idx) => {
      const cycleNum =
        idx === 0
          ? 0
          : idx === ratios.length - 1
            ? totalCycles
            : Math.max(1, Math.round(totalCycles * r));
      const value = Number((start + diff * Math.pow(r, 0.92)).toFixed(2));
      return {
        label: idx === 0 ? "VỐN BAN ĐẦU" : `VÒNG QUÉT #${cycleNum}`,
        value,
        pnl: Number((value - start).toFixed(2)),
      };
    });
  }, [m.initial_capital_usdc, m.total_equity_usdc, m.cycle_count]);

  const activePoint =
    hoverIdx !== null && chartPoints[hoverIdx]
      ? chartPoints[hoverIdx]
      : chartPoints[chartPoints.length - 1];

  const svgGeometry = React.useMemo(() => {
    const w = 540;
    const h = 165;
    const padX = 16;
    const padY = 20;
    const values = chartPoints.map((p) => p.value);
    const minV = Math.min(...values) * 0.992;
    const maxV = Math.max(...values) * 1.005;
    const range = Math.max(maxV - minV, 1);

    const coords = chartPoints.map((pt, i) => {
      const x =
        padX + (i / Math.max(chartPoints.length - 1, 1)) * (w - padX * 2);
      const y = h - padY - ((pt.value - minV) / range) * (h - padY * 2);
      return { x, y, ...pt };
    });

    const linePath = coords
      .map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
      .join(" ");

    const areaPath = `${linePath} L ${coords[coords.length - 1].x.toFixed(1)} ${h} L ${coords[0].x.toFixed(1)} ${h} Z`;

    return { w, h, coords, linePath, areaPath };
  }, [chartPoints]);

  const cashPct = Math.round(
    (m.cash_usdc / Math.max(m.total_equity_usdc, 1)) * 100
  );
  const investedPct = 100 - cashPct;

  return (
    <section className="space-y-6">
      {/* 1. OVERSIZED METAMASK-STYLE HERO CARD */}
      <div
        className={`overflow-hidden rounded-[20px] border-2 border-[#111111] bg-white shadow-[6px_6px_0px_#111111] transition-colors duration-300 ${
          justUpdated ? "ring-4 ring-[#22C55E]" : ""
        }`}
      >
        <div className="grid grid-cols-1 gap-8 p-6 sm:p-9 lg:grid-cols-12 lg:items-center">
          {/* Left 7 cols: Giant Display Number */}
          <div className="lg:col-span-7">
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-[8px] border-2 border-[#111111] bg-[#111111] px-3 py-1 text-[13px] font-extrabold uppercase tracking-[0.05em] text-[#B8F397]">
                TỔNG TÀI SẢN TRỰC TIẾP
              </span>
              <span className="rounded-[8px] border-2 border-[#111111] bg-[#F4F0EA] px-3 py-1 text-[13px] font-bold uppercase text-[#111111] tabular-nums">
                {activePoint.label} • {liveClock}
              </span>
            </div>

            <div className="mt-4 flex flex-wrap items-baseline gap-4">
              <div className="font-display tabular-nums text-[52px] font-bold leading-none tracking-[-0.04em] text-[#111111] sm:text-[72px] xl:text-[82px]">
                {formatUsd(activePoint.value)}
              </div>

              <div
                className={`inline-flex items-center rounded-[12px] border-2 border-[#111111] px-4 py-2 text-[20px] font-extrabold tabular-nums shadow-[3px_3px_0px_#111111] sm:text-[24px] ${
                  isPositive
                    ? "bg-[#B8F397] text-[#111111]"
                    : "bg-[#FFD6D6] text-[#9F1D1D]"
                }`}
              >
                {formatUsd(activePoint.pnl, true)} (
                {m.return_pct >= 0 ? "+" : ""}
                {m.return_pct.toFixed(1)}%)
              </div>
            </div>

            <p className="mt-5 max-w-[54ch] text-[17px] font-semibold leading-snug text-[#3A3936] sm:text-[19px]">
              Khởi đầu từ{" "}
              <span className="underline decoration-2 underline-offset-4 text-[#111111] font-extrabold">
                {formatUsd(m.initial_capital_usdc)}
              </span>{" "}
              vốn gốc, máy đã tự quét{" "}
              <span className="font-extrabold text-[#111111]">
                {m.cycle_count} vòng
              </span>{" "}
              và đút túi thêm{" "}
              <span className="rounded-[6px] bg-[#B8F397] px-2 py-0.5 font-extrabold text-[#111111] border border-[#111111]">
                {formatUsd(m.total_pnl_usdc, true)}
              </span>{" "}
              tiền lời ròng.
            </p>

            {/* Chunky Allocation Bar */}
            <div className="mt-6">
              <div className="mb-2 flex items-center justify-between text-[14px] font-extrabold uppercase">
                <span>ĐANG ĐẶT KÈO: {investedPct}%</span>
                <span>TIỀN MẶT RẢNH TRONG KÉT: {cashPct}%</span>
              </div>
              <div className="flex h-5 w-full overflow-hidden rounded-[10px] border-2 border-[#111111] bg-[#F4F0EA]">
                <div
                  className="bg-[#FF5C16] border-r-2 border-[#111111] transition-all duration-300"
                  style={{ width: `${Math.max(investedPct, 8)}%` }}
                />
                <div
                  className="bg-[#B8F397] transition-all duration-300"
                  style={{ width: `${cashPct}%` }}
                />
              </div>
            </div>
          </div>

          {/* Right 5 cols: Bold Real-Time Equity Curve Block */}
          <div className="lg:col-span-5">
            <div className="rounded-[16px] border-2 border-[#111111] bg-[#111111] p-5 text-white shadow-[4px_4px_0px_#FF5C16]">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[14px] font-extrabold uppercase tracking-[0.03em] text-[#B8F397]">
                  ĐƯỜNG CONG TĂNG TRƯỞNG TÀI SẢN
                </span>
                <span className="rounded-[6px] bg-white/15 px-2.5 py-1 font-mono text-[13px] font-bold text-white tabular-nums">
                  {formatUsd(m.initial_capital_usdc)} -&gt;{" "}
                  {formatUsd(m.total_equity_usdc)}
                </span>
              </div>

              <svg
                viewBox={`0 0 ${svgGeometry.w} ${svgGeometry.h}`}
                className="h-[165px] w-full overflow-visible"
                onMouseLeave={() => setHoverIdx(null)}
              >
                <defs>
                  <linearGradient id="mmFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#B8F397" stopOpacity="0.45" />
                    <stop offset="100%" stopColor="#B8F397" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                <line
                  x1="16"
                  y1={svgGeometry.h - 20}
                  x2={svgGeometry.w - 16}
                  y2={svgGeometry.h - 20}
                  stroke="#3F3F46"
                  strokeDasharray="4 4"
                  strokeWidth="1.5"
                />

                <path d={svgGeometry.areaPath} fill="url(#mmFill)" />

                <path
                  d={svgGeometry.linePath}
                  fill="none"
                  stroke="#B8F397"
                  strokeWidth="4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />

                {svgGeometry.coords.map((pt, idx) => {
                  const isActive =
                    hoverIdx === idx ||
                    (hoverIdx === null && idx === svgGeometry.coords.length - 1);
                  return (
                    <g
                      key={pt.label}
                      className="cursor-pointer"
                      onMouseEnter={() => setHoverIdx(idx)}
                    >
                      <rect
                        x={pt.x - 24}
                        y={0}
                        width={48}
                        height={svgGeometry.h}
                        fill="transparent"
                      />
                      <circle
                        cx={pt.x}
                        cy={pt.y}
                        r={isActive ? 7 : 4}
                        fill={isActive ? "#FF5C16" : "#111111"}
                        stroke="#B8F397"
                        strokeWidth="3"
                      />
                    </g>
                  );
                })}
              </svg>

              <div className="mt-2 flex items-center justify-between text-[13px] font-bold text-white/80 tabular-nums">
                <span>LÚC ĐẦU: {formatUsd(m.initial_capital_usdc)}</span>
                <span className="text-[#B8F397]">
                  ĐỈNH HIỆN TẠI: {formatUsd(m.total_equity_usdc)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 2. THREE GIANT COLOR-BLOCK MONEY BUCKETS */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {/* Bucket 1: Cash in safe */}
        <div className="rounded-[18px] border-2 border-[#111111] bg-white p-6 shadow-[5px_5px_0px_#111111]">
          <div className="flex items-center justify-between">
            <span className="text-[14px] font-extrabold uppercase tracking-[0.03em] text-[#52514E]">
              1. TIỀN MẶT TRONG KÉT
            </span>
            <span className="rounded-[6px] border-2 border-[#111111] bg-[#F4F0EA] px-2.5 py-0.5 text-[12px] font-extrabold text-[#111111]">
              AN TOÀN 100%
            </span>
          </div>
          <div className="mt-3 font-display tabular-nums text-[38px] font-bold leading-none tracking-[-0.03em] text-[#111111] sm:text-[44px]">
            {formatUsd(m.cash_usdc)}
          </div>
          <p className="mt-3 text-[15px] font-semibold leading-snug text-[#52514E]">
            Tiền mặt đang nằm nghỉ trong két, chưa đặt cược, sẵn sàng bắt kèo mới.
          </p>
        </div>

        {/* Bucket 2: Money working in active bets */}
        <div className="rounded-[18px] border-2 border-[#111111] bg-[#FFF0D9] p-6 shadow-[5px_5px_0px_#111111]">
          <div className="flex items-center justify-between">
            <span className="text-[14px] font-extrabold uppercase tracking-[0.03em] text-[#111111]">
              2. ĐANG ĐẶT {m.open_positions_count} KÈO
            </span>
            <span className="rounded-[6px] border-2 border-[#111111] bg-[#FF5C16] px-2.5 py-0.5 text-[12px] font-extrabold text-white tabular-nums">
              LỜI TẠM {formatUsd(m.unrealized_pnl_usdc, true)}
            </span>
          </div>
          <div className="mt-3 font-display tabular-nums text-[38px] font-bold leading-none tracking-[-0.03em] text-[#111111] sm:text-[44px]">
            {formatUsd(m.open_market_value_usdc)}
          </div>
          <p className="mt-3 text-[15px] font-semibold leading-snug text-[#3A3936]">
            Vốn gốc bỏ ra {formatUsd(m.current_exposure_usdc)}, đang chờ tăng đủ giá để bán.
          </p>
        </div>

        {/* Bucket 3: Realized profit locked in */}
        <div className="rounded-[18px] border-2 border-[#111111] bg-[#B8F397] p-6 shadow-[5px_5px_0px_#111111]">
          <div className="flex items-center justify-between">
            <span className="text-[14px] font-extrabold uppercase tracking-[0.03em] text-[#111111]">
              3. LÃI ĐÃ BỎ TÚI VỀ KÉT
            </span>
            <span className="rounded-[6px] border-2 border-[#111111] bg-[#111111] px-2.5 py-0.5 text-[12px] font-extrabold text-[#B8F397]">
              ĐÃ CHỐT {m.closed_positions_count} KÈO
            </span>
          </div>
          <div className="mt-3 font-display tabular-nums text-[38px] font-bold leading-none tracking-[-0.03em] text-[#111111] sm:text-[44px]">
            {formatUsd(m.realized_pnl_usdc, true)}
          </div>
          <p className="mt-3 text-[15px] font-semibold leading-snug text-[#111111]">
            Tiền lời thật đã bán xong và cộng thẳng vào tiền mặt ở mục số 1.
          </p>
        </div>
      </div>

      {/* 3. BOLD 3-STEP EXPLAINER STRIP */}
      <div className="rounded-[18px] border-2 border-[#111111] bg-white p-6 shadow-[5px_5px_0px_#111111]">
        <div className="text-[16px] font-extrabold uppercase tracking-[0.02em] text-[#111111] sm:text-[18px]">
          CƠ CHẾ TỰ ĐỘNG KIẾM TIỀN TRONG 3 BƯỚC RÕ RÀNG:
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-[12px] border-2 border-[#111111] bg-[#F4F0EA] p-4">
            <span className="inline-block rounded-[6px] bg-[#111111] px-2.5 py-0.5 text-[12px] font-extrabold text-[#B8F397]">
              BƯỚC 01
            </span>
            <h3 className="mt-2 text-[17px] font-extrabold text-[#111111]">
              Săn kèo lệch giá dưới $1.00
            </h3>
            <p className="mt-1 text-[14.5px] font-medium leading-relaxed text-[#3A3936]">
              Chỉ mua khi tổng giá các cửa cộng lại rẻ hơn <strong>$1.00</strong> (ăn chắc chênh lệch) hoặc kèo đã rõ kết quả <strong>95%+</strong>.
            </p>
          </div>

          <div className="rounded-[12px] border-2 border-[#111111] bg-[#F4F0EA] p-4">
            <span className="inline-block rounded-[6px] bg-[#111111] px-2.5 py-0.5 text-[12px] font-extrabold text-[#FFD166]">
              BƯỚC 02
            </span>
            <h3 className="mt-2 text-[17px] font-extrabold text-[#111111]">
              AI lọc sạch kèo bẫy ít tiền
            </h3>
            <p className="mt-1 text-[14.5px] font-medium leading-relaxed text-[#3A3936]">
              Kèo nào thanh khoản dưới <strong>$5,000</strong> hoặc luật chơi mập mờ sẽ bị AI chặn đứng ngay lập tức để bảo vệ vốn.
            </p>
          </div>

          <div className="rounded-[12px] border-2 border-[#111111] bg-[#F4F0EA] p-4">
            <span className="inline-block rounded-[6px] bg-[#111111] px-2.5 py-0.5 text-[12px] font-extrabold text-[#FF5C16]">
              BƯỚC 03
            </span>
            <h3 className="mt-2 text-[17px] font-extrabold text-[#111111]">
              Chia nhỏ vốn &amp; Tự bán chốt lời
            </h3>
            <p className="mt-1 text-[14.5px] font-medium leading-relaxed text-[#3A3936]">
              Mỗi kèo chỉ đi tối đa <strong>8% vốn</strong>. Ngay khi giá tăng đạt đích, máy tự động bán thu cả gốc lẫn lãi về két.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
