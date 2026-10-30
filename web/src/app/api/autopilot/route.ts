import { NextResponse } from "next/server";
import { getAutopilotServerState, triggerPythonCycle } from "@/lib/autopilot-server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await getAutopilotServerState(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Unable to read portfolio" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  // Public deployments are read-only; backend credentials never reach the browser.
  if (process.env.VERCEL || request.headers.get("origin") !== new URL(request.url).origin) {
    return NextResponse.json({ error: "Remote controls are disabled" }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json({ error: "application/json required" }, { status: 415 });
  }
  try {
    const body = await request.json();
    if (body?.action !== "scan") return NextResponse.json({ error: "Unsupported action" }, { status: 400 });
    return NextResponse.json(await triggerPythonCycle());
  } catch {
    return NextResponse.json({ error: "Scan failed. Check the Python backend and its logs." }, { status: 503 });
  }
}
