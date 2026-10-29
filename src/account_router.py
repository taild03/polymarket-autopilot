"""
Multi-Account Google Argon Quota Failover Router (`src/account_router.py`).
Manages multiple Google / Antigravity accounts (Account #1 & Account #2 with Argon).
Automatically detects quota exhaustion (HTTP 429 / RESOURCE_EXHAUSTED / rate-limit)
and hot-swaps the active credential profile so the 24/7 trading daemon never stops.
"""
import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATA_DIR

GEMINI_HOME = Path.home() / ".gemini"
OAUTH_TOKEN_FILE = GEMINI_HOME / "jetski-standalone-oauth-token"
CLI_STATE_FILE = GEMINI_HOME / "antigravity-cli" / "jetski_state.pbtxt"
PROFILES_ROOT = GEMINI_HOME / "autopilot_accounts"
ROUTER_STATE_FILE = DATA_DIR / "account_router_state.json"

QUOTA_ERROR_PATTERNS = (
    "429",
    "quota",
    "resource_exhausted",
    "rate limit",
    "rate_limit",
    "too many requests",
    "exhausted",
    "limit exceeded",
)


@dataclass
class AccountSlot:
    slot_id: str                  # "account_1" | "account_2"
    label: str                    # e.g. "Google Argon #1 (Primary)"
    model_tier: str               # "Gemini 4 Argon (High)"
    configured: bool
    status: str                   # "ACTIVE" | "STANDBY" | "COOLDOWN" | "UNCONFIGURED"
    calls_succeeded: int
    quota_hits: int
    cooldown_until_iso: str
    last_used_iso: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ArgonAccountRouter:
    """
    Hot-swaps between 2+ Google Argon accounts when quota limits are reached.
    Supports both Antigravity OAuth token profiles and fallback API keys.
    """

    def __init__(self, cooldown_minutes: int = 60) -> None:
        self.cooldown_minutes = cooldown_minutes
        PROFILES_ROOT.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.state = self._load_or_init_state()
        self._auto_enroll_primary_if_needed()

    def _load_or_init_state(self) -> Dict[str, Any]:
        if ROUTER_STATE_FILE.exists():
            try:
                return json.loads(ROUTER_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        default_state = {
            "active_slot": "account_1",
            "total_switches": 0,
            "last_switch_reason": "Khởi tạo mặc định trên Google Argon #1",
            "last_switch_at": datetime.now(timezone.utc).isoformat(),
            "accounts": {
                "account_1": {
                    "slot_id": "account_1",
                    "label": "Google Argon #1 (Primary)",
                    "model_tier": "Gemini 4 Argon (High)",
                    "configured": False,
                    "status": "ACTIVE",
                    "calls_succeeded": 0,
                    "quota_hits": 0,
                    "cooldown_until_iso": "",
                    "last_used_iso": "",
                },
                "account_2": {
                    "slot_id": "account_2",
                    "label": "Google Argon #2 (Backup Failover)",
                    "model_tier": "Gemini 4 Argon (High)",
                    "configured": False,
                    "status": "STANDBY",
                    "calls_succeeded": 0,
                    "quota_hits": 0,
                    "cooldown_until_iso": "",
                    "last_used_iso": "",
                },
            },
        }
        self._save_state(default_state)
        return default_state

    def _save_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        target = state or self.state
        ROUTER_STATE_FILE.write_text(json.dumps(target, indent=2, ensure_ascii=False), encoding="utf-8")

    def _auto_enroll_primary_if_needed(self) -> None:
        """Automatically snapshots the currently logged-in Google account into slot `account_1`."""
        slot1_dir = PROFILES_ROOT / "account_1"
        slot1_token = slot1_dir / "jetski-standalone-oauth-token"
        if OAUTH_TOKEN_FILE.exists() and not slot1_token.exists():
            self.save_current_login_to_slot("account_1", label="Google Argon #1 (Primary)")

        # Refresh configured flags
        for slot_id in ("account_1", "account_2"):
            slot_token = PROFILES_ROOT / slot_id / "jetski-standalone-oauth-token"
            env_key = os.environ.get(f"GEMINI_API_KEY_{slot_id[-1]}")
            is_cfg = slot_token.exists() or bool(env_key)
            self.state["accounts"][slot_id]["configured"] = is_cfg
            if not is_cfg and self.state["accounts"][slot_id]["status"] == "STANDBY":
                self.state["accounts"][slot_id]["status"] = "READY_TO_LINK"
        self._save_state()

    def save_current_login_to_slot(self, slot_id: str, label: Optional[str] = None) -> bool:
        """Copies the active ~/.gemini OAuth token & CLI state into the specified account slot."""
        if slot_id not in ("account_1", "account_2"):
            raise ValueError("slot_id must be 'account_1' or 'account_2'")
        slot_dir = PROFILES_ROOT / slot_id
        slot_dir.mkdir(parents=True, exist_ok=True)

        copied = False
        if OAUTH_TOKEN_FILE.exists():
            shutil.copy2(OAUTH_TOKEN_FILE, slot_dir / "jetski-standalone-oauth-token")
            copied = True
        if CLI_STATE_FILE.exists():
            shutil.copy2(CLI_STATE_FILE, slot_dir / "jetski_state.pbtxt")
            copied = True

        acct = self.state["accounts"][slot_id]
        acct["configured"] = copied
        if label:
            acct["label"] = label
        acct["status"] = "ACTIVE" if self.state["active_slot"] == slot_id else "STANDBY"
        self._save_state()
        return copied

    def activate_slot(self, slot_id: str, reason: str = "Manual switch") -> bool:
        """Hot-swaps the saved OAuth credentials for `slot_id` into ~/.gemini and marks it ACTIVE."""
        if slot_id not in self.state["accounts"]:
            return False

        slot_dir = PROFILES_ROOT / slot_id
        slot_token = slot_dir / "jetski-standalone-oauth-token"
        slot_state = slot_dir / "jetski_state.pbtxt"

        if slot_token.exists():
            shutil.copy2(slot_token, OAUTH_TOKEN_FILE)
        if slot_state.exists() and CLI_STATE_FILE.parent.exists():
            shutil.copy2(slot_state, CLI_STATE_FILE)

        now_iso = datetime.now(timezone.utc).isoformat()
        prev_slot = self.state["active_slot"]
        self.state["active_slot"] = slot_id
        if prev_slot != slot_id:
            self.state["total_switches"] = int(self.state.get("total_switches", 0)) + 1
        self.state["last_switch_reason"] = reason
        self.state["last_switch_at"] = now_iso

        for s_id, info in self.state["accounts"].items():
            if s_id == slot_id:
                info["status"] = "ACTIVE"
                info["cooldown_until_iso"] = ""
            else:
                if info["status"] == "ACTIVE":
                    info["status"] = "STANDBY" if info["configured"] else "READY_TO_LINK"

        self._save_state()
        return True

    def record_success(self) -> None:
        active = self.state["active_slot"]
        acct = self.state["accounts"][active]
        acct["calls_succeeded"] = int(acct.get("calls_succeeded", 0)) + 1
        acct["last_used_iso"] = datetime.now(timezone.utc).isoformat()
        self._save_state()

    def is_quota_error(self, output_or_error: str) -> bool:
        lower = (output_or_error or "").lower()
        return any(pat in lower for pat in QUOTA_ERROR_PATTERNS)

    def handle_quota_exhausted(self, error_detail: str = "429 Quota Exceeded") -> str:
        """
        Marks the current active slot as COOLDOWN and automatically fails over
        to the alternate Google Argon account slot.
        Returns the newly activated slot_id.
        """
        now = datetime.now(timezone.utc)
        cooldown_until = (now + timedelta(minutes=self.cooldown_minutes)).isoformat()

        current_slot = self.state["active_slot"]
        cur_acct = self.state["accounts"][current_slot]
        cur_acct["quota_hits"] = int(cur_acct.get("quota_hits", 0)) + 1
        cur_acct["status"] = "COOLDOWN"
        cur_acct["cooldown_until_iso"] = cooldown_until

        next_slot = "account_2" if current_slot == "account_1" else "account_1"
        reason = (
            f"Tự động Failover từ {current_slot} sang {next_slot} do chạm giới hạn Quota "
            f"({error_detail[:60]}). Cooldown {self.cooldown_minutes} phút."
        )
        self.activate_slot(next_slot, reason=reason)
        cur_acct["status"] = "COOLDOWN"
        self._save_state()
        return next_slot

    def get_status_summary(self) -> Dict[str, Any]:
        self._auto_enroll_primary_if_needed()
        return self.state
