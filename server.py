#!/usr/bin/env python3
"""
Zero-Touch Autonomous Server & Live Dashboard for Polymarket Autopilot.
Automatically runs a 24/7 background AI worker thread that scans markets,
audits resolution rules, takes profits, and updates the live dashboard at http://localhost:8080.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from run_autopilot import run_cycle
from src.config import BASE_DIR, STATE_JSON_PATH

DASHBOARD_HTML_PATH = BASE_DIR / "dashboard.html"


def autonomous_background_worker(interval_sec: int) -> None:
    """Runs continuously in the background to make the system 100% hands-free."""
    while True:
        try:
            run_cycle(verbose=False)
        except Exception:
            pass
        time.sleep(max(10, interval_sec))


class AutopilotRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html", "/dashboard"):
            if DASHBOARD_HTML_PATH.exists():
                raw = DASHBOARD_HTML_PATH.read_bytes()
            else:
                raw = b"<h1>Dashboard file not found.</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.startswith("/api/state"):
            if not STATE_JSON_PATH.exists():
                state = run_cycle(verbose=False)
            else:
                state = json.loads(STATE_JSON_PATH.read_text(encoding="utf-8"))
            self._send_json(state)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path.startswith("/api/scan"):
            state = run_cycle(verbose=False)
            self._send_json(state)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket Zero-Touch AI Dashboard & Daemon")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--interval", type=int, default=30, help="Autonomous AI cycle interval in seconds")
    args = parser.parse_args()

    # Run initial AI cycle on startup
    run_cycle(verbose=True)

    # Start 24/7 autonomous AI worker thread
    worker = threading.Thread(
        target=autonomous_background_worker,
        args=(args.interval,),
        daemon=True,
    )
    worker.start()

    server = HTTPServer(("127.0.0.1", args.port), AutopilotRequestHandler)
    print(f"[AI AUTOPILOT LIVE] Zero-touch daemon & dashboard active at http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
