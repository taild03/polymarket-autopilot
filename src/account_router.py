"""
Multi-Account Google Argon Quota Failover Router (`src/account_router.py`).
Manages multiple Google / Antigravity accounts (Account #1 & Account #2 with Argon).
Automatically detects quota exhaustion (HTTP 429 / RESOURCE_EXHAUSTED / rate-limit)
and hot-swaps the active credential profile so the 24/7 trading daemon never stops.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DATA_DIR

GEMINI_HOME = Path.home() / ".gemini"
OAUTH_TOKEN_FILE = GEMINI_HOME / "jetski-standalone-oauth-token"
CLI_STATE_FILE = GEMINI_HOME / "antigravity-cli" / "jetski_state.pbtxt"
PROFILES_ROOT = GEMINI_HOME / "autopilot_accounts"
ROUTER_STATE_FILE = DATA_DIR / "account_router_state.json"

QUOTA_ERROR_REGEX = re.compile(
    r"(?:\bhttp[s]?[\s/:]*429\b|\berror[\s:]*429\b|\bstatus[\s:]*429\b|\b429\s+quota\b|\b429\s+too\s+many\b|"
    r"resource_exhausted|quota\s+exceeded|rate[\s_-]?limit|too\s+many\s+requests|limit\s+exceeded)",
    re.IGNORECASE,
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
    Supports both Antigravity OAuth token profiles and fallback API keys,
    plus isolated test mode so unit tests never overwrite live credentials.
    """

    def __init__(
        self,
        cooldown_minutes: int = 60,
        state_file: Optional[Path] = None,
        isolated_mode: bool = False,
    ) -> None:
        self.cooldown_minutes = cooldown_minutes
        self.isolated_mode = isolated_mode or (os.environ.get("AUTOPILOT_TEST_MODE") == "1")
        self.state_file = state_file or ROUTER_STATE_FILE
        if not self.isolated_mode:
            PROFILES_ROOT.mkdir(parents=True, exist_ok=True)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_or_init_state()
        self._auto_enroll_primary_if_needed()
        self._refresh_expired_cooldowns()

    def _load_or_init_state(self) -> Dict[str, Any]:
        if not self.isolated_mode and self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
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
        if not self.isolated_mode:
            self.state_file.write_text(
                json.dumps(target, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def _refresh_expired_cooldowns(self) -> None:
        now_utc = datetime.now(timezone.utc)
        changed = False
        for slot_id, info in self.state.get("accounts", {}).items():
            cd_iso = info.get("cooldown_until_iso", "")
            if cd_iso:
                try:
                    cd_dt = datetime.fromisoformat(cd_iso.replace("Z", "+00:00"))
                    if now_utc >= cd_dt:
                        info["cooldown_until_iso"] = ""
                        if info.get("status") == "COOLDOWN":
                            info["status"] = (
                                "ACTIVE"
                                if self.state.get("active_slot") == slot_id
                                else ("STANDBY" if info.get("configured") else "READY_TO_LINK")
                            )
                        changed = True
                except Exception:
                    pass
        if changed:
            self._save_state()

    def _auto_enroll_primary_if_needed(self) -> None:
        """Automatically snapshots the currently logged-in Google account into slot `account_1`."""
        slot1_dir = PROFILES_ROOT / "account_1"
        slot1_token = slot1_dir / "jetski-standalone-oauth-token"
        if not self.isolated_mode and OAUTH_TOKEN_FILE.exists() and not slot1_token.exists():
            self.save_current_login_to_slot("account_1", label="Google Argon #1 (Primary)")

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
        if not self.isolated_mode:
            slot_dir.mkdir(parents=True, exist_ok=True)

        copied = False
        if not self.isolated_mode:
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

        self._refresh_expired_cooldowns()
        slot_dir = PROFILES_ROOT / slot_id
        slot_token = slot_dir / "jetski-standalone-oauth-token"
        slot_state = slot_dir / "jetski_state.pbtxt"

        if not self.isolated_mode:
            if not slot_token.exists() and not os.environ.get(f"GEMINI_API_KEY_{slot_id[-1]}"):
                return False
            if self.state["accounts"][slot_id].get("cooldown_until_iso"):
                return False
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
        if not output_or_error:
            return False
        return bool(QUOTA_ERROR_REGEX.search(output_or_error))

    def handle_quota_exhausted(self, error_detail: str = "429 Quota Exceeded") -> str:
        """
        Marks the current active slot as COOLDOWN and automatically fails over
        to the alternate Google Argon account slot if available.
        Returns the newly activated slot_id.
        """
        self._refresh_expired_cooldowns()
        now = datetime.now(timezone.utc)
        cooldown_until = (now + timedelta(minutes=self.cooldown_minutes)).isoformat()

        current_slot = self.state["active_slot"]
        cur_acct = self.state["accounts"][current_slot]
        cur_acct["quota_hits"] = int(cur_acct.get("quota_hits", 0)) + 1
        cur_acct["status"] = "COOLDOWN"
        cur_acct["cooldown_until_iso"] = cooldown_until

        next_slot = "account_2" if current_slot == "account_1" else "account_1"
        next_acct = self.state["accounts"][next_slot]
        next_cd = next_acct.get("cooldown_until_iso", "")

        if next_cd:
            reason = (
                f"Cả 2 tài khoản đều chạm Quota ({error_detail[:50]}). "
                f"Chuyển tạm sang {next_slot} chờ hết Cooldown."
            )
        else:
            reason = (
                f"Tự động Failover từ {current_slot} sang {next_slot} do chạm giới hạn Quota "
                f"({error_detail[:60]}). Cooldown {self.cooldown_minutes} phút."
            )
        switched = self.activate_slot(next_slot, reason=reason)
        if not switched:
            self.state["last_switch_reason"] = "Không có tài khoản dự phòng sẵn sàng; tạm dùng kiểm tra xác định."
        cur_acct["status"] = "COOLDOWN"
        cur_acct["cooldown_until_iso"] = cooldown_until
        self._save_state()
        return self.state["active_slot"]

    def get_status_summary(self) -> Dict[str, Any]:
        self._auto_enroll_primary_if_needed()
        self._refresh_expired_cooldowns()
        return self.state
