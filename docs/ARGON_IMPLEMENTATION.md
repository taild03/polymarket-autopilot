# Argon entry-review gate — change summary & verification

Paper trading only. This change makes a **genuine Argon assessment mandatory before any new
paper money is reserved (maker) or spent (taker)**, using the two logged-in Google profiles
with bounded quota failover. It replaces the previous behaviour where the entry path audited
only rule *clarity* and silently fell back to deterministic rules.

## What changed

- **`src/argon_entry.py` (new, replaces the untracked draft)** — `ArgonEntryGate` + `EntryReview`.
  - Submits the WHOLE order (every bundle leg, chosen YES/NO side, current entry price,
    resolution rules, expiry/liquidity, proposed risk/size) to `agy` and asks it to critique
    **economic merit**, not just clarity.
  - CLI flags: `--model gemini-4-argon-high --mode plan --sandbox --disable-slash-commands -p <prompt>
    --output-format json --json-schema <schema> --print-timeout <n>s`. Runs in an empty temp cwd.
    Never uses any "skip permissions" flag. The subprocess is injectable (`runner=`) so tests
    never shell out or read credentials.
  - Strict schema/parse validation: required fields, finite numbers, bounded ranges, typed
    `risks`. Invalid JSON / NaN / non-zero exit / timeout → `UNAVAILABLE` → entry blocked.
  - Explicit statuses: `APPROVE` / `REJECT` / `INSUFFICIENT_DATA` / `UNAVAILABLE`. Strategy
    fair_value and market price are declared assumptions, not evidence. The context sets
    `independent_research_available=false`; an `APPROVE` that admits no independent research
    is downgraded to `INSUFFICIENT_DATA` in code (no invented news/sources/probabilities).
  - Two-profile routing: uses the active configured account; on a genuine quota/rate-limit
    error performs exactly one retry on the configured, non-cooling alternate; both unusable
    → block. Counters increment only on a genuinely parsed response.
  - Bounded per cycle (`argon_max_calls_per_cycle`, `argon_cycle_time_budget_sec`); over budget
    → remaining signals blocked (`CYCLE_BUDGET_EXHAUSTED`), never deferred. In-memory cache is
    keyed by price/side/model/account/context with a short TTL and dies on restart, so no stale
    cache can authorize a new trade.

- **`src/account_router.py`** — added `active_eligible_slot()` / `eligible_alternate()`
  (credential-free), and removed the language that implied a deterministic fallback approval
  when no backup is available (now explicitly "block new entries").

- **`src/config.py`** — new fields: `require_argon_entry_review` (default **True**),
  `argon_cli_bin`, `argon_model` (`gemini-4-argon-high`), timeouts, per-cycle call/time budgets,
  cache TTL, and `argon_approval_ttl_sec`.

- **`src/paper_trader.py`**
  - New `positions` columns `entry_review_status/model/account/at/expires_at` (pre-gate rows
    default to `''` = unreviewed, never treated as approved).
  - `record_and_execute(..., entry_review=, approval_expires_at=)` stamps provenance and logs an
    `ARGON_ENTRY_REVIEW` row (provider/model/account/reasons/risks).
  - `migrate_legacy_pending_orders()` cancels & refunds pre-gate `PENDING_MAKER` orders.
  - `cancel_expired_pending_reviews()` refunds pending orders whose approval TTL lapsed.
  - `process_lifecycle` only fills `PENDING_MAKER → OPEN` with a non-expired `APPROVE`
    (execution-boundary gate). Open positions, exits and settlement are untouched.
  - `export_full_state(..., entry_review=)` publishes the truthful entry-review summary.

- **`run_autopilot.py`** — default entry path now: risk sizing → pre-inference CLOB depth →
  mandatory Argon review → conservative re-size from the chosen-side probability (never larger
  than initial) → **re-fetch CLOB after inference** and re-validate → execute only if still
  valid. Runs the legacy-pending migration and expired-approval refund each cycle. Deterministic
  exits remain separate from genuine entry inference.

- **Dashboard (`web/`)** — new `EntryReviewStatus` panel (mode/model/CLI/calls/approve-block
  counts, per-review status + account + reasons), entry-review styling in the AI feed, and
  `entry_review*` types. Minimal, no redesign. (Note: `vercel-react-best-practices/SKILL.md` is
  outside the sandbox and could not be read; React changes were kept minimal and match existing
  conventions.)

- **Docs** — `.env.example` and `docs/OPERATIONS_GUIDE.md` §5 document default behaviour, bounds,
  the no-news-research limitation, account routing and how to inspect decisions.

## Tests

`tests/test_argon_entry.py` (new, isolated — fake runner, isolated router, temp DBs; no CLI,
network, credentials or production data):

- approve / reject / insufficient-data / unavailable / invalid-JSON / NaN / non-zero exit
- correct NO and bundle side context
- two-account quota retry; blocked when backup is unconfigured or in cooldown; only one retry
- no reuse of a stale approval (cache hit within TTL, miss on price change, miss after TTL)
- legacy pending refund; approved-pending fill vs expired-approval refusal + refund
- fresh-book re-validation blocking stale authorization
- per-cycle budget blocking deferred signals

Existing suites are preserved; component tests that fill maker orders now run in explicit
deterministic mode (`require_argon_entry_review=False`).

## Verification (run by the parent — needs shell/network/CLI)

```bash
cd /Users/taileduc/Personal/polymarket-autopilot
python3 -m unittest discover -s tests -v        # all suites incl. test_argon_entry
npm --prefix web run build                       # dashboard type-check/build
python3 scripts/doctor.py --network              # live Gamma/CLOB reachability
# Live probe of the gate (real agy, real profiles). Expect mostly INSUFFICIENT_DATA given no
# news provider; confirm no trade opens without an APPROVE and that quota failover switches
# accounts. Inspect data/portfolio_state.json -> entry_review, and ai_brain_log rows.
python3 run_autopilot.py --limit 40
```

Do NOT reset `data/*.db` or the JSON snapshots to verify; the ledger is authoritative.
