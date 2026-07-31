# Design: issue-347-c2-production-quota-domain-gate-for-auto

## Current state

The communication agent's safety machinery today, all verified in the clone:

- **Policy engine** (`internal/agent/policy/policy.go`, `Evaluate`) is a pure
  function taking `Input{Profile, Conversation, Action, RecentAgentSends,
  GlobalKill, Now}`. It already denies on `GlobalKill`, `Profile.Mode ==
  off`, `Profile.AutopilotPaused`, conversation state, blocked senders, and
  requires approval (in guarded mode) when `MaxAutonomousTurns` is exhausted
  or `overRate(RecentAgentSends, MaxMsgsPerMinute, Now)` trips. `overRate`
  only knows a **one-minute** window — there is no hour/day ceiling anywhere
  in the codebase today.
- **Modes** (`internal/db/agent_domain.go`): `AgentModeObserve` (never
  auto-send, C1), `AgentModeGuarded` (allowlisted discovery intents may
  auto-send — this is the plan's "guarded autopilot" and what issue #347
  calls "C2 autopilot mode"), `AgentModeOff`. There is no fourth mode; C2 is
  the production promotion of `guarded`, not a new mode.
- **`agent_profiles`** (`internal/db/agent_schema.go` CREATE TABLE,
  `internal/db/agent_domain.go` `AgentProfile` struct) already carries
  `mode`, `autopilot_paused`, `max_autonomous_turns`, `max_msgs_per_minute`,
  `max_reply_chars`, `intent_allowlist`, `blocked_senders`,
  `sender_allowlist`. `EnsureAgentProfile` (`agent_domain.go`) inserts new
  rows with `autopilot_paused = true` unconditionally (explicit column
  value, documented as intentionally overriding the schema default) — the
  issue's "autopilot_paused must default to true for any new account"
  requirement is **already satisfied structurally** and must not regress.
- **Rate enforcement at send time** (`internal/db/agent_actions.go`,
  `ReserveAgentActionSend`) is the authoritative, crash-safe reservation: it
  locks the `conversations` row (`FOR UPDATE` on Postgres), re-checks
  `MaxAutonomousTurns` and a `maxMsgsPerMinute` window computed by counting
  `conversation_messages` (outgoing) plus in-flight `agent_actions` rows in
  `executing`/`denied` since `rateWindowStart`, and only then flips the
  action to `executing`. This is **per-conversation only** — there is no
  per-account aggregate across a user's conversations. `internal/agent/executor/executor.go`'s
  `send()` calls it with `time.Now().UTC().Add(-time.Minute)` as the window
  start (hardcoded to one minute, matching the one policy dimension that
  exists today).
- **Kill switch today is single and global**: `AGENT_KILL_SWITCH`
  (`internal/config/config.go`, `Config.AgentKillSwitch`, env-only, read
  once at boot) is checked via `Executor.GlobalKill()` and fed into
  `policy.Input.GlobalKill`. `docs/runbook.md`'s "Communication Agent
  operations" section documents it as one of four independent containment
  controls (kill switch, `listener_enabled`, `autopilot_paused`, worker
  replica count), explicitly manual, requiring a reviewed deployment change
  to flip. There is no automatic trip path anywhere in the codebase.
- **Cost accounting exists only at the single-job level**: `internal/agentworker/claudeinvoker.go`'s
  `ClaudeInvoker.MaxBudgetUSD` (env `AGENT_MAX_BUDGET_USD`,
  `cmd/agent-worker/main.go`) passes `--max-budget-usd` to `claude -p` so
  **one job** cannot overspend. `internal/agentworker/worker.go` parses
  `total_cost_usd` out of the CLI's JSON result (`TotalCostUSD float64`),
  but nothing persists or aggregates it: it is not written to `agent_jobs`,
  not summed anywhere, and not compared against any rolling ceiling. There
  is no mechanism today that could notice "this account has spent $40 in
  the last hour" and act on it.
- **Admin-driven profile changes are audited generically**:
  `internal/agentapi/profilehandler.go`'s admin upsert handler calls
  `store.LogToolCall(ctx, id.UserID, "admin.agent_profile.upsert", "", ...)`
  (`internal/db/store.go:1035`) for every profile write, including a mode
  flip to `guarded` or an `autopilot_paused` flip. This is one flat
  audit event name for all profile edits — there is no dedicated,
  distinctly-named audit trail specifically for "this account was just
  opted into C2."
