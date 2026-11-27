# Design: issue-1430-spike-pa-postgresql-job-queue-polling-cl

## Current state

Pinned to `mctlhq/mctl-telegram@13fd2333a041c3a0a2634db29879bfa116250bf6`
(clone HEAD, and the image `main-13fd233` deployed on both preview services).
The issue cites `1a19b22`, so line numbers below are from `13fd233`.

### Worker side (OBSERVED, code)

- `cmd/agent-worker/pa_mode.go` builds `agentworker.PAWorker` from
  `AGENT_WORKER_CONCURRENCY` and `AGENT_PA_STREAMING`. It does not set
  `PollInterval`, so there is no environment variable for it.
- `internal/agentworker/parunner.go` `PAWorker.Loop` starts
  `max(Concurrency,1)` goroutines. Each one runs `loop`:
  - `Claim` (POST `PARouteClaim` = `/api/pa/v1/jobs/claim`, using the pool
    credential).
  - On a job, `Run`, then reclaim immediately (`continue`).
  - On no job, or on an error, `waitContext(ctx, interval)`, where `interval`
    defaults to 2 s. The wait is fixed: no jitter, no backoff, and the same
    wait follows a claim error.

### Server side (OBSERVED, code)

`internal/pa/runloop.go` `RunLoop.serveClaim` authenticates the pool token
and calls `Store.ClaimPAJob` with `Lease` (`jobs.DefaultLease` = 5 min,
`internal/pa/jobs/jobs.go`), `Budget`, `Gate` and `Build`. It then delivers
the notices.

`internal/db/pa_jobs.go` `ClaimPAJob` runs these steps:

1. `postgresDialect` calls `resolveDialect` (`internal/db/agent_jobs.go`).
   The answer is cached after the first conclusive probe, so steady state runs
   no SQL here. The issue's "dialect check per claim" is a Go-level branch and
   costs no DB round-trip.
2. `ExpirePAJobs`, in its own transaction:
   - `UPDATE pa_jobs SET status='expired' WHERE status='claimed' AND lease_until_ms <= now RETURNING ...`;
   - per expired row, `enqueuePANotice`;
   - `UPDATE pa_usage SET status='held' WHERE status='reserved' AND job_id IN (SELECT id FROM pa_jobs WHERE status <> 'claimed')`;
   - COMMIT.

   All of this runs on every claim, including when the queue is empty.
3. `ClaimsEnded` short-circuit (`MANAGED_CLAIM_NOT_AFTER`).
4. Up to `maxClaimTries` = 8 calls to `claimOnce`, then `claimPicked`. Each
   call is a new transaction:
   - `lockManagedBudget`:
     `SELECT pg_advisory_xact_lock(hashtextextended(managedBudgetLockKey,0))`.
     This is a single, process-wide, exclusive transaction-scoped advisory
     lock (`internal/db/agent_usage.go`).
   - Pick:
     `SELECT j.id, j.principal, j.claim_failures FROM pa_jobs j WHERE status IN ('pending','held') AND retry_at_ms <= now AND (held_until_ms <= now OR <held-and-conversation-gone>) AND NOT EXISTS (claimed job of same principal) ORDER BY created_at_ms, id LIMIT 1`.
     It has no row lock and no `SKIP LOCKED`.
   - Empty result: return `ClaimNone`. The transaction rolls back through the
     deferred `Rollback`, and the advisory lock is released at the end of the
     transaction.
   - Picked: `LockPAPrincipal` (`internal/db/pa_convo.go`), an UPSERT into
     `pa_principal_locks` that acts as the lock row and writes a row. Then the
     job is re-read with `FOR UPDATE` on PostgreSQL. Then `runGate`, budget
     (`paBudget`, `paWindowSums`) and the reservation in `pa_usage`, and the
     status change to `claimed` with a lease.
   - A per-job failure leads to `backoffPAJob` in its own transaction
     (`claim_failures`, `retry_at_ms`, `MaxClaimFailures` = 5).
5. Schema (`paJobsSchema`):
   - `idx_pa_jobs_queued`: UNIQUE on `(principal)`, filtered to pending/held.
     At most one queued job per principal.
   - `idx_pa_jobs_running`: UNIQUE on `(principal)`, filtered to claimed.
     At most one claimed job per principal.
   - `idx_pa_jobs_status(status, created_at_ms)`.
   - `idx_pa_jobs_principal`.

The same global advisory lock is taken by several other paths, so any wait on
it is a cross-path wait:

- the managed agent claim (`internal/db/agent_jobs.go` around line 428, for
  budgeted managed claims);
- the managed turn claim (`internal/db/agent_turn_claim.go:77`);
- PA running-job admission with budget (`beginRunningLocked`,
  `pa_jobs.go:797`);
- PA writes (`internal/db/pa_writes.go:46`).

Precedent: the managed agent claim already uses `FOR UPDATE SKIP LOCKED`
(`agent_jobs.go:414`). The PA claim deliberately does not.

DB pool: `internal/db/db.go` defaults to 10 open and 2 idle connections on
PostgreSQL (`DB_MAX_OPEN_CONNS`, `internal/config/config.go`). An idle claim
uses one connection for two short transactions.

