import { NextResponse } from "next/server";
import {
  getAutopilotServerState,
  switchArgonAccountServer,
  triggerPythonCycle,
} from "@/lib/autopilot-server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const state = await getAutopilotServerState();
    return NextResponse.json(state, {
      headers: {
        "Cache-Control": "no-store, max-age=0",
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to load state" },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const bodyPromise = request.json().catch(() => ({}));
    const body = (await bodyPromise) as {
      action?: "scan" | "switch_account";
      slot?: "account_1" | "account_2" | "failover";
    };

    if (body.action === "switch_account" && body.slot) {
      const updated = await switchArgonAccountServer(body.slot);
      return NextResponse.json(updated);
    }

    const updated = await triggerPythonCycle();
    return NextResponse.json(updated);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Execution failed" },
      { status: 500 }
    );
  }
}
