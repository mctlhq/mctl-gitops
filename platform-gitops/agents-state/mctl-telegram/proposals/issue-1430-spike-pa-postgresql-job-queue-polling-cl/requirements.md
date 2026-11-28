# Spike: PA PostgreSQL job-queue polling, claim-lock contention and worker scaling (research only)

## Context

Issue #1430 asks for a research spike on the Personal Assistant (PA) job
queue before the private read-only preview grows past its first users. Today
each PA worker goroutine (`internal/agentworker/parunner.go`, `PAWorker.loop`)
POSTs `/api/pa/v1/jobs/claim` and sleeps a fixed 2 s after an empty claim.
On the server, `Store.ClaimPAJob` (`internal/db/pa_jobs.go`) opens one
transaction for `ExpirePAJobs` and then a second one, `claimPicked`. That
second transaction takes the process-wide managed-budget advisory lock
(`lockManagedBudget`, `internal/db/agent_usage.go`) before it looks for a due
job. This happens even when the queue is empty. Nobody knows how much load
or lock contention this causes at higher worker counts. The issue wants
evidence-based answers and an architecture decision with four possible
outcomes: `KEEP_POSTGRES_POLLING`, `OPTIMIZE_POSTGRES_CLAIM`,
`POSTGRES_NOTIFY_WITH_POLL_FALLBACK` or `EVALUATE_EXTERNAL_QUEUE`.

The issue puts the work on IMPLEMENTATION HOLD. It authorizes no change to
production code, no live or preview load test, no extra replicas or
concurrency, no Redis, no Phase 2 and no pilot expansion. This proposal is
therefore limited to written research artifacts committed under `docs/`:

- a static, pinned-code analysis;
- a benchmark and instrumentation plan that is not run;
- a dashboard specification;
- pass/fail targets registered before any measurement;
- a decision record skeleton that can be completed only after a separate
  owner GO lets someone run the benchmark.

The issue's deliverables are split into three stages with separate owner
decisions. This proposal covers stage D2 only:

- **D2 documentation** (this proposal): report, benchmark plan, measurement
  contract and pre-registered targets. Its docs-only PR uses `Refs #1430`,
  never a closing keyword, and the issue stays open.
- **D3 benchmark evidence**: running the plan on isolated synthetic
  infrastructure. Needs its own owner GO with a budget.
- **D4 architecture decision**: the owner chooses one of the four outcomes
  from D3 evidence. Only D4 can close #1430.

## User stories

- AS the PA owner I WANT a pinned-code inventory of every HTTP call, SQL
  statement, transaction and lock on the PA claim path SO THAT I can see what
  idle polling costs before I approve scaling.
- AS the PA owner I WANT a benchmark plan with fixed budgets, isolation and
  authorization requirements SO THAT a later GO authorizes exactly one bounded,
  synthetic experiment and nothing else.
- AS a reviewer I WANT pass/fail targets registered before any measurement SO
  THAT the eventual results cannot be rationalized after the fact.
- AS a platform operator I WANT a dashboard specification that names the
  metrics to read SO THAT later measurements can tell claim-lock wait apart
  from pool wait, query time and model/tool latency.
- AS the security owner I WANT every alternative checked against the existing
  invariants SO THAT no option weakens the principal fencing, budget
  reservation or consent checks. The invariants are: at most one claimed job
  per principal, lease and attempt fencing, consent, revocation and allowlist
  gating, and the global budget.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL contain:
  - a sequence diagram of the current claim path, pinned to a named commit of
    `mctlhq/mctl-telegram`;
  - an inventory listing, per step: the HTTP route, each SQL statement, its
    transaction boundary, the locks it takes (advisory, row, upsert-as-lock)
    and whether it writes rows.
- WHEN the report states a fact about the claim path THE SYSTEM SHALL label
  it either `OBSERVED (code)` with a file and symbol reference, or
  `HYPOTHESIS` with the measurement that would confirm or refute it.
- WHEN the report quotes request rates THE SYSTEM SHALL mark them as derived
  arithmetic (slots / poll interval), never as measured PostgreSQL QPS or
  latency.
- WHEN the benchmark plan is written THE SYSTEM SHALL specify:
  - synthetic fixtures only (personas Alice/Bob/Carol/Dana and synthetic ids);
  - the experiment model, with each term defined: replicas `R`, concurrency
    per replica `C`, total claim slots `S = R x C`; arrival rate `lambda`
    (jobs/s); job duration (stub model latency distribution); enrolled
    principals versus concurrently active principals; warm-up that is
    discarded; repetitions per cell; and the minimum sample count for each
    reported percentile (a cell below it reports `insufficient`, not a value);
  - the scenario matrix: `S` = 1/5/10/20, each realised both by replicas and
    by concurrency where possible; 20/100/1,000 enrolled principals; idle,
    steady and synchronized-burst load;
  - two workload profiles: PA-only, and PA plus a synthetic competing
    managed-budget workload on every other path that takes the same advisory
    lock (managed agent claim, managed turn claim, PA writes);
  - an isolated PostgreSQL instance and a stub model with no real connector or
    tool effects;
  - equivalent, stated resource limits per component and cohort;
  - fixed wall-clock, compute and total cost budgets;
  - the named owner GO required before the run.
- WHEN the dashboard specification is written THE SYSTEM SHALL name, for each
  metric listed in the issue's deliverables, its source and whether it exists
  today (for example `mctl_pa_run_phase_seconds` in `internal/metrics/pa.go`)
  or would need new instrumentation. The sources are a Prometheus metric,
  `pg_stat_statements`, `pg_locks`/`pg_stat_activity` wait events,
  `database/sql` `DBStats`, or a trace span.
