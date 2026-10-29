"use client";

import React from "react";
import { ShieldAlert, Sparkles, Zap } from "lucide-react";
import { useAutopilot } from "@/components/autopilot-provider";
import type { AccountSlotInfo } from "@/types/autopilot";

function AccountSlotCard({
  slot,
  isActive,
  onSelect,
  disabled,
}: {
  slot: AccountSlotInfo;
  isActive: boolean;
  onSelect: () => void;
  disabled: boolean;
}) {
  return (
    <div
      className={
        isActive
          ? "p-4 rounded-xl border border-emerald-500/40 bg-emerald-500/5 flex items-center justify-between gap-4"
          : "p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex items-center justify-between gap-4"
      }
    >
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm text-slate-100">{slot.label}</span>
          <span
            className={
              isActive
                ? "px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/20 text-emerald-300"
                : slot.status === "COOLDOWN"
                  ? "px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/20 text-rose-300"
                  : "px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-400"
            }
          >
            {isActive ? "ACTIVE" : slot.status}
          </span>
        </div>
        <p className="text-xs text-slate-400">
          Model: <span className="text-slate-300 font-medium">{slot.model_tier}</span> •{" "}
          {slot.configured ? "OAuth Token Đã Lưu" : "Chưa lưu (manage_accounts.py save)"}
        </p>
      </div>

      <div className="flex items-center gap-4">
        <div className="text-right font-mono text-xs">
          <div className="text-slate-200 font-semibold">Calls OK: {slot.calls_succeeded}</div>
          <div className="text-slate-400">Quota Hits: {slot.quota_hits}</div>
        </div>
        {!isActive ? (
          <button
            type="button"
            disabled={disabled}
            onClick={onSelect}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 transition disabled:opacity-50 cursor-pointer"
          >
            Kích hoạt
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function ArgonAccountPanel() {
  const { state, actions, meta } = useAutopilot();
  const router = state.data.ai_summary?.account_router;

  if (!router) {
    return null;
  }

  const slot1 = router.accounts.account_1;
  const slot2 = router.accounts.account_2;

  return (
    <section className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <h2 className="text-base font-semibold text-slate-100">
              Bộ Định Tuyến 2 Tài Khoản Google Argon (Dual-Account Quota Failover)
            </h2>
            <span className="text-xs font-mono text-slate-400">
              Tổng lần tự động đảo nick: {router.total_switches}
            </span>
          </div>
          <p className="text-xs text-slate-400">{router.last_switch_reason}</p>
        </div>

        <button
          type="button"
          disabled={meta.isPending}
          onClick={() => actions.switchArgonAccount("failover")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 transition disabled:opacity-50 cursor-pointer"
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>Mô phỏng Hết Quota (Test Auto-Switch)</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <AccountSlotCard
          slot={slot1}
          isActive={router.active_slot === "account_1"}
          disabled={meta.isPending}
          onSelect={() => actions.switchArgonAccount("account_1")}
        />
        <AccountSlotCard
          slot={slot2}
          isActive={router.active_slot === "account_2"}
          disabled={meta.isPending}
          onSelect={() => actions.switchArgonAccount("account_2")}
        />
      </div>
    </section>
  );
}