Existing metrics: `mctl_pa_run_phase_seconds` (queue, model, tool, run,
total) and `mctl_pa_job_failures_total` (`internal/metrics/pa.go`). Nothing
counts claims, empty claims or lock wait.

Existing PG concurrency tests: `internal/db/pa_concurrency_pg_test.go` and
`managed_runtime_pg_test.go`, both gated on `TEST_DATABASE_URL`. This is the
natural harness location for a later GO-authorized synthetic benchmark.

### Derived load (arithmetic, NOT measured)

One idle claim slot at 2 s makes 0.5 HTTP claims/s (43,200/day). Each claim
is two transactions and at least four statements, one of them a global
advisory lock acquire.

| Slots | Claims/s | Claims/day |
|---|---|---|
| 1 (current preview) | 0.5 | 43,200 |
| 5 | 2.5 | 216,000 |
| 10 | 5 | 432,000 |
| 20 | 10 | 864,000 |

### Hypotheses (to be measured, not asserted)

- H1. Idle polls serialize on the global advisory lock with each other and
  with managed and PA budget paths. The hold time is about the duration of
  the pick SELECT. The wait is expected to be negligible below 20 slots.
- H2. `ExpirePAJobs`' second UPDATE scans the reserved rows in `pa_usage`
  plus a subquery on every claim. Its cost grows with the ledger, not with
  the queue.
- H3. An idle claim produces near-zero WAL, because the zero-row UPDATEs
  assign no xid. The picked path writes WAL from the principal-lock UPSERT,
  the reservation and the status change.
- H4. Synchronized bursts are bounded by the global lock plus the oldest-first
  pick. Throughput is then limited by claim-transaction length, not by slot
  count.
