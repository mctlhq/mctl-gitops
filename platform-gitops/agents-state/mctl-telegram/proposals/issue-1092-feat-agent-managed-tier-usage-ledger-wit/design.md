# Design: issue-1092-feat-agent-managed-tier-usage-ledger-wit

## Current state

Slice 2 of ADR 0008 (pool credential and managed claim) is merged. The pieces
this slice touches:

- `internal/db/agent_managed_claim.go` `ListManagedClaimCandidates`: a
  lock-free keyset query over `agent_profiles`, `users` and `agent_jobs`
  (runtime `managed`, current consent, a claimable due job, a Telegram login
  id, in-flight below the cap). The query has the placeholder line
  `-- budget filter (budget_paused_until, slice 4, #1092) goes here`.
- `internal/db/agent_jobs.go` `ClaimManagedAgentJobs` calls
  `claimAgentJobs(..., RuntimeManaged, limit, maxInflight)`. When
  `maxInflight > 0` it calls `reserveInflight`, which takes
  `pg_advisory_xact_lock(hashtextextended('mctl-telegram:managed-claim:<uid>'))`
  and counts processing jobs, then runs the `WITH due AS (... FOR UPDATE SKIP LOCKED) UPDATE agent_jobs ... runtime = $7`
  claim. The coalesced path `claimCoalesced` (`internal/db/agent_turn_claim.go:60`)
  calls `reserveInflight` the same way. SQLite runs on one connection, so the
  transaction alone serializes there.
- `RecordAgentJobCost` (`agent_jobs.go:786`): `UPDATE agent_jobs SET cost_usd`
  fenced on `id, user_id, attempts`. No ledger exists.
- `RequeueStaleAgentJobs` (`agent_jobs.go:950`) collects `fencedIDs`,
  `deadIDs` and `requeuedIDs` in one transaction and closes their attempt rows.
  `ReleaseUnissuedClaim` (`agent_jobs.go:878`) decrements `attempts` and
  deletes the open attempt row, so the next claim reuses that attempt number.
- `purgeAgentJobs` (`agent_jobs.go:1066`) locks `agent_jobs`, then deletes
  `agent_job_attempts` and `agent_jobs`. It is registered as `purgeAgentJobsHook`
  for `purgeAgentData` (`agent_domain.go:736`).
- `RouteUnclaimedAgentJobs` (`internal/db/event_outbox.go:183`) moves pending
  jobs with `attempts = 0` that are older than `after` to `routed`. It has no
  runtime or budget awareness.
- Schema: `agent_profiles.budget_paused_until` already exists
  (`agent_schema.go:183-184`, commented "unused in this slice") and is read
  into `AgentProfile.BudgetPausedUntil` (`agent_domain.go:93-94,168,184`).
  New columns use `addColumnIfMissing`. Tables are declared twice:
  `agentSchemaSQLite()` (line 451) and `agentSchemaPG()` (line 836).
- Owner notifications: `owner_notifications` and `InsertOwnerNotification`,
  `HasOwnerNotificationSince` and kinds `NotificationSummary`, `Approval`,
  `Alert` and `HumanInput` (`internal/db/agent_actions.go:1390`). Delivery is
  handled by the existing notifier sweep.
- Handler: `internal/agentapi/events.go` `handleReportJobCost` decodes
  `reportJobCostRequest{Attempt, CostUSD}` with `decodeStrict`, then runs
  `enforceBinding(..., jobID, req.Attempt)` (`binding.go:34`, which compares
  against `id.JobID` and `id.JobAttempt`), then `GetAgentJob` and
  `RecordAgentJobCost`, then audits `report_agent_job_cost`.
  `poolClaimOne` (`events.go:~575`) builds the `jobEnvelope` (`events.go:30`).
- Server config: `ManagedClaimConfig{MaxInflightPerAccount, Revocations}`
  (`internal/agentapi/server.go:130`), wired by `wireManagedPool`
  (`cmd/server/managedpool.go`) from `config.Config.ManagedMaxInflightPerAccount`
  (`internal/config/config.go:479,570,653`).
- Admin route: `NewAdminAgentProfileHandlerWithManaged`
  (`internal/agentapi/profilehandler.go:109`) under the `admin:users` scope
  already handles `runtime`.
- Worker: `Client.ReportJobCost` (`internal/agentworker/client.go:463`) sends
  `{attempt, cost_usd}`. `recordRunCost` (`finishrun.go`) calls it. The client
  already retries `/complete` once with a legacy body on 400
  (`client.go:~455`). `ClaudeResult` carries only `TotalCostUSD`. The OpenAI
  runner tracks `out.Usage` and `Prices.Cost` (`openairunner.go:132-147`).
