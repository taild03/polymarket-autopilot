#!/usr/bin/env python3
"""
Decoupled Backend API Server & 24/7 Autonomous AI Daemon (`server.py`).
Binds to 0.0.0.0:8080 with CORS enabled so any Frontend (Local, Mobile LAN,
Cloudflare Tunnel, Tailscale, or GitHub Pages) can poll live data directly
WITHOUT needing to `git push` on every market tick.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from run_autopilot import run_cycle
from src.account_router import ArgonAccountRouter
from src.config import BASE_DIR, STATE_JSON_PATH

FRONTEND_HTML_PATH = BASE_DIR / "frontend" / "index.html"
FALLBACK_HTML_PATH = BASE_DIR / "dashboard.html"


def autonomous_background_worker(interval_sec: int) -> None:
    """Runs continuously in the background to make the system 100% hands-free."""
    while True:
        try:
            run_cycle(verbose=False)
        except Exception:
            pass
        time.sleep(max(10, interval_sec))


class AutopilotRequestHandler(BaseHTTPRequestHandler):
    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html", "/dashboard"):
            target_html = FRONTEND_HTML_PATH if FRONTEND_HTML_PATH.exists() else FALLBACK_HTML_PATH
            raw = target_html.read_bytes() if target_html.exists() else b"<h1>Frontend not found.</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._set_cors_headers()
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.startswith("/api/state"):
            if not STATE_JSON_PATH.exists():
                state = run_cycle(verbose=False)
            else:
                state = json.loads(STATE_JSON_PATH.read_text(encoding="utf-8"))
            self._send_json(state)
        elif self.path.startswith("/api/accounts"):
            router = ArgonAccountRouter()
            self._send_json(router.get_status_summary())
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path.startswith("/api/scan"):
            state = run_cycle(verbose=False)
            self._send_json(state)
        elif self.path.startswith("/api/switch-account"):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            router = ArgonAccountRouter()
            target_slot = body.get("slot")
            if target_slot in ("account_1", "account_2"):
                router.activate_slot(target_slot, reason="Chuyển đổi từ giao diện Web Command Center")
            else:
                router.handle_quota_exhausted("Simulated Quota Failover from Web UI")
            state = run_cycle(verbose=False)
            self._send_json(state)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket Decoupled Backend API & Daemon")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--interval", type=int, default=30, help="Autonomous AI cycle interval in seconds")
    args = parser.parse_args()

    run_cycle(verbose=True)

    worker = threading.Thread(
        target=autonomous_background_worker,
        args=(args.interval,),
        daemon=True,
    )
    worker.start()

    server = HTTPServer(("0.0.0.0", args.port), AutopilotRequestHandler)
    print(f"[BACKEND API LIVE] Listening on http://0.0.0.0:{args.port} (CORS enabled for remote Frontend)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