- **Metrics and alerting conventions**: `internal/metrics/metrics.go`
  defines `AgentEventsReceivedTotal`, `AgentJobsTotal`, `AgentDeadLetterTotal`,
  `AgentActionsExecutingStuck`, `AgentApprovalLatencySeconds`,
  `AgentExecutorRestartsTotal` — all low-cardinality (no per-user labels
  anywhere in the file). `deploy/alerts/mctl-telegram.rules.yaml` is a
  `PrometheusRule` CRD with a dedicated `mctl-telegram-agent` rule group
  (`MctlAgentDeadLetter`, `MctlAgentActionsExecutingStuck`) and a
  fast-burn/slow-burn pattern elsewhere in the same file
  (`mctl-telegram-tool-availability`) for approaching-vs-breaching an SLO
  budget — that two-tier pattern is the existing precedent to reuse for
  "approaching vs breaching" a C2 ceiling. There is no C2-specific metric or
  alert today.
- **Migrations are hand-rolled and additive**
  (`internal/db/agent_schema.go`, `addColumnIfMissing`, called from
  `migrateAgentDomain`/`Migrate()`), idempotent on every boot, following the
  `internal/db/refresh_tokens.go` precedent noted in the plan doc. New
  columns get conservative defaults so an un-migrated or freshly-created
  profile is never looser than intended.

## Proposed solution

Add a distinct **C2 quota-domain gate** as a new layer that sits alongside
(not inside) the existing policy engine, reusing its established patterns
rather than inventing new ones.

### 1. Schema: per-account/per-conversation ceilings and C2 state

Extend `agent_profiles` (via `addColumnIfMissing`, same as the existing
`sender_allowlist`/`owner_profile_encrypted` additions) with:

- `max_msgs_per_hour INTEGER NOT NULL DEFAULT 0` and
  `max_msgs_per_day INTEGER NOT NULL DEFAULT 0` (account-scoped; `0` means
  "C2 not configured, see opt-in gate below" — mirrors how `MaxMsgsPerMinute
  <= 0` today falls back to a default inside `UpsertAgentProfile`, except
  here `0` is a deliberate "not opted in" sentinel, not a fallback-to-2).
- `max_cost_usd_per_day REAL NOT NULL DEFAULT 0` — the account's C2-scoped
  spend ceiling, independent of the org-wide Agent SDK cap and independent
  of the per-job `AGENT_MAX_BUDGET_USD`.
- `c2_kill_switch_tripped_at TIMESTAMPTZ`, `c2_kill_switch_reason TEXT NOT
  NULL DEFAULT ''`, `c2_kill_switch_tripped_by TEXT NOT NULL DEFAULT ''`
  (`'system'` or an admin identity) — the new, per-account, auto-trippable
  kill switch, distinct from `AGENT_KILL_SWITCH`.
- `c2_enabled_at TIMESTAMPTZ`, `c2_enabled_by TEXT` — set only by the
  dedicated opt-in path (see below), never by the generic profile upsert.

Add `agent_jobs.cost_usd REAL` (same `addColumnIfMissing` pattern as the
existing `agent_jobs.result_action_id`/`result_lead_id` additions) so a
completed job's `total_cost_usd` (already parsed in
`internal/agentworker/worker.go`) is persisted durably instead of only
existing in a log line. `internal/agentapi`'s job-completion handler writes
it alongside `result_action_id`/`result_lead_id`.

### 2. Enforcement: extend the existing reservation pattern to hour/day and to account scope

`ReserveAgentActionSend` already does the crash-safe, transaction-locked
windowed count for the one-minute case. Extend it (or add a sibling method
following the identical shape) to also check, still inside the same locked
transaction:

- **Per-conversation hour/day**: same query shape as the existing
  `maxMsgsPerMinute` count, parameterized by window (`rateWindowStart`
  already is a parameter — the caller just needs to run it three times, or
  the query is rewritten to count all three windows in one round trip).