- Metrics: `internal/metrics/metrics.go` has `mctl_agent_job_cost_usd_total{result}`
  and no usage or budget metrics.
- Tests: `internal/db/agent_managed_cap_test.go` has the Postgres harness
  `newFreshSchemaPostgresStore` (skips without `TEST_DATABASE_URL`) and
  `TestClaimManagedAgentJobs_InflightCap_Postgres` as the concurrency pattern.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` and
  `services/labs/mctl-telegram/values.yaml`: `EVENTS_OPERATOR_ROUTING: "true"`
  and `AGENT_UNCLAIMED_ROUTE_AFTER: "5m"` in both. Operator routing is live, so
  the `RouteUnclaimedAgentJobs` budget skip has a real effect.
- A grep for `MANAGED_` across `$MCTL_GITOPS_ROOT/services` matched nothing.
  The managed runtime flag and caps are not set anywhere, so this slice ships
  dark (default flag off).
- `services/labs/agent-worker-preview/values.yaml`: `AGENT_MAX_BUDGET_USD: "0.50"`.
  This is the basis for the proposed `MANAGED_MAX_JOB_COST_USD` default.
- The mctl MCP tools were not called. The gitops files above were enough for
  the env facts this design depends on. Live pod and env state was not
  observed.

## Proposed solution

### 1. Schema (`internal/db/agent_schema.go`)

Add the table `agent_usage` to both schema lists:

```
id            INTEGER PK / BIGSERIAL
job_id        BIGINT NOT NULL           -- agent_jobs.id
attempt       INTEGER NOT NULL
user_id       BIGINT NOT NULL
runtime       TEXT NOT NULL             -- copied from agent_jobs.runtime
runner        TEXT NOT NULL DEFAULT ''
model         TEXT NOT NULL DEFAULT ''
input_tokens  BIGINT NOT NULL DEFAULT 0
output_tokens BIGINT NOT NULL DEFAULT 0
reserved_usd  REAL/DOUBLE PRECISION NOT NULL DEFAULT 0
cost_usd      REAL/DOUBLE PRECISION      -- NULL until settled
status        TEXT NOT NULL              -- reserved|held|settled
created_at, updated_at, settled_at
UNIQUE(job_id, attempt)
INDEX (user_id, runtime, created_at), INDEX (runtime, created_at)
```

There is no foreign key cascade: the purge deletes these rows explicitly, the
way it handles `agent_job_attempts`. Add the nullable profile columns
`managed_budget_usd_day` and `managed_budget_usd_month` with
`addColumnIfMissing`. `budget_paused_until` already exists, so drop its
"unused" comments.

### 2. Budget logic (`internal/db/agent_usage.go`, new)

```go
type ManagedBudget struct {
    PerJobUSD, AccountDayUSD, AccountMonthUSD, GlobalDayUSD float64
    Now func() time.Time
}
func (s *Store) WithManagedBudget(b ManagedBudget) *Store
```

Without a configured budget (a zero struct), the claim behaves as it does
today. This keeps every existing test and own-runtime path unchanged.

#### Lock order (owner amendment 2026-11-03)

When `runtime == managed` and a budget is configured, `claimAgentJobs` and
`claimCoalesced` take the global budget lock FIRST, before `reserveInflight`:
on Postgres `pg_advisory_xact_lock(hashtextextended('mctl-telegram:managed-budget:global'))`.
The order is global lock, then the account advisory lock in `reserveInflight`,
then the claim's `FOR UPDATE SKIP LOCKED`. There is no `agent_profiles ... FOR UPDATE`.

Why the first draft's order (account lock, profile `FOR UPDATE`, global lock)
was rejected: claim A holds the global lock and finds the global cap durably
exhausted, so `pauseForBudget` updates every managed profile with pending jobs,
including account B's. Meanwhile claim B holds B's profile row lock and waits
for the global lock. A waits on B's row and B waits on A's lock, which is a
deadlock (`40P01`). With the global lock first, B waits before it holds
anything, and the cycle cannot form. The global lock already serializes every
managed claim that has a budget, so a profile row lock adds no protection a
test could show. It is removed rather than kept as an unproven guard. The cost
is the same as before: managed claims are serialized platform-wide, which is
acceptable at the pool's scale (`MANAGED_RUNTIME_MAX_ACCOUNTS`, 1 at first,
and claims are short). Own-runtime claims and managed claims without a budget
never take the global lock.

#### `reserveBudget(ctx, tx, pg, userID, limit) (int, error)`

It runs inside the claim transaction directly after `reserveInflight` (the
global lock is already held):

1. `SELECT managed_budget_usd_day, managed_budget_usd_month FROM agent_profiles WHERE user_id = $1`, a plain read.
2. For three windows (the account day, the account month and the global day,
   with the UTC start of day and of month compared against `created_at`),
   compute over `runtime='managed'` rows:
   - `durable` = `SUM(cost_usd)` of `settled` rows + `SUM(reserved_usd)` of `held` rows;
   - `inflight` = `SUM(reserved_usd)` of `reserved` rows.
3. `room = floor(min over windows of (cap - durable - inflight) / PerJobUSD)`,
   limited to `limit`. If `room > 0`, return it.
4. If `room == 0`:
   - if some window has `cap - durable < PerJobUSD` (durable exhaustion), call
     `pauseForBudget(tx, scope, windowEnd)` for the first such window in the
     order global day, account month, account day, and return 0;
   - otherwise (transient: in-flight reservations only), return 0 without a
     pause, a notification or `mctl_agent_budget_exhausted_total`, and report
     `mctl_agent_budget_deferred_total{scope}` through the same hook.

   The claim then commits only what step 4 wrote and claims nothing.

After the claim's `UPDATE ... RETURNING`, insert one `agent_usage` row per
claimed job: `(job_id, attempts, user_id, 'managed', reserved_usd=PerJobUSD, status='reserved')`.
The insert uses the same `tx`, so the reservation and the claim commit
together.

`pauseForBudget`:

- Account scope:
  `UPDATE agent_profiles SET budget_paused_until=$end WHERE user_id=$1 AND (budget_paused_until IS NULL OR budget_paused_until < $end)`.
- Global scope: the same update across every `runtime='managed'` profile with
  a pending job, with `RETURNING user_id`. It runs only under the global lock,
  which no other claim waits for while holding a profile row (see "Lock order").
- For each row actually updated, insert an `owner_notifications` row with
  kind `NotificationBudget = "budget"`. The body is sealed like the others and
  states which window and when it resets. Because the update fires only when
  `budget_paused_until` moves forward, there is exactly one notification per
  window and no `HasOwnerNotificationSince` window guessing.
- Return the scope so the caller increments
  `mctl_agent_budget_exhausted_total{scope}`. The store reports it through an
  optional hook, as `notifyOutbox` does, and the store does not import metrics.

### 3. Candidates and routing

In `ListManagedClaimCandidates`, replace the placeholder with
`AND (ap.budget_paused_until IS NULL OR ap.budget_paused_until <= $now)` and a
global guard:
`AND (SELECT COALESCE(SUM(COALESCE(u.cost_usd,u.reserved_usd)),0) FROM agent_usage u WHERE u.runtime='managed' AND u.created_at >= $dayStart) + $perJob <= $globalCap`
(every status counts: settled at its cost, `reserved` and `held` at the reservation).
This is emitted only when a budget is configured. The candidate list stays a
hint and the claim stays the authority.

In `RouteUnclaimedAgentJobs`, add
`AND NOT EXISTS (SELECT 1 FROM agent_profiles bp WHERE bp.user_id = agent_jobs.user_id AND bp.budget_paused_until > $now)`.

### 4. Settle and release

- `RecordAgentJobUsage(ctx, userID, jobID, attempt int, u Usage) (UsageOutcome, error)`
  replaces the body of `RecordAgentJobCost`. The old function becomes a
  wrapper so existing callers keep working. In one transaction:
  1. `SELECT runtime FROM agent_jobs WHERE id=$1 AND user_id=$2 AND attempts=$3 FOR UPDATE`.
     No rows returns `ErrAgentJobNotFound`, the existing 409 "no longer
     claimed".
  2. `UPDATE agent_jobs SET cost_usd`, the existing behaviour.
  3. Select the `agent_usage` row for (job, attempt).
     - None (an own job, or a pre-ledger managed claim): insert `settled`
       with the runtime from the job row (`own` when NULL).
     - `reserved` or `held`: update to `settled` with the reported fields.
     - `settled` with identical fields: `UsageUnchanged`, no write.
     - `settled` with different fields: `ErrUsageConflict`, rolled back.

     A late report for a `held` attempt settles only while `agent_jobs.attempts`
     still equals that attempt (step 1's fence). Once the job has been
     re-claimed, the report is refused as before and the row stays `held`,
     counted at the full reservation. That is the conservative outcome.
- In `RequeueStaleAgentJobs`, for `fencedIDs`, `deadIDs` and `requeuedIDs`,
  run
  `UPDATE agent_usage SET status='held', updated_at=$now WHERE job_id=$1 AND status='reserved'`
  in the same transaction, after the attempt rows. This follows the existing
  lock order: `agent_jobs` first. (Owner amendment 2026-11-03.) The first
  draft released these rows. But a pool job token expires at
  `ClaimedAt + jobVisibility` (`events.go`, the envelope `Deadline`), which is
  exactly the threshold the sweeper requeues on. A run that crosses its
  deadline has spent money, its cost report is refused with 401 (the risk
  #1090 accepted and assigned to this slice), and releasing the reservation
  would drop that spend from every cap. `held` keeps it counted at the
  reservation, the upper bound the runner enforces up to one model call, until
  a report settles it or the window ends.
- In `ReleaseUnissuedClaim`, run
  `DELETE FROM agent_usage WHERE job_id=$1 AND attempt=$2 AND status='reserved'`,
  because no token for that attempt ever left the server, the attempt number
  is reused, and UNIQUE(job_id, attempt) would otherwise block the next claim.
  This is the only path that removes a reservation without a cost report.
- Overshoot bound: the runner checks `totalCost > MaxBudgetUSD` after each
  model call (`openairunner.go`), so one attempt can exceed `reserved_usd` by at
  most one call. The settle records the actual cost, so later claims see it. A
  cap can therefore be overrun by at most one model call per in-flight managed
  attempt. This is stated in ADR 0008 section 5 by task 11.
- In `purgeAgentJobs`, add
  `DELETE FROM agent_usage WHERE user_id = $1` after the `agent_jobs` lock
  statement and before deleting `agent_jobs`.

### 5. HTTP (`internal/agentapi/events.go`)

```go
type reportJobCostRequest struct {
    Attempt      int     `json:"attempt"`        // legacy; optional with a job token
    CostUSD      float64 `json:"cost_usd"`
    Model        string  `json:"model"`
    Runner       string  `json:"runner"`
    InputTokens  int64   `json:"input_tokens"`
    OutputTokens int64   `json:"output_tokens"`
}
```

`decodeStrict` already rejects unknown fields, so `user_id`, `runtime` and
`job_id` return 400. With a job token, `attempt := id.JobAttempt` and a
non-zero body attempt must match (`enforceBinding`). An account token still
requires `attempt > 0`, the legacy path. Validate `runner` and `model`
against `[A-Za-z0-9._:/-]{0,128}` and require non-negative token counts.
`ErrUsageConflict` maps to 409 `{"error":"usage_conflict"}` plus
`s.audit(ctx, uid, "report_agent_job_cost", "refused", "usage_conflict")`.
`UsageUnchanged` maps to 200 `{"recorded": true, "unchanged": true}`. On a
first settle, increment the usage metrics. The metric label value for model
is the validated string, and runner is clamped to `claude|openai|other`.

`jobEnvelope` gains `MaxJobCostUSD float64 \`json:"max_job_cost_usd,omitempty"\``,
which `poolClaimOne` sets from `ManagedClaimConfig.MaxJobCostUSD`.

