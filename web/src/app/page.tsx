import React, { Suspense } from "react";
import { getAutopilotServerState } from "@/lib/autopilot-server";
import { AutopilotProvider } from "@/components/autopilot-provider";
import { HeaderBar } from "@/components/header-bar";
import { PortfolioKpiGrid } from "@/components/portfolio-kpi-grid";
import { StrategyPositionsTable } from "@/components/strategy-positions-table";
import { AiBrainFeed } from "@/components/ai-brain-feed";
import { ArgonAccountPanel } from "@/components/argon-account-panel";

export const dynamic = "force-dynamic";

function PortfolioSkeleton() {
  return (
    <div className="min-h-screen bg-[#F7F6F3] p-6 sm:p-10">
      <div className="mx-auto max-w-[1200px] space-y-6">
        <div className="h-14 animate-pulse rounded-[8px] bg-[#EAE9E4]" />
        <div className="h-64 animate-pulse rounded-[8px] bg-[#EAE9E4]" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="h-96 animate-pulse rounded-[8px] bg-[#EAE9E4] lg:col-span-7" />
          <div className="h-96 animate-pulse rounded-[8px] bg-[#EAE9E4] lg:col-span-5" />
        </div>
      </div>
    </div>
  );
}

async function AutopilotDashboardContent() {
  const initialData = await getAutopilotServerState();

  return (
    <AutopilotProvider initialData={initialData}>
      <div className="min-h-screen bg-[#F7F6F3] text-[#111111]">
        <HeaderBar />

        <main className="mx-auto max-w-[1200px] space-y-6 px-4 py-6 sm:px-8 sm:py-8">
          {/* 1. Robinhood-Style Hero Portfolio Value + Equity Curve + 3-Step Plain Guide */}
          <PortfolioKpiGrid />

          {/* 2. Asymmetric 2-Column Editorial Split: 7 Cols Active Positions / 5 Cols Activity Log */}
          <section className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-start">
            <div className="lg:col-span-7">
              <StrategyPositionsTable />
            </div>
            <div className="lg:col-span-5">
              <AiBrainFeed />
            </div>
          </section>

          {/* 3. Unobtrusive Bottom Settings: Dual Google Argon Failover & Server Source */}
          <ArgonAccountPanel />
        </main>

        <footer className="mx-auto max-w-[1200px] border-t border-[#EAEAEA] px-4 py-6 text-[12px] text-[#787774] sm:px-8">
          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
            <span>
              Sổ Đầu Tư Polymarket Tự Hành • Chế độ Paper Trading bảo toàn vốn ($1,000.00 USDC)
            </span>
            <span>
              Giới hạn an toàn: Tối đa 8% vốn mỗi kèo • Luôn giữ tiền mặt dự phòng trong két
            </span>
          </div>
        </footer>
      </div>
    </AutopilotProvider>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<PortfolioSkeleton />}>
      <AutopilotDashboardContent />
    </Suspense>
  );
}
