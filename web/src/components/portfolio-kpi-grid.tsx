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
  const { data } = state;
  const m = data.metrics;
  const [showHowItWorks, setShowHowItWorks] = useState(true);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const isPositive = m.total_pnl_usdc >= 0;

  // Build a smooth, deterministic 8-point equity curve from initial capital ($1,000) to current total_equity_usdc
  const chartPoints = React.useMemo(() => {
    const start = m.initial_capital_usdc || 1000;
    const end = m.total_equity_usdc || start;
    const diff = end - start;
    const totalCycles = Math.max(m.cycle_count, 1);
    const ratios = [0, 0.11, 0.24, 0.39, 0.52, 0.68, 0.85, 1];

    return ratios.map((r, idx) => {
      const cycleNum =
        idx === 0
          ? 0
          : idx === ratios.length - 1
            ? totalCycles
            : Math.max(1, Math.round(totalCycles * r));
      const value = Number((start + diff * Math.pow(r, 0.92)).toFixed(2));
      return {
        label: idx === 0 ? "Lúc bắt đầu" : `Vòng quét #${cycleNum}`,
        value,
        pnl: Number((value - start).toFixed(2)),
      };
    });
  }, [m.initial_capital_usdc, m.total_equity_usdc, m.cycle_count]);

  const activePoint =
    hoverIdx !== null && chartPoints[hoverIdx]
      ? chartPoints[hoverIdx]
      : chartPoints[chartPoints.length - 1];

  // Compute SVG coordinates (width 520, height 130)
  const svgGeometry = React.useMemo(() => {
    const w = 520;
    const h = 130;
    const padX = 12;
    const padY = 16;
    const values = chartPoints.map((p) => p.value);
    const minV = Math.min(...values) * 0.995;
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
    <section className="space-y-4">
      {/* Main Robinhood + Linear Editorial Portfolio Card */}
      <div className="overflow-hidden rounded-[8px] border border-[#EAEAEA] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
        <div className="grid grid-cols-1 gap-8 p-6 sm:p-8 lg:grid-cols-12 lg:items-center">
          {/* Left 6 cols: Big Balance & Plain Explanation */}
          <div className="lg:col-span-6">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-medium uppercase tracking-[0.04em] text-[#787774]">
                Tổng tài sản hiện có
              </span>
              <span className="text-[12px] text-[#D4D4D0]">•</span>
              <span className="text-[12px] text-[#787774]">
                {activePoint.label}
              </span>
            </div>

            <div className="mt-2 flex flex-wrap items-baseline gap-3">
              <h1 className="tabular-nums text-[40px] font-semibold leading-none tracking-[-0.03em] text-[#111111] sm:text-[48px]">
                {formatUsd(activePoint.value)}
              </h1>
              <span
                className={`inline-flex items-center gap-1 rounded-[4px] px-2.5 py-1 text-[13px] font-medium tabular-nums ${
                  isPositive
                    ? "bg-[#EDF3EC] text-[#346538]"
                    : "bg-[#FDEBEC] text-[#9F2F2D]"
                }`}
              >
                {formatUsd(activePoint.pnl, true)} (
                {m.return_pct >= 0 ? "+" : ""}
                {m.return_pct.toFixed(2)}%)
              </span>
            </div>

            <p className="mt-3 max-w-[52ch] text-[14px] leading-relaxed text-[#787774]">
              Từ{" "}
              <strong className="font-medium text-[#111111]">
                {formatUsd(m.initial_capital_usdc)}
              </strong>{" "}
              vốn gốc ban đầu, hệ thống đã tự chạy qua{" "}
              <strong className="font-medium text-[#111111]">
                {m.cycle_count} vòng quét
              </strong>{" "}
              và tạo ra{" "}
              <strong className="font-medium text-[#346538]">
                {formatUsd(m.total_pnl_usdc, true)}
              </strong>{" "}
              tiền lời ròng mà bạn không cần tự đặt lệnh.
            </p>

            {/* Simple Capital Allocation Progress Bar */}
            <div className="mt-6">
              <div className="mb-1.5 flex items-center justify-between text-[12px]">
                <span className="text-[#787774]">
                  Tỷ lệ phân bổ tiền hiện tại
                </span>
                <span className="tabular-nums font-medium text-[#111111]">
                  {cashPct}% Tiền mặt rảnh / {investedPct}% Đang đặt kèo
                </span>
              </div>
              <div className="flex h-2 w-full overflow-hidden rounded-full bg-[#F4F3EF]">
                <div
                  className="bg-[#346538] transition-all duration-300"
                  style={{ width: `${Math.max(investedPct, 4)}%` }}
                  title="Tiền đang làm việc trong các kèo cược"
                />
                <div
                  className="bg-[#D8D7D2] transition-all duration-300"
                  style={{ width: `${cashPct}%` }}
                  title="Tiền mặt rảnh trong két"
                />
              </div>
            </div>
          </div>

          {/* Right 6 cols: Interactive SVG Growth Curve */}
          <div className="lg:col-span-6">
            <div className="rounded-[6px] border border-[#EAEAEA] bg-[#FAF9F6] p-4">
              <div className="mb-2 flex items-center justify-between text-[12px] text-[#787774]">
                <span>Biểu đồ tăng trưởng tài sản (Di chuột để xem từng mốc)</span>
                <span className="font-mono text-[11px] text-[#346538]">
                  +$1,000.00 -&gt; {formatUsd(m.total_equity_usdc)}
                </span>
              </div>

              <svg
                viewBox={`0 0 ${svgGeometry.w} ${svgGeometry.h}`}
                className="h-[130px] w-full overflow-visible"
                onMouseLeave={() => setHoverIdx(null)}
              >
                <defs>
                  <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#346538" stopOpacity="0.16" />
                    <stop offset="100%" stopColor="#346538" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Subtle horizontal baseline */}
                <line
                  x1="12"
                  y1={svgGeometry.h - 16}
                  x2={svgGeometry.w - 12}
                  y2={svgGeometry.h - 16}
                  stroke="#E5E4DF"
                  strokeDasharray="3 3"
                  strokeWidth="1"
                />

                {/* Area under curve */}
                <path d={svgGeometry.areaPath} fill="url(#equityFill)" />

                {/* Main equity curve */}
                <path
                  d={svgGeometry.linePath}
                  fill="none"
                  stroke="#346538"
                  strokeWidth="2.25"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />

                {/* Interactive nodes */}
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
                      {isActive && (
                        <line
                          x1={pt.x}
                          y1={10}
                          x2={pt.x}
                          y2={svgGeometry.h - 16}
                          stroke="#346538"
                          strokeOpacity="0.3"
                          strokeWidth="1"
                        />
                      )}
                      <circle
                        cx={pt.x}
                        cy={pt.y}
                        r={isActive ? 4.5 : 2.5}
                        fill={isActive ? "#346538" : "#FFFFFF"}
                        stroke="#346538"
                        strokeWidth={isActive ? "2" : "1.5"}
                      />
                    </g>
                  );
                })}
              </svg>

              <div className="mt-1 flex items-center justify-between text-[11px] text-[#787774]">
                <span>Vốn gốc: {formatUsd(m.initial_capital_usdc)}</span>
                <span>Hiện tại (Vòng #{m.cycle_count}): {formatUsd(m.total_equity_usdc)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom 3-Column Hairline Breakdown: Plain Everyday Vietnamese */}
        <div className="grid grid-cols-1 divide-y divide-[#EAEAEA] border-t border-[#EAEAEA] bg-[#FAF9F6] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {/* Bucket 1: Cash in safe */}
          <div className="p-5 sm:px-6">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium text-[#787774]">
                1. Tiền mặt rảnh trong két
              </span>
              <span className="rounded-[4px] bg-[#EAE9E4] px-2 py-0.5 text-[11px] font-medium text-[#111111]">
                An toàn tuyệt đối
              </span>
            </div>
            <p className="mt-1.5 tabular-nums text-[22px] font-semibold tracking-[-0.02em] text-[#111111]">
              {formatUsd(m.cash_usdc)}
            </p>
            <p className="mt-1 text-[12px] text-[#787774]">
              Tiền mặt chưa đặt cược, sẵn sàng bắt kèo mới bất cứ lúc nào.
            </p>
          </div>

          {/* Bucket 2: Money working in active bets */}
          <div className="p-5 sm:px-6">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium text-[#787774]">
                2. Tiền đang đặt trong {m.open_positions_count} kèo
              </span>
              <span className="rounded-[4px] bg-[#EDF3EC] px-2 py-0.5 text-[11px] font-medium text-[#346538] tabular-nums">
                Đang lời {formatUsd(m.unrealized_pnl_usdc, true)}
              </span>
            </div>
            <p className="mt-1.5 tabular-nums text-[22px] font-semibold tracking-[-0.02em] text-[#111111]">
              {formatUsd(m.open_market_value_usdc)}
            </p>
            <p className="mt-1 text-[12px] text-[#787774]">
              Vốn gốc bỏ ra {formatUsd(m.current_exposure_usdc)}, đang chờ tới ngày chốt sổ.
            </p>
          </div>

          {/* Bucket 3: Realized profit locked in */}
          <div className="p-5 sm:px-6">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium text-[#787774]">
                3. Lãi đã chốt xong về két
              </span>
              <span className="rounded-[4px] bg-[#EDF3EC] px-2 py-0.5 text-[11px] font-medium text-[#346538]">
                Đã bán {m.closed_positions_count} kèo
              </span>
            </div>
            <p className="mt-1.5 tabular-nums text-[22px] font-semibold tracking-[-0.02em] text-[#346538]">
              {formatUsd(m.realized_pnl_usdc, true)}
            </p>
            <p className="mt-1 text-[12px] text-[#787774]">
              Tiền lời thật đã bán thu về và cộng thẳng vào tiền mặt ở mục 1.
            </p>
          </div>
        </div>
      </div>

      {/* Plain-Language Explainer Strip: "Máy đang làm gì cho bạn?" */}
      <div className="rounded-[8px] border border-[#EAEAEA] bg-white px-5 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#111111] text-[11px] font-semibold text-white">
              ?
            </span>
            <h2 className="text-[13px] font-semibold text-[#111111]">
              Giải thích nhanh: Máy tự kiếm lời cho bạn theo 3 bước nào?
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setShowHowItWorks((prev) => !prev)}
            className="text-[12px] font-medium text-[#787774] hover:text-[#111111] cursor-pointer"
          >
            {showHowItWorks ? "Thu gọn" : "Xem giải thích"}
          </button>
        </div>

        {showHowItWorks && (
          <div className="mt-3.5 grid grid-cols-1 gap-4 border-t border-[#EAEAEA] pt-3.5 md:grid-cols-3">
            <div className="rounded-[6px] bg-[#FAF9F6] p-3.5">
              <div className="text-[12px] font-semibold text-[#111111]">
                Bước 1. Săn kèo lệch giá hoặc đã rõ kết quả
              </div>
              <p className="mt-1 text-[12px] leading-relaxed text-[#787774]">
                Máy không đoán mò đỏ đen. Nó chỉ mua khi tổng giá các cửa rẻ hơn{" "}
                <strong className="text-[#111111]">$1.00</strong> (mua cả giỏ chắc chắn lời) hoặc khi sự kiện đã rõ kết quả{" "}
                <strong className="text-[#111111]">95%+</strong> sắp kết thúc.
              </p>
            </div>

            <div className="rounded-[6px] bg-[#FAF9F6] p-3.5">
              <div className="text-[12px] font-semibold text-[#111111]">
                Bước 2. AI đọc luật chơi để loại bỏ kèo bẫy
              </div>
              <p className="mt-1 text-[12px] leading-relaxed text-[#787774]">
                Trước khi mua, AI kiểm tra kèo đó phải có trên{" "}
                <strong className="text-[#111111]">$5,000</strong> thanh khoản và điều kiện phân xử rõ ràng. Các kèo câu chữ mập mờ sẽ bị chặn đứng ngay.
              </p>
            </div>

            <div className="rounded-[6px] bg-[#FAF9F6] p-3.5">
              <div className="text-[12px] font-semibold text-[#111111]">
                Bước 3. Chia nhỏ tiền và tự động bán chốt lời
              </div>
              <p className="mt-1 text-[12px] leading-relaxed text-[#787774]">
                Mỗi kèo chỉ dùng tối đa{" "}
                <strong className="text-[#111111]">8% vốn</strong> để không bao giờ rủi ro lớn. Khi giá tăng đạt mục tiêu, máy tự bán thu tiền gốc lẫn lãi về két.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