### 6. Config and wiring

In `internal/config/config.go`, add `ManagedMaxJobCostUSD`
(`MANAGED_MAX_JOB_COST_USD`, 0.50), `ManagedBudgetUSDPerAccountDay` (1.00),
`ManagedBudgetUSDPerAccountMonth` (15.00) and `ManagedBudgetUSDGlobalDay`
(20.00). Validation: every value must be greater than 0, and the per-job value
must not exceed any cap. `wireManagedPool` passes them to
`ManagedClaimConfig` and `store.WithManagedBudget`.

The admin profile route accepts `managed_budget_usd_day` and
`managed_budget_usd_month` (a `*float64`, where JSON null clears the value;
negative values return 400). The change is persisted through the existing
profile update and logged with `LogToolCall` like the other admin fields.

### 7. Worker (`internal/agentworker`)

`Client.ReportJobCost` gains a `Usage` argument and sends the new shape
`{cost_usd, model, runner, input_tokens, output_tokens}`. When it holds a job
token it omits `attempt`. On a 400 from an older server it retries once with
`{attempt, cost_usd}`, mirroring the `/complete` fallback. `recordRunCost`
fills runner and model (and tokens from the OpenAI runner's accumulated
usage). In pool mode the runner's budget is
`min(AGENT_MAX_BUDGET_USD, envelope.max_job_cost_usd)` when the envelope
carries the value.

