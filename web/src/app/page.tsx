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
    <div className="min-h-screen bg-[#F4F0EA] p-6 sm:p-10">
      <div className="mx-auto max-w-[1360px] space-y-6">
        <div className="h-20 animate-pulse rounded-[16px] border-2 border-[#111111] bg-white" />
        <div className="h-80 animate-pulse rounded-[20px] border-2 border-[#111111] bg-white" />
      </div>
    </div>
  );
}

async function AutopilotDashboardContent() {
  const initialData = await getAutopilotServerState();

  return (
    <AutopilotProvider initialData={initialData}>
      <div className="min-h-screen bg-[#F4F0EA] text-[#111111]">
        <HeaderBar />

        <main className="mx-auto max-w-[1360px] space-y-8 px-4 py-6 sm:px-8 sm:py-9">
          {/* 1. Giant MetaMask-Style Hero Portfolio + 3 Color-Block Money Compartments */}
          <PortfolioKpiGrid />

          {/* 2. Asymmetric 12-Col Split: 7 Cols Active Positions / 5 Cols Live Activity Stream */}
          <section className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-start">
            <div className="lg:col-span-7">
              <StrategyPositionsTable />
            </div>
            <div className="lg:col-span-5">
              <AiBrainFeed />
            </div>
          </section>

          {/* 3. Dual Google Argon Accounts & Server Source */}
          <ArgonAccountPanel />
        </main>

        <footer className="mx-auto max-w-[1360px] border-t-2 border-[#111111] px-4 py-6 text-[14px] font-bold text-[#111111] sm:px-8">
          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
            <span>
              SỔ ĐẦU TƯ POLYMARKET TỰ HÀNH • CHẾ ĐỘ BẢO TOÀN VỐN ($1,000.00 VỐN GỐC)
            </span>
            <span>
              TỰ ĐỘNG LÀM MỚI MỖI 5 GIÂY • GIỚI HẠN AN TOÀN TỐI ĐA 8% VỐN MỖI KÈO
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