- WHEN the measurement contract is written THE SYSTEM SHALL define three
  separate latency intervals: created-to-claim, runnable-to-claim (from the
  moment a job became due: the latest of created, `retry_at_ms` and
  `held_until_ms`) and claim-to-worker-start. For every metric it SHALL state
  units, bounded labels (no principal, job or conversation id as a label),
  missing-data semantics (a missing sample is unknown, never zero) and how
  fairness is computed as an aggregate over the cohort rather than per
  principal.
- WHEN the measurement contract names a metric that #1445 (traces, stage
  latency) or #1446 (usage, cost) already defines THE SYSTEM SHALL reference
  theirs instead of defining a second one, and SHALL use the shared
  `job_id` + `attempt` correlation. The queue metrics defined here are the
  source #3004 consumes for its queue panels.
- WHEN the measurement contract is written THE SYSTEM SHALL include a
  process resource contract per component (server, worker, PostgreSQL): CPU
  seconds, CPU throttling, Go GC pause and frequency, heap and RSS, aligned
  with the shared runtime baseline mctlhq/mctl-agents#1131.
- WHEN pass/fail targets are recorded THE SYSTEM SHALL record them for both a
  20-person and a 100-person read-only pilot. They SHALL cover claim latency
  p95/p99, time-to-start p95, per-principal fairness, DB headroom (connections,
  CPU, lock wait), and zero tolerance for duplicate claims, cross-principal
  claims and usage-ledger mismatches. All of this SHALL be committed before
  any benchmark result.
- WHEN the decision record is written THE SYSTEM SHALL:
  - list all four outcomes with cost, tradeoffs and rollback for each;
  - select no outcome. `KEEP_POSTGRES_POLLING` is stated as the baseline
    hypothesis the benchmark tests against, not as a decision; the record
    reads `AWAITING D3 EVIDENCE`;
  - name the follow-up implementation issues it would open, without opening or
    implementing them.
- WHILE the HOLD is in force THE SYSTEM SHALL change no Go source, schema,
  configuration, GitOps value, replica count or concurrency setting.
- IF an alternative relaxes the order in which locks are taken, or adds
  `SKIP LOCKED`, THEN the report SHALL state how it preserves each of these,
  or SHALL reject the alternative:
  - global-budget serialization;
  - principal-lock-before-row ordering;
  - the `idx_pa_jobs_running` one-claimed-per-principal invariant;
  - oldest-first fairness.
- IF an alternative moves `ExpirePAJobs` off the claim path (a timer, a
  conditional probe or a separate worker) THEN the report SHALL state how it
  preserves the `expired` status transition, exactly-once notice enqueue
  (`RETURNING`) and the `pa_usage` reserved-to-held reconciliation; SHALL
  define the cleanup latency it allows (an expired claimed job blocks its
  principal through `idx_pa_jobs_running`, so this latency is user-visible);
  and SHALL define behaviour when the expirer fails or restarts (catch-up on
  start, no double notice, more than one replica).
- IF the report discusses `LISTEN/NOTIFY` THEN it SHALL treat NOTIFY only as
  a best-effort wake-up hint over the durable `pa_jobs` table, keep a polling
  fallback, and never treat it as a durable queue.
- IF the report discusses an external queue THEN it SHALL price dual-write or
  outbox, redelivery, deduplication and operational overhead against the
  PostgreSQL options.

## Out of scope

- Running any benchmark, load test or preview experiment (D3). That needs a
  new owner GO. #1317 (security suite S1) is completed; the #1319 (R1-R6
  evals) and #1324 (private pilot) gates stay in force for anything touching
  the preview.
- The architecture decision itself (D4).
- Any change to Go code, SQL schema, indexes, the claim protocol, the poll
  interval, `AGENT_WORKER_CONCURRENCY`, `replicaCount` or other GitOps values.
- Adopting Redis or any other broker. Phase 2. Pilot expansion to 20 real
  users.
- Changing budget, consent, revocation, allowlist or authorization semantics.
- Treating this research as a Phase 1 launch blocker without measured
  evidence.
- MTProto session scaling (#1282), other PA P3 follow-ups (#1399), the
  managed conversation-plane rollout (#889), and a Rust or other language
  rewrite (named in the 2026-11-27 runtime-profiling note).

## Open questions

- The issue pins `1a19b2266fb8d9f1fb299a2c070acd00d1a290be`. This clone and
  the deployed preview image are at `13fd2333a041c3a0a2634db29879bfa116250bf6`
  (`main-13fd233`), and the issue's line numbers no longer match. The report
  pins `13fd233` and notes the difference. The reviewer should confirm that
  this pin is acceptable.
- The issue says the preview has "five idle concurrency slots". GitOps shows
  `replicaCount: 1` and `AGENT_WORKER_CONCURRENCY: "1"`, which is one slot,
  about 0.5 claim requests/s by derivation. The report treats five slots as a
  hypothetical scenario, not as current state.
- Which PostgreSQL instance and version would host the isolated benchmark, and
  whether `pg_stat_statements` is available there. The shared CNPG cluster
  must not be used without the owner's say.
- The fixed benchmark budget (wall-clock hours, compute) is not given. The
  plan proposes defaults: at most 4 hours wall-clock, and model spend of $0
  because a stub model is used. The owner can change these at GO time.
- `PAWorker.PollInterval` has no environment variable (`cmd/agent-worker/pa_mode.go`
  never sets it), so changing it means a code change. Whether that counts as a
  config-only change for option B is the owner's call.
