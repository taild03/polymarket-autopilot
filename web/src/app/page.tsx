import React from "react";
import { getAutopilotServerState } from "@/lib/autopilot-server";
import { AutopilotProvider } from "@/components/autopilot-provider";
import { HeaderBar } from "@/components/header-bar";
import { ArgonAccountPanel } from "@/components/argon-account-panel";
import { PortfolioKpiGrid } from "@/components/portfolio-kpi-grid";
import { AiBrainFeed } from "@/components/ai-brain-feed";
import { StrategyPositionsTable } from "@/components/strategy-positions-table";

export const dynamic = "force-dynamic";

export default async function AutopilotDashboardPage() {
  const initialState = await getAutopilotServerState();

  return (
    <AutopilotProvider initialData={initialState}>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <HeaderBar />
        <ArgonAccountPanel />
        <PortfolioKpiGrid />
        <AiBrainFeed />
        <StrategyPositionsTable />
      </main>
    </AutopilotProvider>
  );
}