- **Per-account hour/day**: the same count shape but scoped by `user_id`
  across all of that account's conversations rather than one
  `conversation_id`. This requires locking at the account level for the
  duration of the check — reuse the existing per-conversation `FOR UPDATE`
  approach but add a `SELECT ... FROM agent_profiles WHERE user_id = $1 FOR
  UPDATE` row lock (the profile row already exists and is read once per
  send) as the account-level serialization point, avoiding a new lock
  primitive.
- **C2 kill switch check**: add `c2_kill_switch_tripped_at IS NOT NULL` as
  an immediate deny, checked first (cheapest, no counting needed), mirroring
  how `policy.Evaluate` checks `GlobalKill` before anything else.

`policy.Evaluate`'s `Input` gains a `C2KillSwitchTripped bool` field (set
from the profile, not a second I/O call) so the pure policy function keeps
denying/requiring-approval consistently with `executor.send()`'s later
reservation check — same "policy re-checked, then reservation re-checked
atomically at send time" two-layer pattern the codebase already uses for
`MaxMsgsPerMinute` (`policy.Evaluate`'s `overRate` is the cheap first
check; `ReserveAgentActionSend` is the authoritative atomic one). The hour/
day/account ceilings follow the identical two-layer shape.

### 3. Automatic trip path: a periodic anomaly sweep

Add a new sweep function in `internal/agent/executor` (or a small sibling
package, e.g. `internal/agent/quota`), following the exact operational
pattern of `Executor.RecoverStuck` — called periodically from a goroutine in
`cmd/server/main.go` alongside the existing `RecoverStuck` ticker. Each
tick, per account with `mode = guarded && !autopilot_paused &&
c2_kill_switch_tripped_at IS NULL`:

- Count recent `agent_actions` with `status = denied` in a short rolling
  window (e.g. last 10 minutes) — if it exceeds a configured threshold,
  trip the C2 kill switch with reason `"repeated policy denials"`.
- Compare the account's rolling send count (already computable via the same
  per-account hour-window query added in step 2) against its own
  `max_msgs_per_hour` ceiling times a configured anomaly multiple (e.g. the
  account is sending at >2x its steady-state ceiling within a short
  sub-window) — trip with reason `"abnormal send velocity"`.
- Sum `agent_jobs.cost_usd` for the account's C2-scoped jobs (jobs belonging
  to conversations under a `guarded`-mode, C2-opted-in profile) in the
  rolling day window; if it exceeds `max_cost_usd_per_day`, trip with reason
  `"cost ceiling exceeded"`.

Tripping is a single `UPDATE agent_profiles SET c2_kill_switch_tripped_at =
now(), c2_kill_switch_reason = $1, c2_kill_switch_tripped_by = 'system'
WHERE user_id = $2 AND c2_kill_switch_tripped_at IS NULL` — idempotent,
first-trip-wins, same shape as the existing CAS-style updates in
`agent_actions.go`. Each trip is logged via `LogToolCall(ctx, userID,
"agent.c2_kill_switch.auto_trip", "", "tripped", reason, "")` so it lands in
the same audit surface operators already query.

Clearing a trip is a **manual-only**, admin-API, audited action
(`admin.agent_c2_kill_switch.clear`) that requires the account id and
records the actor — never automatic, matching the issue's "hard kill-switch
semantics" framing (auto-trip yes, auto-clear no).

### 4. Cost ceiling scoped specifically to C2 traffic

The org-wide Agent SDK spend cap lives in mctl-agents and is out of this
repo's control. This proposal's cost ceiling is a **second, narrower gate**:
`max_cost_usd_per_day` on the account profile, enforced against the newly
persisted `agent_jobs.cost_usd` sum (step 1/3), independent of whatever the
upstream pool's remaining balance is. The existing per-job
`AGENT_MAX_BUDGET_USD`/`--max-budget-usd` remains as the pre-flight
worst-case backstop on any single job; the new rolling ceiling is the
aggregate backstop across all of an account's C2 jobs. Both are necessary:
the per-job cap bounds one runaway invocation, the rolling ceiling bounds
the account's cumulative C2 footprint against the pool other services
share.

### 5. Alerting

