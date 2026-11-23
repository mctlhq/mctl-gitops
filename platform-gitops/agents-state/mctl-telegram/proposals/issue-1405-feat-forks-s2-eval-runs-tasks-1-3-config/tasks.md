# Tasks: issue-1405-feat-forks-s2-eval-runs-tasks-1-3-config

One PR. These are S2 tasks 1-3 of the #1403 proposal only. No route, token
audience, worker, UI or gitops change.

- [ ] 1. Add `AssistantForkEvalEnabled` (`ASSISTANT_FORK_EVAL_ENABLED`,
  `envBool`, default false) to `internal/config/config.go` next to
  `AssistantForksEnabled`, and log it in `cmd/server/main.go` as
  `eval_enabled` on the `"assistant forks"` startup line (`:645`), or
  unconditionally next to the sweeper start if that line is conditional.
  Nothing else reads it. — DoD: the flag is parsed, logged at startup, and
  covered by `internal/config/config_forkeval_test.go`. grep shows no other
  reader.
- [ ] 2. Add `assistant_fork_eval_runs` and `assistant_fork_eval_tasks`, plus
  indexes `idx_fork_eval_runs_digest`, `idx_fork_eval_runs_state` and
  `idx_fork_eval_tasks_claim`, to `agentSchemaSQLite` and `agentSchemaPG` in
  `internal/db/agent_schema.go`, as in design.md. Add the two `DELETE`s to
  `purgeAgentData` (`internal/db/agent_domain.go`) before `assistant_forks`.
  In `DeleteAssistantFork` (`internal/db/assistant_forks.go`), cancel the
  `queued`/`running` runs of the deleted digests in the same transaction,
  after the `ErrForkInUse` check and before the `DELETE`. — DoD: the
  migration test passes on SQLite and on Postgres (`TEST_DATABASE_URL`),
  migrating twice is a no-op, and `agent_purge_test.go` covers both new
  tables.
- [ ] 3. (depends on 2) Add `internal/db/assistant_fork_evals.go` with the
  state constants, limits, typed errors, `ForkEvalBinding`, `ForkEvalRun`,
  `ForkEvalTask`, `ForkEvalTaskResult`, `ForkEvalScorer` and
  `CreateForkEvalRun` (every limit checked under `beginForkTx`),
  `ClaimForkEvalTask` (account-scoped or any-account), `FinishForkEvalTask`
  (scores the run through the scorer when the last task finishes),
  `LatestScoredForkEvalRun` and `ExpireForkEvalRuns`. Do not import
  `internal/agenteval`. Add `sweeper.ForkEvals` (15 min interval, boot run)
  to `internal/sweeper/sweeper.go` and start it in `cmd/server/main.go` next
  to the other sweepers. — DoD: every limit refuses with its typed error and
  writes nothing. Expired, incomplete and cancelled runs are never returned
  by `LatestScoredForkEvalRun` and never count as scored. All store tests
  pass on both engines. `go vet`, `golangci-lint` and `go test ./...` are
  green.

## Tests

- [ ] T1. Config: `ASSISTANT_FORK_EVAL_ENABLED` unset gives false, `true`
  gives true, `false` gives false.
- [ ] T2. Migration (`agent_schema_test.go`, both engines): both tables and
  three indexes exist after `Migrate`, and a second `Migrate` succeeds
  unchanged.
- [ ] T3. Purge (`agent_purge_test.go`): seed a fork, a run and two tasks for
  the user, then `HardDeleteAccount` leaves 0 rows in
  `assistant_fork_eval_runs` for the user and 0 tasks for its run ids. A
  second account's run survives.
- [ ] T4. Fork delete: deleting a version cancels its `queued` and `running`
  runs (with `finished_at` set) and leaves `passed`/`failed` runs and the
  runs of other digests and accounts untouched. A delete refused with
  `ErrForkInUse` or `ErrAssistantForkNotFound` leaves every run unchanged.
- [ ] T5. Limits (`assistant_fork_evals_test.go`, both engines), each
  asserting the typed error and unchanged row counts in both tables: a second
  open run (`ErrForkEvalRunOpen`); a 4th run in 24 h
  (`ErrForkEvalAccountLimit`), allowed again once the oldest is older than
  24 h; a 21st global run (`ErrForkEvalGlobalLimit`); a run after a pass
  (`ErrForkEvalDigestPassed`); a third run after two fails
  (`ErrForkEvalDigestLimit`); a second run after one fail succeeds; an
  unknown digest or another account's digest (`ErrAssistantForkNotFound`);
  empty fixtures or a duplicate fixture id or an empty binding field
  (refused).
- [ ] T6. Not scored: a digest with one `incomplete`, one `expired` and one
  `cancelled` run still accepts a new run (they do not count toward
  `ErrForkEvalDigestLimit`), and `LatestScoredForkEvalRun` returns
  `ErrForkEvalRunNotFound`. With a `failed` and a newer `passed` run it
  returns the `passed` one.
- [ ] T7. Claim: account-scoped claim never returns another account's task.
  Any-account claim (`userID == 0`) does. The run moves `queued -> running`.
  A timed-out task at attempt 1 is re-offered at attempt 2. A timed-out task
  at attempt 2 makes the run `incomplete` and is not offered. Tasks of
  cancelled or expired runs are never offered. No candidate gives
  `ErrForkEvalNoTask`.
- [ ] T8. Finish: finishing the last task calls the scorer once with all
  results in `seq` order and stores its verdict and report. A scorer that
  returns `failed` gives a `failed` run, whatever the task results contain.
  A scorer error leaves the task `claimed` and the run `running`. A stale
  attempt, an unclaimed task or a non-running run gives
  `ErrForkEvalTaskStale` with no write. `infraFailed` gives an `incomplete`
  run.
- [ ] T9. Expiry: `ExpireForkEvalRuns(now)` expires open runs created at or
  before `now-24h`, leaves younger and finished runs alone, and returns the
  count. `sweeper.ForkEvals` runs once at boot (sweeper test with a cancelled
  context, as for the existing sweepers).
- [ ] T10. Concurrency: two concurrent `CreateForkEvalRun` calls for one
  account give exactly one success and one `ErrForkEvalRunOpen`. Two
  concurrent `ClaimForkEvalTask` calls on a one-task run give one task and
  one `ErrForkEvalNoTask`.

## Rollback

Revert the PR. The flag is off and unread, and no route writes the new
tables, so reverting changes no behaviour. The tables are additive and empty.
They can stay in place harmlessly (an older binary ignores them), or be
dropped later in a cleanup change. No gitops or data rollback is needed.