### 8. Metrics (`internal/metrics/metrics.go`)

Add `AgentUsageCostUSDTotal{runner,model}`,
`AgentUsageTokensTotal{direction,model}`,
`AgentBudgetExhaustedTotal{scope}`, `AgentBudgetDeferredTotal{scope}`
(transient: in-flight reservations only), `AgentManagedAccounts` (a gauge), and
the drift gauges `AgentUsageHeldUSD` (`mctl_agent_usage_held_usd`) and
`AgentUsageHeldRows` (`mctl_agent_usage_held_rows`) over `held` rows of the
current UTC day. The gauges are refreshed by the existing sweeper loop through
the new `Store.CountManagedAccounts` and `Store.HeldUsage`. Gitops alert rules
are a follow-up PR.

## Alternatives

- **Check the caps at claim time without reservations** (sum only settled
  cost). This was dropped. ADR 0008 section 5 calls this advisory: N
  concurrent claims all see the same settled sum, and each in-flight job can
  spend up to the per-job cap before it settles.
- **A separate `agent_budget_state` table for the global pause instead of
  stamping every managed profile.** This would need its own reads in the
  candidate query and the router, and notifying owners would still need
  per-account state. Stamping `budget_paused_until` keeps one predicate in
  both places and gives "notify once" for free. The global guard in the
  candidate query remains as a cheap backstop.
