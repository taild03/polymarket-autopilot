# Independent Code Review — Polymarket Autopilot (paper trading)

Reviewer: Claude (Opus 4.8), 2026-10-30. Scope requested: Python paper-trading
engine, ledger/accounting, orderbook execution, risk, settlement, API/OAuth
security, Next.js server bridge, tests, CI. Paper trading only; no UI redesign,
no speculative features.

**Method & honesty note.** Only file tools were available in this session, so I
**did not run** the test suite, the Next.js build, or any network/live cycle.
Every statement below is from source inspection. Fixes I implemented are marked
**FIXED (inspection-verified)**; I added regression tests, but the parent agent
must actually run `python3 -m unittest discover -s tests -v` and
`npm --prefix web run build` to confirm. I preserved the pre-existing uncommitted
fixes in `scripts/doctor.py`, `src/polymarket_client.py` (detailed fallback
errors), `tests/test_operations.py`, and `docs/OPERATIONS_GUIDE.md`, and did not
touch databases, `data/*.json`, `docs/state.json`,
`web/src/data/initial-state.json`, credentials, or untracked handoff docs.

I reviewed the prior handoff claims (AGENTS.md / CLAUDE.md) skeptically and
treated code as authoritative. The headline P0/P1 items the earlier handoff
claims were fixed (no synthetic mark drift, no fake +2.8c probability, per-UUID
position PKs, process lock, offline trading lockout) do appear genuinely present
in the current code.

---

## Findings

### P1-1 — Cached HTTP `Date` ignored `Age`: reference clock lags real time — FIXED (inspection-verified)

**Affected:** `src/polymarket_client.py` (`_extract_server_time`,
`_http_get_with_clock_skew_tolerance`, both the `urllib` and `curl` fallback
paths).

**Trigger / impact.** The engine derives its authoritative "now" (`server_now`)
solely from the origin response's `Date` header and propagates it into
`PaperTrader._now()`, which stamps `generated_at`, the equity-history timestamp,
and drives `days_to_expiry`. The dashboard's freshness label marks state "live"
only when `Date.now() - generated_at <= 120s` (`web/src/components/header-bar.tsx:20`).
Gamma/CLOB responses are frequently served through a CDN/proxy; a cached response
carries the `Date` at which it was *generated* plus an `Age` header for the
seconds it has sat in cache. The code parsed `Date` but **discarded `Age`**, so
on a cache hit `server_now` (and therefore `generated_at`) lagged real time by the
cache residence time — several minutes in practice. This is exactly the
"generated_at/server reference time lag" and "observation freshness vs event API
cache time" concern raised in the task. Concrete effects: fresh cycles can be
mislabeled stale/"CHẾ ĐỘ SNAPSHOT" on the dashboard, equity-history timestamps
drift, and `days_to_expiry` is slightly overstated.

**Fix.** `_extract_server_time` now accepts an optional `Age` value and returns
`Date + Age`. A new `_parse_age_seconds` helper parses a non-negative integer and
accepts values in `[0, 86400]`, ignoring empty/malformed/negative/absurd values (never
subtracting time). Both transport paths now extract and forward `Age` (the curl
path parses the `Age:` header line from the `-D -` dump alongside `Date:`). This
is observation-side only; it changes neither TLS behavior nor trade gating.

**Tests added** (`tests/test_operations.py`):
- `test_server_time_adds_cache_age_and_ignores_garbage` — `Date+Age` arithmetic
  and rejection of malformed/negative/huge/`None` ages.
- `test_fetch_uses_cache_age_for_reference_clock` — end-to-end through
  `_http_get_with_clock_skew_tolerance` with a mocked `urlopen` carrying
  `Age: 420`, asserting `server_now` advances by 7 minutes. TLS stack is not
  touched.

### P2-1 — `ai_summary.timestamp` used the local (skewed) clock — FIXED (inspection-verified)

**Affected:** `src/ai_analyst.py:generate_self_tuning_summary`, `run_autopilot.py`.

