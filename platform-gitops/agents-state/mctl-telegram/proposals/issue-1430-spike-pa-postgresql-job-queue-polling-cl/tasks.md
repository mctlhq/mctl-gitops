# Tasks: issue-1430-spike-pa-postgresql-job-queue-polling-cl

All tasks are documentation-only. Do not change Go source, schema, GitOps
values, replicas or concurrency, and do not run any benchmark or load test.

- [ ] 1. Re-verify the pin. Confirm the claim path at the commit being
  documented (`13fd233` or newer `main`) in these files:
  - `internal/agentworker/parunner.go` (`Loop`, `loop`, `Claim`);
  - `cmd/agent-worker/pa_mode.go`;
  - `internal/pa/runloop.go` (`serveClaim`);
  - `internal/db/pa_jobs.go` (`ClaimPAJob`, `ExpirePAJobs`, `claimOnce`,
    `claimPicked`, `backoffPAJob`, `paJobsSchema`);
  - `internal/db/agent_usage.go` (`lockManagedBudget`);
  - `internal/db/pa_convo.go` (`LockPAPrincipal`);
  - `internal/db/agent_jobs.go` (`resolveDialect`, SKIP LOCKED claim);
  - `internal/db/db.go` (pool defaults).

  DoD: the report header names the exact SHA and lists where it differs from
  the issue's `1a19b22` line references.
- [ ] 2. (depends on 1) Write `docs/reports/pa-job-queue-scaling-spike.md`
  with these sections: scope and HOLD; a Mermaid sequence diagram (empty and
  picked branches); the SQL/lock inventory table; observations versus
  hypotheses H1-H5; the invariant register; the derived-rate table, labelled
  "derived, not measured". DoD: every row is labelled `OBSERVED (code)` with a
  file/symbol or `HYPOTHESIS` with its confirming measurement. All other
  lock-sharing paths are listed (`agent_jobs.go`, `agent_turn_claim.go`,
  `pa_jobs.go` `beginRunningLocked`, `pa_writes.go`).
- [ ] 3. (depends on 2) In the same report, add an alternatives analysis of
  A, B, C and D. DoD: each option is scored against every invariant in the
  register. The report also covers:
  - `SKIP LOCKED` explicitly, as redundant under the global lock;
  - NOTIFY as a hint only, with a polling fallback and the HTTP-worker
    constraint;
  - the broker's cost of outbox, redelivery, dedup and operations;
  - a rollback for each option.
- [ ] 4. (depends on 1) Write `docs/plans/pa-queue-benchmark.md`: isolation,
  synthetic fixtures (Alice/Bob/Carol/Dana plus generated synthetic ids), the
  scenario matrix (slots 1/5/10/20 x concurrency 1/2; principals
  20/100/1,000; idle/steady/burst; faults), equal resource limits, the fixed
  budget (at most 4 h, $0 model spend via a stub), and the required owner GO
  with the #1317/#1319/#1324 gates. Include the `EXPLAIN (ANALYZE, BUFFERS)`
  queries to run on synthetic data. DoD: an operator could execute it without
  further design. It states "not run; requires GO".
  Also in the plan: the experiment model from design.md (`R`, `C`, `S`,
  `lambda`, utilisation levels, job duration profiles, enrolled `N` versus
  active `A`, 2-minute warm-up, at least 5 repetitions, minimum samples per
  percentile with `insufficient` below it); the two workload profiles
  (PA-only, PA plus competing managed-budget paths); and the stated resource
  limits, compute ceiling and total cost ceiling. #1317 is recorded as
  completed; #1319 and #1324 stay in force.
- [ ] 5. (depends on 4) Add the measurement contract, dashboard
  specification and pre-registered pass/fail targets (20-person and
  100-person pilots) to the plan: the three latency intervals
  (created-to-claim, runnable-to-claim, claim-to-worker-start), units,
  bounded labels, missing-data semantics, aggregate fairness, the process
  resource contract (CPU, throttling, GC, heap/RSS per component), and a
  reference table to the #1445/#1446 metrics it reuses. DoD: every metric
  from the issue's deliverables has a source and an exists/new marker; no
  metric duplicates one from #1445 or #1446; the interval measured by
  `mctl_pa_run_phase_seconds{phase="queue"}` is verified at the pin.
  The targets include zero duplicate-claim, cross-principal and
  ledger-mismatch violations. They are marked "frozen at GO".
- [ ] 6. (depends on 3, 5) Write the decision record skeleton in the report:
  no outcome selected; `KEEP_POSTGRES_POLLING` as the baseline hypothesis;
  for each target, which outcome its failure would point to; the
  `ExpirePAJobs` preservation conditions (status, notices, usage
  reconciliation, cleanup latency, failure/restart) that any off-claim-path
  variant must meet; the owner checklists for the D3 GO and the D4 decision.
  DoD: status reads "AWAITING D3 EVIDENCE". The record states that this is
  not a Phase 1 launch blocker.
- [ ] 7. (depends on 2-6) Open a docs-only PR against `mctlhq/mctl-telegram`
  with the commit `docs: add PA job-queue scaling spike report and benchmark
  plan (#1430)`. DoD: CI is green, the PR body restates the HOLD and uses
  `Refs #1430` (no closing keyword); #1430 stays open for D3 and D4.

## Tests

- [ ] T1. `go test ./docs/...` passes. Doc guard tests such as
  `docs/runbook_test.go` and `docs/pa_*_manifest_test.go` are not broken by
  the new files.
- [ ] T2. `git diff --stat main` touches only `docs/reports/pa-job-queue-scaling-spike.md`
  and `docs/plans/pa-queue-benchmark.md`.
- [ ] T3. Spot-check the citations: every file path and symbol cited in the
  report exists at the pinned SHA (`git grep` each symbol).
- [ ] T4. Fixture hygiene: the plan contains no real Telegram id, name or
  handle. Any numeric id is checked with `git grep <id>` per CLAUDE.md.
- [ ] T5. Consistency: the derived-rate table matches slots / 2 s, and
  neither the report summary nor the decision record selects an outcome.
- [ ] T6. Contract review: every metric in the measurement contract has
  units, bounded labels and a missing-data rule; none is also defined in the
  #1445 or #1446 proposals; every scenario cell states `R`, `C`, `lambda`,
  duration profile, workload profile and its minimum sample count.

## Rollback

The change is documentation only. Revert the merge commit or delete the two
files. No runtime, schema or deployment state is affected.
