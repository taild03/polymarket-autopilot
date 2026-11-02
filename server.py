#!/usr/bin/env python3
"""Persistent paper-trading API. Remote bindings require a bearer token."""
from __future__ import annotations

import argparse
import time
import hmac
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from run_autopilot import run_cycle
from src.config import STATE_JSON_PATH

STOP = threading.Event()


class ScanWorker:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.status = {"phase": "idle", "started_at": None}

    def snapshot(self):
        with self.lock:
            return dict(self.status)

    def start(self):
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.status = {"phase": "running", "started_at": time.time()}
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
            return self.thread

    def _run(self):
        try:
            run_cycle(verbose=False)
            phase = "completed"
        except Exception as exc:
            sys.stderr.write(f"[SCAN ERROR] {type(exc).__name__}: {exc}\n")
            phase = "failed"
        with self.lock:
            self.status["phase"] = phase


SCANS = ScanWorker()


def autonomous_background_worker(interval_sec):
    while not STOP.is_set():
        SCANS.start().join()
        STOP.wait(max(10, interval_sec))


def allowed_origins():
    return {x.strip() for x in os.environ.get('AUTOPILOT_ALLOWED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000').split(',') if x.strip()}


class AutopilotRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        origin = self.headers.get('Origin')
        if origin in allowed_origins():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        origin = self.headers.get('Origin')
        if origin and origin not in allowed_origins():
            self._send_json({'error': 'Origin not allowed'}, 403)
            return False
        token = os.environ.get('AUTOPILOT_API_TOKEN', '')
        supplied = self.headers.get('Authorization', '')
        if token and not hmac.compare_digest(supplied, f'Bearer {token}'):
            self._send_json({'error': 'Authentication required'}, 401)
            return False
        if not token and self.client_address[0] not in ('127.0.0.1', '::1'):
            self._send_json({'error': 'Remote access requires a token'}, 403)
            return False
        return True

    def do_OPTIONS(self):
        self._send_json({}, 200 if self.headers.get('Origin') in allowed_origins() else 403)

    def do_GET(self):
        if not self._authorized():
            return
        route = urlsplit(self.path).path
        if route == '/health':
            self._send_json({'status': 'ok', 'mode': 'paper', 'state_available': STATE_JSON_PATH.exists()})
        elif route == '/api/state':
            try:
                state = json.loads(STATE_JSON_PATH.read_text())
                state['scan_status'] = SCANS.snapshot()
                state['runtime'] = {'mode': 'paper', 'can_scan': True, 'can_switch_accounts': False}
                self._send_json(state)
            except (OSError, ValueError):
                self._send_json({'error': 'State not ready; wait for the first cycle'}, 503)
        else:
            self._send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        if not self._authorized():
            return
        if urlsplit(self.path).path != '/api/scan':
            self._send_json({'error': 'Not found; manage account credentials locally'}, 404)
            return
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self._send_json({'error': 'application/json required'}, 415)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 4096:
                raise ValueError('Body too large')
            body = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body, dict):
                raise ValueError('Expected object')
        except (ValueError, UnicodeError):
            self._send_json({'error': 'Invalid request body'}, 400)
            return
        try:
            thread = SCANS.start()
            if body.get('action') == 'scan_async':
                self._send_json({'scan_status': SCANS.snapshot()}, 202)
                return
            thread.join()
            if SCANS.snapshot()['phase'] == 'failed':
                raise RuntimeError('Scan failed')
            state = json.loads(STATE_JSON_PATH.read_text())
            state['runtime'] = {'mode': 'paper', 'can_scan': True, 'can_switch_accounts': False}
            self._send_json(state)
        except Exception as exc:
            sys.stderr.write(f'[API] {type(exc).__name__}: {exc}\n')
            self._send_json({'error': 'Cycle failed; inspect backend logs'}, 503)

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--interval', type=int, default=30)
    parser.add_argument('--no-worker', action='store_true', help='Serve existing state without running cycles')
    args = parser.parse_args()
    if args.host not in ('127.0.0.1', 'localhost', '::1') and not os.environ.get('AUTOPILOT_API_TOKEN'):
        parser.error('Set AUTOPILOT_API_TOKEN before binding a remote interface')
    server = ThreadingHTTPServer((args.host, args.port), AutopilotRequestHandler)
    if not args.no_worker:
        threading.Thread(target=autonomous_background_worker, args=(args.interval,), daemon=True).start()
    print(f'Paper API: http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STOP.set()
        server.server_close()


if __name__ == '__main__':
    main()