**Trigger / impact.** The whole snapshot is stamped with the server-derived clock
via `PaperTrader._now()`, but `generate_self_tuning_summary` stamped its own
`timestamp` with `datetime.now(timezone.utc)`. On this host the OS clock is
deliberately skewed, so `ai_summary.timestamp` disagreed with `generated_at`.
Cosmetic (the freshness gate uses `generated_at`, not this field) but it is the
same class of "which clock is authoritative" inconsistency flagged in the task.

**Fix.** Added an optional `now` parameter (defaulting to `datetime.now` for
backward compatibility) and pass `trader._now()` from `run_cycle`, so the AI
summary stamp matches the snapshot clock.

**Test added** (`tests/test_autopilot.py`):
`test_self_tuning_summary_honors_server_clock`.

---

## Items reviewed and judged correct (verified by inspection only, not fixed)

- **Honest mark-to-market / no synthetic drift.** The live path marks only via
  `PaperTrader.mark_with_books`, which walks real CLOB bid levels for the full
  position size and nets the taker fee; positions without a fully executable
  liquidation quote are deliberately left unmarked and are *not* offered to the
  AI exit manager. `mark_to_market` (Gamma `best_bid`) is used only by unit tests.
- **Entry/exit accounting & fees.** Entry deducts `recommended_size_usdc` from
  cash and sets `cost_basis = recommended_size`, `shares = size/entry_price`; the
  per-leg taker fee is baked into `entry_price` (strategy engine) and
  `ExecutionBooks.validate` re-checks that live ask-depth cost + fee ≤ budget.
  Exit credits the fee-netted proceeds and `realized += proceeds − cost_basis`.
  Settlement mirrors this. No double counting (`current_exposure`, `reserved_cash`,
  and `open_market_value` net out in `total_equity`).
- **Pending maker lifecycle.** `record_and_execute` reserves cash as a
  `PENDING_MAKER`; `process_lifecycle` cancels+refunds on leg close/expiry, and
  fills to `OPEN` only when `cost_for_quantity(asks, shares, limit=entry_price)`
  can fill the full size at/below the resting price (no cross). The drawdown
  kill-switch cancels pending orders before new fills in `run_cycle`.
- **Stale quotes / liquidity reuse.** `ExecutionBooks` builds a fresh per-cycle
  cache keyed by token id (YES vs NO tokens tracked separately, so NO positions
  liquidate against NO bids). Duplicate market exposure — including a bundle leg
  that overlaps an existing single position or another bundle — is blocked by the
  `open_ids | held_market_ids()` guard re-evaluated each signal iteration, so the
  same book is not reused to open two colliding positions.
- **Duplicate bundle legs.** `_scan_bundle_arbitrage` requires the active,
  non-closed, Yes/No leg count to equal the event's `outcomes_count_in_event`,
  preventing partial baskets; bundle marks/settlement track exact `leg_market_ids`.
- **Settlement finality.** Settlement requires `closed AND settlement_yes is not
  None` for every leg and is idempotent (closed rows are never re-queried); a
  total-loss settlement correctly books `realized = −cost_basis`
  (`test_settlement_requires_confirmed_result_and_is_idempotent`).
- **Concurrency.** `run_cycle` holds `fcntl.flock(LOCK_NB)` and returns the last
  persisted snapshot if a cycle is already running; SQLite connections use a 15s
  busy timeout. The server's worker thread and `/api/scan` contend on the same
  lock.
- **HTTP / API security.** `server.AutopilotRequestHandler._authorized` enforces
  an Origin allowlist, constant-time bearer-token comparison, and refuses
  non-loopback clients when no token is set; `main()` refuses to bind a non-loopback
  interface without `AUTOPILOT_API_TOKEN`. CORS `Access-Control-Allow-Origin` is
  reflected only for allowlisted origins. The Next.js route (`web/src/app/api/autopilot/route.ts`)
  blocks cross-origin and Vercel POSTs and keeps the backend token server-side
  only. Body size/content-type are validated before a cycle runs.
- **TLS never disabled.** The curl fallback never passes `-k`/`--insecure`
  (asserted by `test_tls_fallback_never_disables_verification`); DoH answers are
  filtered to globally-routable A records.