New collectors in `internal/metrics/metrics.go`, matching the existing
naming/cardinality conventions (no per-user labels; aggregate gauges/
counters only, since Prometheus cardinality concerns already shape every
existing metric in that file):

- `AgentC2KillSwitchTrippedTotal *prometheus.CounterVec` (label `reason`) —
  incremented on every automatic trip.
- `AgentC2SpendRatioMax prometheus.Gauge` — the highest
  `spend/max_cost_usd_per_day` ratio across all C2-opted-in accounts on the
  most recent sweep tick (mirrors `AgentActionsExecutingStuck`'s "gauge set
  by the periodic sweep" shape).
- `AgentC2RateRatioMax *prometheus.GaugeVec` (label `window` =
  `hour`/`day`) — the highest ceiling-utilization ratio across accounts, per
  window.

New rules in `deploy/alerts/mctl-telegram.rules.yaml`, added to the existing
`mctl-telegram-agent` group, following the file's own two-tier
approach-then-breach pattern (already used for tool-availability burn
rates):

- `MctlAgentC2CeilingApproaching` (`severity: warning`) — any ratio gauge
  `> 0.8`.
- `MctlAgentC2CeilingBreached` (`severity: critical`) — any ratio gauge
  `>= 1.0` (in practice this should rarely fire since the reservation itself
  denies at the ceiling — it exists as a defense-in-depth signal that the
  gate itself may have a bug).
- `MctlAgentC2KillSwitchTripped` (`severity: critical`) — `increase(mctl_agent_c2_kill_switch_tripped_total[15m])
  > 0`, same shape as the existing `MctlAgentDeadLetter` rule.

### 6. Explicit, audited C2 opt-in

Add a dedicated admin endpoint (or a distinguished request shape on the
existing admin profile endpoint in `internal/agentapi/profilehandler.go`)
that is the **only** path allowed to transition an account to `mode =
guarded && autopilot_paused = false` simultaneously. It:

- Requires `max_msgs_per_hour`, `max_msgs_per_day`, and
  `max_cost_usd_per_day` to already be non-zero for the account (reject the
  transition otherwise — this is the schema-level guarantee that C2 cannot
  go live without ceilings configured).
- Requires `c2_kill_switch_tripped_at IS NULL` (cannot opt in over a
  tripped state without first clearing it explicitly).
- Writes `c2_enabled_at`/`c2_enabled_by` and a dedicated audit entry
  `LogToolCall(ctx, userID, "admin.agent_c2.enable", "", "ok", "", "")`,
  distinct from the generic `admin.agent_profile.upsert` event so operators
  can find every C2 activation without filtering through routine profile
  edits.
- The existing generic profile-upsert path is still used for every other
  field edit and for any transition that does *not* simultaneously flip
  both `mode` and `autopilot_paused` into the live-C2 state (e.g. adjusting
  `intent_allowlist` on an already-opted-in account stays on the generic
  path).

`EnsureAgentProfile`'s `autopilot_paused = true` default is unchanged — this
proposal only adds a gate in front of the one path that could flip it to
`false` for a guarded-mode account, it does not touch profile creation.

## Alternatives

1. **Enforce the cost/rate ceiling entirely at the mctl-agents org level
   instead of adding a domain-specific gate in mctl-telegram.** Rejected:
   the issue explicitly asks for a gate "separate from and in addition to
   the existing org-wide Agent SDK spend cap." An org-wide cap has no
   visibility into per-conversation state, policy denials, or Telegram send
   velocity — those signals only exist in mctl-telegram. A shared upstream
   cap is also the wrong place to encode "pause *this* account," which needs
   to reach `policy.Evaluate` and `ReserveAgentActionSend` directly.

2. **A distributed/Redis-backed token-bucket rate limiter instead of the
   DB-transaction windowed-count pattern.** Rejected for this proposal: the
   codebase has no Redis dependency today. `internal/audit.RateLimiter` is
   an in-process, per-replica token bucket used for read-side API rate
   limiting, not agent sends — it is explicitly documented elsewhere as
   insufficient for cross-replica send accounting, which is exactly why
   `ReserveAgentActionSend` uses a DB transaction with row locking instead.
   Reusing that established, crash-safe, multi-replica-correct pattern for
   the new hour/day/account windows is more consistent than introducing a
   new stateful dependency for one feature.

3. **Overload `AGENT_KILL_SWITCH` itself with per-account and automatic-trip
   semantics instead of adding a second kill switch.** Rejected: the issue
   explicitly asks for a switch "distinct from AGENT_KILL_SWITCH (which is
   binary/global)." `AGENT_KILL_SWITCH` is documented in `docs/runbook.md`
   as one of four independent, manually-operated containment controls with
   an established operational runbook (dark-start procedure, safe-close
   procedure). Changing its semantics to be per-account and
   automatically-settable would break that documented contract and the
   existing operational muscle memory (and the existing tests that assert
   its current global/env-only behavior).

