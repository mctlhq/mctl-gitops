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
- [ ] 5. (depends on 4) Add the dashboard specification and pre-registered
  pass/fail targets (20-person and 100-person pilots) to the plan. DoD: every
  metric from the issue's deliverables has a source and an exists/new marker.
  The targets include zero duplicate-claim, cross-principal and
  ledger-mismatch violations. They are marked "frozen at GO".
- [ ] 6. (depends on 3, 5) Write the decision record section in the report:
  provisional `KEEP_POSTGRES_POLLING`, plus the list of
  `OPTIMIZE_POSTGRES_CLAIM` follow-ups and their triggers (which target
  failing would open which issue), plus the owner GO/NO-GO checklist. DoD:
  status reads "PROVISIONAL - AWAITING BENCHMARK GO". The record states that
  this is not a Phase 1 launch blocker.
- [ ] 7. (depends on 2-6) Open a docs-only PR against `mctlhq/mctl-telegram`
  with the commit `docs: add PA job-queue scaling spike report and benchmark
  plan (#1430)`. DoD: CI is green and the PR body restates the HOLD.

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
- [ ] T5. Consistency: the derived-rate table matches slots / 2 s, and the
  decision record's provisional outcome matches the report summary.

## Rollback

The change is documentation only. Revert the merge commit or delete the two
files. No runtime, schema or deployment state is affected.