- H5. At the preview's scale, model/tool latency dominates time-to-start far
  more than the claim path does.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-pa-preview/values.yaml`:
  `replicaCount: 1`, `AGENT_WORKER_CONCURRENCY: "1"`, `AGENT_PA_STREAMING: "true"`,
  `AGENT_PA_BASE_URL` pointing at `labs-mctl-telegram-preview-base-service`,
  image tag `main-13fd233`, limits 500m CPU / 256Mi. No poll-interval key.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  image `main-13fd233`, `PA_ENABLED: "true"`, a database `labs-mctl-telegram-preview`
  (Vault `teams/labs/mctl-telegram-preview/database`), limits 1 CPU / 512Mi.
  No `DB_MAX_OPEN_CONNS` key was found, so I infer the code default of 10 from
  the code; it was not observed at runtime.
- `mctl_get_service_status(labs, agent-worker-pa-preview)`: Synced, Healthy,
  `main-13fd233`.
- `mctl_get_service_pods(labs, mctl-telegram-preview)`: 1 pod, Running, 0
  restarts.
- Not observed: PostgreSQL version, `pg_stat_statements` availability, real
  claim QPS and lock waits. No such tool is used here and no live measurement
  is authorized. These are recorded as gaps, not as absent.

## Proposed solution

A documentation-only spike. Three committed artifacts, plus nothing in code.

1. `docs/reports/pa-job-queue-scaling-spike.md`, the report:
   - Pin and scope, and the HOLD statement.
   - A current-state sequence diagram (Mermaid) of worker, `serveClaim`,
     `ClaimPAJob`, `ExpirePAJobs` tx, `claimPicked` tx and the outbox, with
     both the empty and the picked branch.
   - A SQL/lock inventory table: step, statement, tx, lock type
     (advisory-xact global, principal UPSERT lock, `FOR UPDATE` row), whether
     it writes rows, and whether it runs on an idle poll.
   - Observations versus hypotheses (H1-H5 above), each with its confirming
     measurement.
   - An invariant register:
     - one claimed job per principal (`idx_pa_jobs_running`);
     - lease and attempt fencing (pa-job token, `loadRunningPAJob` `FOR UPDATE`);
     - the gate at claim and at every tool dispatch (`runGate`, `AdmitPAToolCall`);
     - reservation accounting (`pa_usage`);
     - oldest-first fairness;
     - backoff (`ClaimBackoff`);
     - cancellation on revoke.

     Each alternative below is scored against every invariant.
   - The alternatives analysis (A-D, see below), with cost, tradeoffs and
     rollback.
   - The decision record: provisional `KEEP_POSTGRES_POLLING`, with candidate
     `OPTIMIZE_POSTGRES_CLAIM` items queued as follow-up issues to open only
     if the targets fail. Status: AWAITING BENCHMARK GO.
2. `docs/plans/pa-queue-benchmark.md`, the plan, not run:
   - Isolation: a throwaway PostgreSQL that is never the shared CNPG cluster,
     a stub OpenAI-compatible model that returns a fixed reply, no connectors,
     and an in-process or loopback `mctl-telegram`.
   - Fixtures: synthetic principals (Alice/Bob/Carol/Dana plus generated
     synthetic ids at 20/100/1,000), conversations and queued jobs, built with
     the existing store APIs (`EnqueuePAJob`, `PAConversationOpen`).
   - Scenario matrix: slots 1/5/10/20 x concurrency 1/2; principals
     20/100/1,000; load idle, steady (Poisson) and synchronized burst
     (N principals enqueue at t0); the active-job count is kept separate from
     the enrolled count.
   - Fault scenarios: worker kill mid-run (lease expiry), simultaneous claims,
     DB outage and restart, revocation during claim.
   - Equal CPU/memory limits per cohort. Fixed budget: at most 4 h wall-clock
     and $0 model spend. Owner GO is required, with the #1317/#1319/#1324
     gates restated.
   - The harness lives where the existing `TEST_DATABASE_URL`-gated PG tests
     live. Writing it is a separate implementation issue, out of scope here.
3. A dashboard specification and pre-registered targets, as sections in the
   plan:
   - Metrics: claims/s (empty and non-empty), HTTP and DB QPS, tx and
     lock-wait p50/p95/p99, claim response p50/p95/p99, runnable queue depth
     and oldest age, time-to-start, throughput, `DBStats` (WaitCount,
     WaitDuration, InUse), WAL bytes, CPU, per-principal fairness (max/median
     time-to-start), expired, duplicate and failed claims, and usage-ledger
     reconciliation.
   - For each metric, its source and whether it exists today
     (`mctl_pa_run_phase_seconds{phase="queue"}` covers time-to-start) or
     would need new instrumentation.
   - Proposed targets. The 20-person pilot: claim p99 < 250 ms, time-to-start
     p95 < 3 s excluding model, advisory-lock wait p99 < 50 ms, DB connections
     in use p95 < 50% of the pool, and zero duplicate, cross-principal or
     ledger violations. The 100-person pilot: the same correctness targets,
     claim p99 < 500 ms, time-to-start p95 < 5 s, fairness ratio
     (p95 principal / median) < 3.
   - The owner amends the targets before the GO. They are frozen once
     committed.

Why documentation-only: the issue explicitly withholds authorization for code
changes and tests. A written inventory and a pre-registered plan are the
whole of what can be delivered under HOLD, and they make the later GO
decision bounded.

## Alternatives

Options for the queue itself, which the report evaluates:

- A. Keep the fixed 2 s polling. It costs nothing. Idle load scales linearly
  with slots, and every idle poll takes the global lock.
- B. Optimize the PostgreSQL claim. Candidates:
  - jitter or adaptive backoff on empty claims (worker-only);
  - an env var for `PollInterval`;
  - a cheap lock-free existence probe for a due job before taking the global
    lock, so idle polls take no advisory lock and the full pick stays under
    the lock (this preserves the global-budget ordering);
  - running `ExpirePAJobs` only when a claimed row with an expired lease
    exists, or on a timer;
  - a partial index for the due-job pick.

  `SKIP LOCKED` is listed only with an analysis. Under the global lock, row
  contention between PA claimers cannot happen, so it adds nothing unless the
  global lock is narrowed first, and narrowing it touches budget semantics.
- C. `LISTEN/NOTIFY` as a wake-up hint. NOTIFY on enqueue; workers keep the
  polling fallback with a longer interval. This needs a dedicated listening
  connection on the server, plus a long-poll or SSE on the claim route,
  because workers talk HTTP and never connect to PostgreSQL directly. That is
  a larger protocol change than it first appears.
- D. An external broker (Redis Streams and similar). It needs an outbox from
  `pa_jobs` (which must stay the source of truth for fencing and budget),
  redelivery, deduplication, a new stateful service, secrets and an on-call
  burden. It is not justified at 1-20 slots unless measurements show
  PostgreSQL saturation.

Options for the spike deliverable, rejected:

- Build the benchmark harness and instrumentation in this proposal. Rejected:
  the issue says code changes are not authorized. It becomes a follow-up issue
  after the GO.
- Run the analysis only in the issue thread. Rejected: a committed
  `docs/reports` file follows the repo's spike convention
  (`docs/reports/assistant-runtime-boundary-spike.md`, `docs/reports/mcp-apps-spike.md`)
  and can be reviewed and pinned.
- Pick a decision now from the derived arithmetic. Rejected: the issue forbids
  inferring performance from theoretical request rates, so the decision stays
  provisional.

## Platform impact

- Migrations: none. Backward compatibility: unaffected, because no code,
  schema or config changes.
- Resource impact: none at merge. The future benchmark is bounded by the
  plan's budget and needs isolated infrastructure.
- Risks and mitigations:
  - The report could be read as a launch blocker. It carries an explicit
    "not a Phase 1 blocker without measured evidence" statement.
  - Hypotheses could be quoted as facts. Every claim carries an
    `OBSERVED`/`HYPOTHESIS` label, and derived rates are marked.
  - The pinned code could drift. The report names the commit, and the
    inventory must be re-verified at GO time.
  - Fixtures could leak real identities. The plan mandates the synthetic
    personas, following CLAUDE.md.
  - New doc files might trip the doc guard tests in `docs/*_test.go`. The
    implementer runs `go test ./docs/...`.