- **OAuth callback.** `manage_accounts.valid_oauth_callback` checks the exact
  path and compares `state` with `secrets.compare_digest`.
- **Credential-switching truthfulness.** `runtime.can_switch_accounts` is always
  `false` and the dashboard's account switch action only shows an instructional
  message; no HTTP route copies or swaps OAuth tokens.

---

## Unresolved limitations / lower-severity notes (pre-existing, not changed)

These are pre-existing behaviors I chose **not** to change because fixing them
would alter trade/kill-switch semantics or exceed the "no redesign" scope. They
are documented here and in README/OPERATIONS_GUIDE.

1. **`metrics["daily_pnl_usdc"]` is actually intraday peak-drawdown, not daily
   P&L.** `get_account_metrics` returns `min(total_equity − day_start,
   total_equity − day_peak)`, i.e. drawdown from the intraday high-water mark. This
   is the *correct, more conservative* input for the 3% kill-switch it feeds (both
   the `run_cycle` pre-cycle cancel and `RiskManager`), but the field name is
   misleading for any external reader of `/api/state` (it reads 0 when equity is at
   a new high even if up intraday). I did not rename/split it to avoid changing
   kill-switch behavior; `drawdown_from_peak_usdc` and `daily_risk_reference_usdc`
   are reported alongside. Recommend a future rename to `daily_drawdown_usdc` plus a
   separate true `daily_pnl_usdc`.
2. **Stale marks in reported equity.** Open positions that cannot be fully
   liquidated against current CLOB bids keep their last mark, so `total_equity` can
   include a stale component. This is intentional (the AI is correctly barred from
   exiting such positions) and documented, but consumers should treat equity for
   illiquid holds as last-known rather than live.
3. **Narrow settlement recognition.** Settlement is recognized only when resolved
   `outcomePrices` are exactly `(1,0)`, `(0,1)`, or `(0.5,0.5)`. Other resolved
   encodings leave the position `OPEN` rather than fabricating a payout
   (conservative, but such positions can linger until the orderbook also clears).
4. **Static fee / fill model.** Taker fee is a fixed bps buffer; there is no queue
   priority, partial fills, or latency modeling. Already stated as a limitation in
   README/OPERATIONS_GUIDE.
5. **Marketing copy in AI summary.** `generate_self_tuning_summary` always narrates
   "auto-failover between two Argon accounts" regardless of whether `account_2` is
   configured. Harmless (the honest `can_switch_accounts: false` governs behavior),
   but the prose overstates capability.
6. **First `increment_cycle` of a run uses the local clock** because `server_now`
   is only known after the Gamma fetch; every subsequent timestamp in the cycle uses
   server time. Negligible.

---

## Summary

The engine is in substantially better shape than a skeptical reading of the old
handoff would suggest: mark-to-market is honest against live CLOB depth, entry/exit
and fee accounting net out correctly, the pending-maker and settlement lifecycles
are idempotent and conservative, duplicate-leg and offline-trading guards hold, and
the API/OAuth/TLS surface is sensibly locked down. I found and fixed one P1
correctness bug — the cached-`Date` reference-clock lag (missing `Age` handling),
which directly caused the `generated_at`/freshness drift called out in the task —
plus one related P2 clock-consistency inconsistency in the AI summary stamp, each
with a focused regression test. No P0 issues were found on inspection. Remaining
items are documented limitations (clock-of-record edge cases, static fee/fill
model, conservative settlement, and the mislabeled `daily_pnl_usdc` field) rather
than active defects. The parent agent should run the Python test suite and the
Next.js build to confirm the two fixes and their tests, since I was unable to
execute anything in this session.

## Parent-agent validation

Codex independently ran the Python suite after these changes: **27 tests passed**.
A real Gamma response returned `Date: Fri, 30 Oct 2026 08:18:02 GMT` and
`Age: 101` at local UTC `2026-10-30T08:19:43`, confirming that Date + Age
corrects the observed clock lag. This confirms observation time, not that cached
Gamma prices are newly generated; order execution still validates CLOB depth.

The production Next.js build and TypeScript check also passed; `git diff --check` was clean.
