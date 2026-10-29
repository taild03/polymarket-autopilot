#!/usr/bin/env python3
"""
CLI Utility to manage the 2 Google Argon Accounts for Polymarket Autopilot.
Commands:
  python3 manage_accounts.py status             # Show status of Account #1 and Account #2
  python3 manage_accounts.py save account_1     # Snapshot current login as Account #1
  python3 manage_accounts.py save account_2     # Snapshot current login as Account #2
  python3 manage_accounts.py switch account_2   # Manually switch active account
  python3 manage_accounts.py simulate-failover  # Test automatic quota failover
"""
import argparse
import json
from src.account_router import ArgonAccountRouter


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Dual Google Argon Accounts for Autopilot")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Display dual account quota & failover status")

    p_save = sub.add_parser("save", help="Save currently logged-in Google/agy account into a slot")
    p_save.add_argument("slot", choices=["account_1", "account_2"], help="Target account slot")
    p_save.add_argument("--label", default=None, help="Custom display label")

    p_switch = sub.add_parser("switch", help="Switch active Google Argon account slot")
    p_switch.add_argument("slot", choices=["account_1", "account_2"], help="Slot to activate")

    sub.add_parser("simulate-failover", help="Simulate a 429 Quota Exhausted event to test automatic switching")

    args = parser.parse_args()
    router = ArgonAccountRouter()

    if args.cmd == "save":
        ok = router.save_current_login_to_slot(args.slot, label=args.label)
        print(f"[ACCOUNT ROUTER] Saved current OAuth profile to '{args.slot}' (success={ok})")
    elif args.cmd == "switch":
        router.activate_slot(args.slot, reason=f"Chuyển đổi thủ công sang {args.slot}")
        print(f"[ACCOUNT ROUTER] Active slot switched to '{args.slot}'")
    elif args.cmd == "simulate-failover":
        new_slot = router.handle_quota_exhausted("HTTP 429: RESOURCE_EXHAUSTED on Argon model")
        print(f"[ACCOUNT ROUTER] Quota failover triggered! Now active on: '{new_slot}'")

    summary = router.get_status_summary()
    print("=" * 74)
    print(" DUAL GOOGLE ARGON ACCOUNT ROUTER STATUS")
    print("=" * 74)
    print(f" Active Account Slot : {summary['active_slot']}")
    print(f" Total Auto-Switches : {summary['total_switches']}")
    print(f" Last Switch Reason  : {summary['last_switch_reason']}")
    print("-" * 74)
    for slot_id, info in summary["accounts"].items():
        marker = ">> ACTIVE <<" if slot_id == summary["active_slot"] else info["status"]
        print(
            f" [{slot_id}] {info['label']} ({info['model_tier']})\n"
            f"    Status: {marker} | Token Saved: {info['configured']} | "
            f"Calls OK: {info['calls_succeeded']} | Quota Hits: {info['quota_hits']}"
        )
    print("=" * 74)


if __name__ == "__main__":
    main()