## Platform impact

- **Migrations**: all additive `addColumnIfMissing` calls
  (`max_msgs_per_hour`, `max_msgs_per_day`, `max_cost_usd_per_day`,
  `c2_kill_switch_tripped_at`, `c2_kill_switch_reason`,
  `c2_kill_switch_tripped_by`, `c2_enabled_at`, `c2_enabled_by` on
  `agent_profiles`; `cost_usd` on `agent_jobs`), run inside the existing
  hand-rolled, idempotent `Migrate()` path. No backfill needed — all new
  columns default to zero/empty/NULL, which is the correct "not configured,
  not C2" state for every existing account.
- **Backward compatibility**: every account currently in `observe` or `off`
  mode is entirely unaffected — the new gate only activates on the specific
  `mode=guarded && !autopilot_paused` transition, which per the current C1
  report has never yet been reached in production. C1's existing behavior
  (`EnsureAgentProfile` defaulting `autopilot_paused=true`,
  `AGENT_KILL_SWITCH` semantics, `MaxMsgsPerMinute` enforcement) is
  unchanged; this is a strictly additive gate in front of a transition that
  does not exist in production traffic yet.
- **Resource impact**: the per-account hour/day count adds one more locked
  read inside the existing `ReserveAgentActionSend` transaction (already
  doing a `FOR UPDATE` conversation lock and a windowed count query) — bound
  and proportional to existing send volume, not a new hot path. The anomaly
  sweep is a periodic goroutine over C2-opted-in accounts only (expected to
  be a small set during the guarded rollout), following the same cost
  profile as the existing `RecoverStuck` sweep. New Prometheus series are
  fixed-cardinality (a handful of gauges/counters, no per-account labels).
- **Risks and mitigations**:
  - *False-positive automatic trip stalls a healthy account.* Mitigated by
    making the trip reason explicit and auditable, and by keeping manual
    clear cheap (one audited admin call) — a false positive costs an
    operator one intervention, not data loss or a stuck state, matching the
    "fail closed" posture already used throughout the executor (e.g.
    `requireApprovalBypassesUnreviewedAllow` in `executor.go`).
  - *Account-level lock contention if one account has many concurrent
    conversations sending simultaneously.* Mitigated by reusing the same
    row-lock granularity (`agent_profiles` row per user) the codebase
    already accepts for the conversation-level lock in
    `ReserveAgentActionSend`; C2 accounts are expected to be low in number
    and moderate in per-account concurrency during the guarded rollout, and
    the plan's own single-replica listener constraint already bounds
    concurrent write pressure.
  - *Clock skew across replicas for hour/day window boundaries.* Mitigated
    by keeping the same `time.Now().UTC()` application-side windowing the
    codebase already uses for the one-minute window (`executor.go`,
    `time.Now().UTC().Add(-time.Minute)`) rather than introducing
    database-server-time semantics only for the new windows — consistent
    behavior beats mixed clock sources for a single feature.
  - *A job's cost is only known after it completes*, so the cost ceiling is
    necessarily a rolling-window check against completed jobs, not a
    pre-flight guarantee for the job about to run. Mitigated by keeping the
    existing per-job `--max-budget-usd` hard cap as the pre-flight backstop
    (already true today) and treating the rolling ceiling as the aggregate
    backstop, exactly as scoped in "Proposed solution" step 4 — this is a
    deliberate design trade-off, not an oversight, and is recorded in Open
    Questions in requirements.md.