- **Trust the body for runtime and user** (the worker states what it ran).
  This was rejected by the acceptance criterion "the worker cannot choose the
  account it bills". Identity comes from the token and the job row only.
- **Serialize the global cap with `SELECT ... FOR UPDATE` on a singleton
  row instead of an advisory lock.** That would also work on Postgres. The
  advisory lock matches the existing `reserveInflight` pattern and needs no
  seed row. Either one passes the race test.
- **Release the reservation on requeue** (first draft). Rejected in owner
  review (2026-11-03): it drops the spend of a deadline-crossing run whose
  report was refused with 401, so the caps would not be hard.
- **Accept job-token cost reports after the deadline (a grace window).**
  Rejected for this slice: it widens the authority of an expired credential
  that #1090 deliberately bounds, and it still loses the report when the
  worker dies. `held` bounds spend without changing token rules.
- **Keep the profile `FOR UPDATE` after the global lock.** Rejected: it
  protects nothing once the global lock serializes the claim, no test could
  fail without it, and in the first draft's order it formed a deadlock with
  the global pause.

## Platform impact

- **Migrations**: one new table and two nullable columns, all additive and
  idempotent (`CREATE TABLE IF NOT EXISTS`, `addColumnIfMissing`). There is no
  backfill. Pre-ledger attempts simply have no row, and a later cost report
  inserts a settled one.
- **Backward compatibility**: the legacy cost body `{attempt, cost_usd}` is
  still accepted. An older worker's report works unchanged. A newer worker
  against an older server falls back on 400. `max_job_cost_usd` is
  `omitempty` and older workers ignore it. Own-runtime claims do not touch
  the budget code: `reserveBudget` runs only for `RuntimeManaged` with a
  configured budget.
- **Behaviour while dark**: the pool and budgets are wired only when
  `MANAGED_RUNTIME_ENABLED` is on, and gitops sets no `MANAGED_` variables
  today. The `RouteUnclaimedAgentJobs` predicate is a no-op while no profile
  has `budget_paused_until` in the future.
- **Resources**: one extra indexed sum query and one insert per managed
  claim, and one row per job attempt. The global advisory lock serializes
  managed claims, which costs milliseconds at current scale.
- **Risks and mitigations**:
  - A reservation that is never settled (`reserved` on a completed job, or
    `held` after a requeue, dead-letter or fence) counts at the full per-job
    cap until its window ends. With the defaults (per job 0.50, account day
    1.00), one deadline-crossing run without a report takes half an account's
    day. That is the conservative trade the owner chose over uncounted spend,
    and it is visible as `mctl_agent_usage_held_usd` / `_rows`, which are the
    soak's reconciliation-drift figures.
  - Lock ordering: the global budget lock, then the account advisory lock,
    then the claim's row locks, the same for every managed claim with a
    budget. No profile row lock. The sweeper and the purge touch
    `agent_usage` only after `agent_jobs`, matching the worker's order.
  - Label cardinality: model and runner values are validated and runner is
    clamped. The set of models is bounded by worker configuration.
  - Privacy: no message content enters the ledger. The notification body is
    sealed per user like the other owner notifications.
