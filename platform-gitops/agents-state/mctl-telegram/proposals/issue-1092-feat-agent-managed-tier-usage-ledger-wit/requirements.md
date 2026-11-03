# Managed-tier usage ledger with reservation caps

## Context

Issue #1092 (epic #1088, P5 of #1002) is slice 4 of ADR 0008
(`docs/adr/0008-managed-runtime.md`, section 5). The platform already has the
managed pool claim: `POST /jobs/claim` for an `aud=agent-pool` identity,
`Store.ListManagedClaimCandidates` and `Store.ClaimManagedAgentJobs` with a
per-account in-flight cap. What it does not have is any spend control. Today
the only spend record is `agent_jobs.cost_usd`, which the worker writes as
`{attempt, cost_usd}` through `POST /jobs/{id}/cost`. Nothing limits what the
platform pays the model provider on behalf of managed accounts.

This slice adds a server-authoritative ledger (`agent_usage`, one row per job
attempt), hard caps per account per day, per account per month and globally
per day, enforced by reserving the per-job cap when a job is claimed. The
reservation is made inside the claim transaction, so the caps hold when claims
run concurrently. An account that reaches a cap keeps its messages queued, its
owner is told once per window, and the unclaimed sweeper does not route those
messages to the operator. The worker reports cost but cannot choose which
account or runtime is billed.

## User stories

- AS the platform operator I WANT hard daily, monthly and global spend caps on managed accounts SO THAT a bug, a loop or an abusive account cannot spend more than the budget.
- AS the platform operator I WANT spend recorded per attempt with runner, model and tokens SO THAT I can reconcile against the AI gateway and alert on cost.
- AS a managed account owner I WANT my messages held, not dropped, when my budget is used up, and to be told once SO THAT I know why replies are late and am not spammed.
- AS a security reviewer I WANT the server to derive the billed account, runtime, job and attempt from the job token and job row SO THAT a compromised worker cannot bill another account or relabel an own job as managed.
- AS an admin I WANT a per-account budget override through the admin profile route SO THAT I can raise or lower one account's cap without a redeploy.

## Acceptance criteria (EARS)

Ledger

- THE SYSTEM SHALL keep a table `agent_usage` with columns `id`, `job_id`, `attempt`, `user_id`, `runtime`, `runner`, `model`, `input_tokens`, `output_tokens`, `reserved_usd`, `cost_usd`, `status` (`reserved`, `held` or `settled`), `created_at`, `updated_at`, `settled_at`, and a UNIQUE constraint on (`job_id`, `attempt`), on both SQLite and Postgres.
- THE SYSTEM SHALL copy `agent_usage.runtime` from `agent_jobs.runtime` of the job row and never from a request body.
- WHEN an account's agent data is purged THE SYSTEM SHALL delete its `agent_usage` rows in the same transaction as its `agent_jobs` rows.

Reservation

