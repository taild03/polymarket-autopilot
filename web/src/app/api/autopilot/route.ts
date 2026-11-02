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
  const origin = request.headers.get("origin");
  const url = new URL(request.url);
  const host = request.headers.get("host") ?? "";
  // Next can canonicalize 127.0.0.1 to localhost in request.url. Keep the
  // browser's actual loopback host AND port matched for this case.
  const localOrigin = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host)
    && origin === `${url.protocol}//${host}`;
  if (process.env.VERCEL || (origin !== url.origin && !localOrigin)) {
    return NextResponse.json({ error: "Remote controls are disabled" }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json({ error: "application/json required" }, { status: 415 });
  }
  try {
    const body = await request.json();
    if (body?.action !== "scan") return NextResponse.json({ error: "Unsupported action" }, { status: 400 });
    return NextResponse.json(await triggerPythonCycle(), { status: 202 });
  } catch {
    return NextResponse.json({ error: "Scan failed. Check the Python backend and its logs." }, { status: 503 });
  }
}
