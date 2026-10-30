#!/usr/bin/env python3
"""
CLI Utility to manage the 2 Google Argon Accounts for Polymarket Autopilot.
Commands:
  python3 manage_accounts.py status             # Show status of Account #1 and Account #2
  python3 manage_accounts.py login account_2    # Open browser login for Account #2 and save it
  python3 manage_accounts.py save account_1     # Snapshot current login as Account #1
  python3 manage_accounts.py save account_2     # Snapshot current login as Account #2
  python3 manage_accounts.py switch account_2   # Manually switch active account
  python3 manage_accounts.py simulate-failover  # Test automatic quota failover
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import time
import webbrowser
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import re
from src.account_router import ArgonAccountRouter, PROFILES_ROOT

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _discover_local_agy_oauth_config() -> tuple[str, list[str]]:
    """Reads the public desktop OAuth client parameters from the local agy binary."""
    agy_bin = Path.home() / ".local" / "bin" / "agy"
    if not agy_bin.exists():
        return ("", [])
    raw = agy_bin.read_bytes()
    client_ids = [
        m.group(0).decode("ascii")
        for m in re.finditer(
            rb"1071006060591-[A-Za-z0-9_.-]+\.apps\.googleusercontent\.com",
            raw,
        )
    ]
    secrets_found = [
        m.group(0).decode("ascii")
        for m in re.finditer(rb"GOCSPX-[A-Za-z0-9_-]{28}", raw)
    ]
    return (client_ids[0] if client_ids else "", secrets_found)


def extract_email_from_id_token(id_token: str) -> Optional[str]:
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "==="
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims.get("email")
    except Exception:
        return None


def exchange_code_for_token(
    code: str, redirect_uri: str, code_verifier: str
) -> Optional[Dict[str, Any]]:
    client_id, client_secrets = _discover_local_agy_oauth_config()
    for secret in client_secrets:
        data = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
    return None


def valid_oauth_callback(path: str, expected_state: str) -> bool:
    parsed = urllib.parse.urlparse(path)
    qs = urllib.parse.parse_qs(parsed.query)
    return parsed.path == "/auth/callback" and secrets.compare_digest(qs.get("state", [""])[0], expected_state)


def interactive_login_slot(
    router: ArgonAccountRouter, slot: str, label: Optional[str] = None
) -> bool:
    """
    Launches a local OAuth callback listener on 127.0.0.1, opens the macOS default
    browser with Google Account Chooser (`prompt=select_account consent`), and saves
    the resulting OAuth token directly into `~/.gemini/autopilot_accounts/<slot>/`.
    """
    state_token = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    captured: Dict[str, Any] = {"code": None, "error": None}

    class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if not valid_oauth_callback(self.path, state_token):
                self.send_response(400)
                self.end_headers()
                return
            if "error" in qs:
                captured["error"] = qs["error"][0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<h3>Đăng nhập bị hủy hoặc gặp lỗi. Bạn có thể đóng tab này.</h3>".encode(
                        "utf-8"
                    )
                )
                return

            if "code" in qs:
                captured["code"] = qs["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = "<h3>Da nhan ma xac thuc. Kiem tra terminal de biet ket qua dang nhap.</h3>"
                self.wfile.write(html.encode("utf-8"))
                return

            self.send_response(404)
            self.end_headers()

    server = http.server.HTTPServer(("127.0.0.1", 0), OAuthCallbackHandler)
    server.timeout = 1
    port = server.server_port
    redirect_uri = f"http://localhost:{port}/auth/callback"
    client_id, _ = _discover_local_agy_oauth_config()

    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "select_account consent",
        "state": state_token,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode(auth_params)
    )

    print("=" * 74)
    print(f" ĐANG BẬT TRÌNH DUYỆT ĐỂ ĐĂNG NHẬP [{slot.upper()}]")
    print(" Vui lòng chọn Nick Google thứ 2 của bạn trên cửa sổ trình duyệt...")
    print(f" Nếu trình duyệt không tự bật, hãy bấm vào link sau:\n {auth_url}")
    print("=" * 74, flush=True)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Wait for the single OAuth callback request (up to 180 seconds)
    deadline = time.monotonic() + 180
    try:
        while time.monotonic() < deadline and not captured["code"] and not captured["error"]:
            server.handle_request()
    finally:
        server.server_close()

    if not captured["code"]:
        print(
            f"[WARN] Chưa nhận được mã xác thực từ trình duyệt (error={captured['error']})."
        )
        return False

    token_resp = exchange_code_for_token(
        captured["code"], redirect_uri, code_verifier
    )
    if not token_resp or "access_token" not in token_resp:
        print("[ERROR] Không thể đổi mã xác thực sang OAuth token.")
        return False

    expires_in = int(token_resp.get("expires_in", 3599))
    expiry_iso = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    id_token = token_resp.get("id_token", "")
    email = extract_email_from_id_token(id_token)

    stored_payload = {
        "token": {
            "access_token": token_resp["access_token"],
            "token_type": token_resp.get("token_type", "Bearer"),
            "refresh_token": token_resp.get("refresh_token", ""),
            "expiry": expiry_iso,
            "expires_in": expires_in,
        },
        "auth_method": "consumer",
        "id_token": id_token,
    }

    slot_dir = PROFILES_ROOT / slot
    slot_dir.mkdir(parents=True, exist_ok=True)
    token_path = slot_dir / "jetski-standalone-oauth-token"
    token_path.write_text(json.dumps(stored_payload, indent=2), encoding="utf-8")
    os.chmod(token_path, 0o600)

    display_label = label or (
        f"Nick Google #2 ({email})"
        if email and slot == "account_2"
        else f"Nick Google #1 ({email})"
        if email
        else "Google Argon #2 (Backup Failover)"
    )

    acct = router.state["accounts"][slot]
    acct["configured"] = True
    acct["label"] = display_label
    acct["status"] = (
        "ACTIVE" if router.state["active_slot"] == slot else "STANDBY"
    )
    router._save_state()

    print(f"[SUCCESS] Đã lưu thành công {display_label} vào khe '{slot}'!")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Dual Google Argon Accounts for Autopilot"
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Display dual account quota & failover status")

    p_login = sub.add_parser(
        "login",
        help="Interactive browser login for a specific slot (e.g. account_2)",
    )
    p_login.add_argument(
        "slot", choices=["account_1", "account_2"], help="Target account slot"
    )
    p_login.add_argument("--label", default=None, help="Custom display label")

    p_save = sub.add_parser(
        "save", help="Save currently logged-in Google/agy account into a slot"
    )
    p_save.add_argument(
        "slot", choices=["account_1", "account_2"], help="Target account slot"
    )
    p_save.add_argument("--label", default=None, help="Custom display label")

    p_switch = sub.add_parser(
        "switch", help="Switch active Google Argon account slot"
    )
    p_switch.add_argument(
        "slot", choices=["account_1", "account_2"], help="Slot to activate"
    )

    sub.add_parser(
        "simulate-failover",
        help="Simulate a 429 Quota Exhausted event to test automatic switching",
    )

    args = parser.parse_args()
    router = ArgonAccountRouter()

    if args.cmd == "login":
        interactive_login_slot(router, args.slot, label=args.label)
    elif args.cmd == "save":
        ok = router.save_current_login_to_slot(args.slot, label=args.label)
        print(
            f"[ACCOUNT ROUTER] Saved current OAuth profile to '{args.slot}' (success={ok})"
        )
    elif args.cmd == "switch":
        router.activate_slot(
            args.slot, reason=f"Chuyển đổi thủ công sang {args.slot}"
        )
        print(f"[ACCOUNT ROUTER] Active slot switched to '{args.slot}'")
    elif args.cmd == "simulate-failover":
        new_slot = router.handle_quota_exhausted(
            "HTTP 429: RESOURCE_EXHAUSTED on Argon model"
        )
        print(
            f"[ACCOUNT ROUTER] Quota failover triggered! Now active on: '{new_slot}'"
        )

    summary = router.get_status_summary()
    print("=" * 74)
    print(" DUAL GOOGLE ARGON ACCOUNT ROUTER STATUS")
    print("=" * 74)
    print(f" Active Account Slot : {summary['active_slot']}")
    print(f" Total Auto-Switches : {summary['total_switches']}")
    print(f" Last Switch Reason  : {summary['last_switch_reason']}")
    print("-" * 74)
    for slot_id, info in summary["accounts"].items():
        marker = (
            ">> ACTIVE <<"
            if slot_id == summary["active_slot"]
            else info["status"]
        )
        print(
            f" [{slot_id}] {info['label']} ({info['model_tier']})\n"
            f"    Status: {marker} | Token Saved: {info['configured']} | "
            f"Calls OK: {info['calls_succeeded']} | Quota Hits: {info['quota_hits']}"
        )
    print("=" * 74)


if __name__ == "__main__":
    main()