- WHEN the pool claims a managed job THE SYSTEM SHALL insert, in the claim transaction, an `agent_usage` row with status `reserved` and `reserved_usd` equal to the server's per-job cap `MANAGED_MAX_JOB_COST_USD`.
- WHEN the pool hands out a claimed job THE SYSTEM SHALL include that per-job cap as `max_job_cost_usd` in the claim envelope.
- THE SYSTEM SHALL compute availability as cap minus settled cost minus every unsettled reservation (`reserved` and `held`) of the window, inside the claim transaction, with the global budget lock held.
- WHEN a managed claim with a configured budget starts THE SYSTEM SHALL take the global budget lock before any per-account lock (`reserveInflight`'s account advisory lock) and before any `agent_profiles` row lock, so that a claim never holds an account or profile lock while it waits for the global lock (owner amendment 2026-11-03, see "Lock order" in design.md).
- WHILE two claim transactions race for an account whose remaining budget covers exactly one job THE SYSTEM SHALL let exactly one of them claim.
- WHILE two claim transactions for two different accounts race and the global remaining budget covers exactly one job THE SYSTEM SHALL let exactly one of them claim.
- WHILE one claim transaction exhausts the global budget and pauses other accounts AND another account's claim is in progress THE SYSTEM SHALL complete both without a deadlock (no Postgres `40P01`).
- WHEN a cost report arrives for an attempt THE SYSTEM SHALL move its row to `settled` with the reported cost, tokens, runner and model.
- WHEN the sweeper requeues, dead-letters or fences a stale managed attempt (`RequeueStaleAgentJobs`) THE SYSTEM SHALL move that attempt's `reserved` row to `held`, and SHALL NOT release it. Its job token has left the server, the run may have spent up to the per-job cap, and a pool job token expires at the same claim deadline the sweeper uses, so its cost report can be refused with 401 (risk accepted in #1090 and assigned to this slice). A `held` row keeps counting at `reserved_usd` until a cost report settles it or its window ends (owner amendment 2026-11-03).
- WHEN a claim is undone with `ReleaseUnissuedClaim` THE SYSTEM SHALL delete that attempt's `reserved` row, because no token for it ever left the server and the attempt number is reused by the next claim. This is the only path that removes a reservation without a cost report.
- IF a cost report arrives for an attempt whose row is `held` THEN THE SYSTEM SHALL settle it with the reported cost, because the spend happened.
- THE SYSTEM SHALL NOT define a `released` status; the statuses are `reserved`, `held` and `settled`.
- THE SYSTEM SHALL expose the unsettled held reservations as a gauge `mctl_agent_usage_held_usd` (sum of `reserved_usd` over `held` rows of the current UTC day) and `mctl_agent_usage_held_rows`, refreshed by the sweeper, which are the "reservation reconciliation drift" figures for the soak.
- THE SYSTEM SHALL document that actual spend per attempt can exceed `reserved_usd` by at most one model call, because the runner checks its budget after each call (`openairunner.go`, `totalCost > MaxBudgetUSD`); a settle records the actual cost, and the next claim's availability uses it.

Caps and windows

- THE SYSTEM SHALL enforce `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY` (default 1.00), `MANAGED_BUDGET_USD_PER_ACCOUNT_MONTH` (default 15.00) and `MANAGED_BUDGET_USD_GLOBAL_DAY` (default 20.00), with day and month as UTC calendar windows attributed by the attempt's `created_at`.
- WHERE an account has `managed_budget_usd_day` or `managed_budget_usd_month` set on its profile THE SYSTEM SHALL use that value instead of the matching default.
- WHEN an admin calls the admin profile route with `managed_budget_usd_day` or `managed_budget_usd_month` THE SYSTEM SHALL store the override (a non-negative number, or null to clear it) and audit the change.
- THE SYSTEM SHALL count every `runtime = 'managed'` row (`reserved`, `held` and `settled`) toward the caps: a settled row at its `cost_usd`, an unsettled one at its `reserved_usd`.

Exhaustion

The amendment of 2026-11-03 separates durable exhaustion from transient exhaustion. Durable usage is settled cost plus `held` reservations: it can only fall when a held row settles lower or the window ends. Transient usage is the `reserved` rows of attempts that are still in flight, which settle within the claim deadline, usually for cents.
- IF a managed claim finds that a cap leaves no room for one more per-job reservation when counting durable usage alone THEN THE SYSTEM SHALL claim nothing for that account, leave its jobs pending, set `agent_profiles.budget_paused_until` to the end of the exhausted window, and increment `mctl_agent_budget_exhausted_total{scope}` with scope `account_day`, `account_month` or `global_day`.
- IF a cap has room counting durable usage alone but none once in-flight `reserved` rows are added THEN THE SYSTEM SHALL claim nothing for that account in this transaction, leave its jobs pending, and SHALL NOT set `budget_paused_until`, queue a notification or increment `mctl_agent_budget_exhausted_total`. It increments `mctl_agent_budget_deferred_total{scope}` instead.
- IF the global cap is durably exhausted THEN THE SYSTEM SHALL set `budget_paused_until` to the end of the UTC day on every managed account that has pending jobs.
- WHEN `budget_paused_until` moves forward to a new window THE SYSTEM SHALL queue exactly one `owner_notifications` row of kind `NotificationBudget` ("budget") for that account, in the same transaction, and SHALL NOT queue another for the same window.
- WHILE `budget_paused_until` is in the future THE SYSTEM SHALL exclude the account from `ListManagedClaimCandidates`.
- WHILE the global day budget has no room for one more per-job reservation THE SYSTEM SHALL return no candidates from `ListManagedClaimCandidates`.
- WHILE an account's `budget_paused_until` is in the future THE SYSTEM SHALL NOT route its pending jobs to the operator in `RouteUnclaimedAgentJobs`.

Cost report (`POST /jobs/{id}/cost`)

- THE SYSTEM SHALL accept a body with only `model`, `input_tokens`, `output_tokens`, `runner`, `cost_usd`, plus the legacy `attempt`, and SHALL reject with 400 any other field, including `user_id`, `runtime` and `job_id`.
- WHEN the caller holds a job token THE SYSTEM SHALL take the user, job and attempt from the token and the runtime from the job row; a body `attempt` that differs from the token is refused by `enforceBinding`.
- WHEN a legacy body `{attempt, cost_usd}` arrives THE SYSTEM SHALL record it as before, with empty runner and model and zero tokens.
- IF a report repeats an already settled attempt with identical `cost_usd`, `model`, `runner`, `input_tokens` and `output_tokens` THEN THE SYSTEM SHALL answer 200 and change nothing.
- IF a report for an already settled attempt differs in any of those fields THEN THE SYSTEM SHALL answer 409 with error code `usage_conflict`, change nothing, and write an audit row with status `refused`.
- WHEN an own-runtime job reports cost THE SYSTEM SHALL record a `settled` row with runtime `own` and SHALL NOT count it toward managed caps.
- THE SYSTEM SHALL keep writing `agent_jobs.cost_usd` as the last reported attempt's cost.

Metrics

- WHEN a row is settled THE SYSTEM SHALL add the cost to `mctl_agent_usage_cost_usd_total{runner,model}` and the tokens to `mctl_agent_usage_tokens_total{direction,model}` (direction `input` or `output`), with model and runner labels bounded.
- THE SYSTEM SHALL expose `mctl_agent_managed_accounts` as the number of profiles with `runtime = 'managed'`.

## Out of scope

- Alert rules in mctl-gitops (global cap hit, hourly spend, pool worker down). The issue defers them to a follow-up PR.
- Deploying the managed worker or setting the flags and caps on tg-preview (ADR 0008 section 6).
- The OpenAI runner itself and `mctl_agent_openai_requests_total` (slice 3). This slice only extends the cost report the runners already send.
- Budgets for own-runtime accounts. Own spend is recorded, never capped.
- Showing budget state in `/mctl assistant` or on the manage page.
- Reconciling against AI gateway invoices.

## Open questions

- Name and default of the server-side per-job reservation. The issue says "`max_job_cost_usd` (server-side value)" but names no env var. This proposal uses `MANAGED_MAX_JOB_COST_USD`, default 0.50, matching `AGENT_MAX_BUDGET_USD: "0.50"` in `labs/agent-worker-preview/values.yaml`. In pool mode the worker uses the smaller of its own `AGENT_MAX_BUDGET_USD` and the envelope value.
- Window boundaries. This proposal uses UTC calendar day and month, and attributes an attempt to the window of its `created_at`, which is the claim time. Rolling 24 h or 30 d windows would need a different `budget_paused_until` computation.
- RESOLVED (owner amendment 2026-11-03): a reservation whose cost report never arrives stays counted. On a completed job it stays `reserved`; on a requeued, dead-lettered or fenced attempt it becomes `held`. Either way it counts at the full per-job cap until the window ends, and it is reported through `mctl_agent_usage_held_usd` / `_rows` as reconciliation drift. Releasing it, as the first draft did, dropped real spend from the caps exactly in the deadline-crossing case that #1090 left to this slice.
- RESOLVED (owner amendment 2026-11-03): the `agent_profiles` row lock is removed. With the global lock taken first, every managed claim with a budget is serialized by that one lock, so a profile `FOR UPDATE` protects nothing a test could show. It also created a deadlock cycle with the global pause, which updates other accounts' profile rows while holding the global lock. Each remaining guard has a failing mutation: the global lock (T1 `global`), the unsettled-reservation term (T1 `account`), the lock order (T16) and the durable/transient split (T15).
- The issue's exact names for the override columns are not given. This proposal uses `agent_profiles.managed_budget_usd_day` and `managed_budget_usd_month`, both nullable.
