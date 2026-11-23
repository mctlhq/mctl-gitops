# Design: issue-1405-feat-forks-s2-eval-runs-tasks-1-3-config

## Current state

Design reference: the #1403 proposal
(`platform-gitops/agents-state/mctl-telegram/proposals/issue-1403-p4-3-fork-promotion-observe-baseline-eva/`,
S2 tasks 1-3 and "Proposed solution / S2" items 1-2) and
`docs/assistants/adr-forks.md` ("Promotion (P4.3)", "P4.3 decisions").
Anchors below were read in a fresh clone of mctl-telegram `main` at
`6743ffd` (merge of release PR #1394). Re-read them before implementing.

- **Config.** `internal/config/config.go:506-511` declares
  `AssistantForksEnabled`, parsed at `:805` with
  `envBool("ASSISTANT_FORKS_ENABLED", false)`. `cmd/server/main.go:642`
  wires it into `assistantSvc.ForksEnabled` and `:645` logs
  `slog.Info("assistant forks", "enabled", ...)`. Config tests are split per
  feature (`internal/config/config_managed_test.go`, `config_pa_test.go`,
  ...). No `ASSISTANT_FORK_EVAL_ENABLED` exists.
- **Fork storage.** `internal/db/agent_schema.go` creates `assistant_forks`
  in `agentSchemaSQLite` (`:852-868`) and `agentSchemaPG` (`:1227-1243`):
  PK `(user_id, name, version)`, unique index `(user_id, digest)`,
  `user_id ... REFERENCES users(id) ON DELETE CASCADE`. SQLite uses
  `INTEGER`/`DATETIME`/`BLOB`, PG uses `BIGINT`/`TIMESTAMPTZ`/`BYTEA` and
  `BIGSERIAL`, as `agent_jobs` (`:669`, `:1068`) shows.
- **Fork lock.** `internal/db/assistant_forks.go:80` `beginForkTx` opens a
  transaction holding the account's row lock on `users`
  (`SELECT ... FOR UPDATE` on PG, `UPDATE users SET id = id` on SQLite). It
  resolves the dialect with `postgresDialect` (`agent_jobs.go:159`) before
  `BeginTx`. Typed errors live in a `var (...)` block at `:28-39`
  (`ErrAssistantForkNotFound`, `ErrForkLimit`, `ErrForkConflict`,
  `ErrForkInUse`).
- **Fork delete.** `DeleteAssistantFork` (`assistant_forks.go:319`) runs
  under `beginForkTx`. It refuses with `ErrForkInUse` when a version to delete
  is pinned by `agent_profiles`, then runs `DELETE FROM assistant_forks WHERE
  <where>`, then refuses with `ErrAssistantForkNotFound` when no rows were
  deleted (rolled back), then commits.
- **Purge.** `purgeAgentData` (`internal/db/agent_domain.go:769`) runs
  `purgeAgentJobsHook` (set in `agent_jobs.go:1190`), then a fixed list of
  `DELETE ... WHERE user_id = $1` statements, including
  `assistant_forks`. `internal/db/agent_purge_test.go:81` lists the tables
  asserted empty after `HardDeleteAccount`.
- **Dual-engine tests.** `internal/db/assistant_forks_test.go:14` runs one
  check function on SQLite (`newTestStoreCrypted`) and on Postgres when
  `TEST_DATABASE_URL` is set (`newPostgresTestStore`). Migration tests are in
  `internal/db/agent_schema_test.go` (e.g. `TestMigrate_CreatesUsageLedger`
  `:454`).
- **Sweepers.** `internal/sweeper/sweeper.go` has one loop function per job
  (`Sessions`, `AuditLog`, `RefreshTokens`, `JobLeads`, `AgentRetention`,
  ...), each running once at boot and then on a ticker, logging failures at
  warn and non-zero counts at info. `cmd/server/main.go:419-447` starts them
  with `go sweeper.X(ctx, store, ...)`.
- **Import direction.** `internal/agenteval/fake.go` and `target.go` import
  `internal/db`, so `internal/db` cannot import `internal/agenteval` (cycle).
  `agenteval.RunBinding` (`binding.go:16`) is
  `{UserID, ForkDigest, BaseDigest, SuiteDigest, HarnessVersion}`, and
  `agenteval.Score` produces a `Report` (`score.go:25`).
- grep over the clone finds no `assistant_fork_eval`, `ForkEval` or
  `ASSISTANT_FORK_EVAL_ENABLED`.

Deployed state checked:

- `mctl_get_service_config(labs, mctl-telegram)`: image tag `0.142.0`, host
  `tg.mctl.ai`, `hasDatabase: true` (Postgres in production).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tag `0.142.0`.
  `services/labs/mctl-telegram-preview/values.yaml`: tag `main-eb1ac9c`.
- grep for `ASSISTANT_FORK` over `$MCTL_GITOPS_ROOT/services`: no match. Forks
  and the new eval flag are therefore off everywhere (default false).
- Runtime status, pods and logs were not observed (not needed for a slice
  that adds an off-by-default flag and additive tables). This is a gap, not
  an observation that they are absent.

## Proposed solution

One PR, three tasks. No route, audience, worker or UI change.

### Task 1: flag

- `internal/config/config.go`: add `AssistantForkEvalEnabled bool` after
  `AssistantForksEnabled`, with a doc comment (P4.3 S2 eval runs, off by
  default, nothing reads it yet), parsed as
  `envBool("ASSISTANT_FORK_EVAL_ENABLED", false)`.
- `cmd/server/main.go`: extend the startup log line at `:645` to
  `slog.Info("assistant forks", "enabled", cfg.AssistantForksEnabled,
  "eval_enabled", cfg.AssistantForkEvalEnabled)`. The flag is logged at the
  same site so an operator reads both together. It is not wired into
  `assistantSvc` yet. If that line sits inside a branch that does not always
  run, log the flag unconditionally next to the sweeper start instead.
- `internal/config/config_forkeval_test.go`: unset gives false, `"true"`
  gives true, `"false"` gives false, matching the existing `envBool` tests.

### Task 2: schema, purge, delete

New statements appended to both schema lists (SQLite types shown; PG uses
`BIGSERIAL`/`BIGINT`/`TIMESTAMPTZ`/`BYTEA`):

```sql
CREATE TABLE IF NOT EXISTS assistant_fork_eval_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  fork_digest TEXT NOT NULL,
  base_digest TEXT NOT NULL,
  suite_digest TEXT NOT NULL,
  harness_version TEXT NOT NULL,
  state TEXT NOT NULL,          -- queued|running|passed|failed|incomplete|expired|cancelled
  created_at DATETIME NOT NULL,
  finished_at DATETIME,
  report_json BLOB              -- gates + per-fixture rows, no text
);
CREATE INDEX IF NOT EXISTS idx_fork_eval_runs_digest
  ON assistant_fork_eval_runs(user_id, fork_digest, created_at);
CREATE INDEX IF NOT EXISTS idx_fork_eval_runs_state
  ON assistant_fork_eval_runs(state, created_at);

CREATE TABLE IF NOT EXISTS assistant_fork_eval_tasks (
  run_id INTEGER NOT NULL REFERENCES assistant_fork_eval_runs(id) ON DELETE CASCADE,
  fixture_id TEXT NOT NULL,
  seq INTEGER NOT NULL,         -- fixture order within the suite
  attempt INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL,          -- pending|claimed|done|infra_failed
  deadline DATETIME,
  result_json BLOB,
  PRIMARY KEY (run_id, fixture_id)
);
CREATE INDEX IF NOT EXISTS idx_fork_eval_tasks_claim
  ON assistant_fork_eval_tasks(state, deadline);
```

`created_at` is written explicitly from Go (`time.Now().UTC()`) rather than
defaulted, so the 24 h window comparisons use one clock on both engines.
Ints, not text ids: the run id is internal, and task 4 binds tokens to it.

- `purgeAgentData`: insert, before `assistant_forks`,
  `DELETE FROM assistant_fork_eval_tasks WHERE run_id IN (SELECT id FROM
  assistant_fork_eval_runs WHERE user_id = $1)` and
  `DELETE FROM assistant_fork_eval_runs WHERE user_id = $1`. They are
  explicit even though `ON DELETE CASCADE` exists, because `HardDeleteAccount`
  keeps the `users` row (the tombstone comment in `purgeAgentData` says the
  identity survives).
- `DeleteAssistantFork`: after the `ErrForkInUse` check and before the
  `DELETE`, run
  `UPDATE assistant_fork_eval_runs SET state='cancelled', finished_at=$n
   WHERE user_id=$1 AND state IN ('queued','running') AND fork_digest IN
   (SELECT digest FROM assistant_forks WHERE <where>)`. It is in the same
   transaction, so the `ErrAssistantForkNotFound` rollback also undoes it.
   Tasks of a cancelled run are left as they are: claim and finish check the
   run state.

### Task 3: store (`internal/db/assistant_fork_evals.go`)

Constants and types:

```go
const (
  ForkEvalQueued, ForkEvalRunning, ForkEvalPassed, ForkEvalFailed,
  ForkEvalIncomplete, ForkEvalExpired, ForkEvalCancelled = "queued", ...
  ForkEvalRunTTL          = 24 * time.Hour
  forkEvalOpenPerAccount  = 1
  forkEvalPerAccount24h   = 3
  forkEvalGlobal24h       = 20
  forkEvalScoredPerDigest = 2
  forkEvalMaxAttempts     = 2 // one infrastructure retry
)
var (
  ErrForkEvalRunOpen, ErrForkEvalAccountLimit, ErrForkEvalGlobalLimit,
  ErrForkEvalDigestPassed, ErrForkEvalDigestLimit,
  ErrForkEvalNoTask, ErrForkEvalTaskStale, ErrForkEvalRunNotFound error
)
type ForkEvalBinding struct{ UserID int64; ForkDigest, BaseDigest, SuiteDigest, HarnessVersion string }
type ForkEvalRun struct{ ID int64; ForkEvalBinding; State string; CreatedAt time.Time; FinishedAt *time.Time; Report []byte }
type ForkEvalTask struct{ RunID int64; Binding ForkEvalBinding; FixtureID string; Attempt int; Deadline time.Time }
type ForkEvalTaskResult struct{ FixtureID string; Result []byte }
type ForkEvalScorer func(results []ForkEvalTaskResult) (passed bool, report []byte, err error)
```

`ForkEvalBinding` mirrors `agenteval.RunBinding` field for field, so task 5
converts between them without the store importing `agenteval`. Each error
value is a distinct `errors.New` with a stable machine string
(`eval_run_open`, `eval_account_limit`, ...) that later routes can surface.

- `CreateForkEvalRun(ctx, b ForkEvalBinding, fixtureIDs []string, now time.Time) (int64, error)`.
  It validates the input (no empty field, at least one fixture, no
  duplicate), then calls `beginForkTx(b.UserID)` and runs, in order:
  `SELECT 1 FROM assistant_forks WHERE user_id=$1 AND digest=$2`
  (`ErrAssistantForkNotFound`); the open count for the account; the account
  count with `created_at > now-24h`; the global count with
  `created_at > now-24h`; then per digest `COUNT(*) FILTER passed` and the
  scored count (as `SUM(CASE ...)` for SQLite compatibility). The first limit
  hit returns its typed error, and the deferred `Rollback` discards the
  transaction, so nothing is written. Otherwise it inserts the run
  (`queued`) and one `pending` task per fixture (`seq` = index), then
  commits. The ordering puts the cheap per-account checks before the global
  scan.
- `ClaimForkEvalTask(ctx, userID int64, now time.Time, lease time.Duration) (*ForkEvalTask, error)`.
  `userID > 0` restricts to that account (the account `agent` token caller).
  `userID == 0` means any account (the pool credential, confirmed by the
  owner on 2026-11-22). In one transaction (a plain transaction, not the fork
  lock, because pool claims span accounts):
  1. Expire the overdue: tasks `claimed` with `deadline <= now` and
     `attempt >= forkEvalMaxAttempts` set their run to `incomplete` (only
     while it is `running`).
  2. Select the first candidate in an open run (`queued`/`running`, created
     after `now-24h`): a `pending` task, or a `claimed` task with
     `deadline <= now` and `attempt < forkEvalMaxAttempts`. Order by run
     `created_at`, `seq`.
  3. Take it with a guarded `UPDATE ... SET state='claimed',
     attempt=attempt+1, deadline=now+lease WHERE run_id=? AND fixture_id=?
     AND state=? AND attempt=?`. 0 rows means a concurrent claim won, so the
     transaction rolls back and `ErrForkEvalNoTask` is returned. The caller
     polls again. Set the run `queued -> running`.
  It returns the task with its binding. `ErrForkEvalNoTask` when there is no
  candidate.
- `FinishForkEvalTask(ctx, runID int64, fixtureID string, attempt int, infraFailed bool, result []byte, score ForkEvalScorer, now time.Time) (state string, err error)`.
  In one transaction: the run must be `running` and the task `claimed` at
  `attempt` (otherwise `ErrForkEvalTaskStale`, nothing written). If
  `infraFailed`, mark the task `infra_failed` and the run `incomplete`.
  Otherwise mark the task `done` with `result`. If no task of the run is left
  in another state than `done`, load all results ordered by `seq`, call
  `score`, and store `passed`/`failed` plus `report_json` and `finished_at`.
  A scorer error rolls the transaction back and is returned wrapped. It
  returns the run's state after the call. `result` is stored as given. The
  doc comment states the caller contract: no model output text.
- `LatestScoredForkEvalRun(ctx, userID int64, digest string) (*ForkEvalRun, error)`:
  `WHERE user_id=$1 AND fork_digest=$2 AND state IN ('passed','failed')
  ORDER BY created_at DESC, id DESC LIMIT 1`. `ErrForkEvalRunNotFound` on no
  rows. The same `IN ('passed','failed')` predicate is the scored count in
  `CreateForkEvalRun`, and both reference one shared SQL fragment constant.
- `ExpireForkEvalRuns(ctx, now time.Time) (int64, error)`:
  `UPDATE ... SET state='expired', finished_at=$1 WHERE state IN
  ('queued','running') AND created_at <= $2` with `$2 = now - ForkEvalRunTTL`.
- `internal/sweeper/sweeper.go`: add `ForkEvalSweeperInterval =
  15 * time.Minute` and `ForkEvals(ctx, store)`, shaped like
  `RefreshTokens`: once at boot, then on the ticker, with a warn log on error
  and an info log with `expired_runs` when non-zero. `cmd/server/main.go`
  starts it next to the other sweepers. It starts unconditionally, not behind
  the flag. With no rows it is one indexed `UPDATE` per 15 minutes, and it
  still expires runs left open if the flag is turned off later. This keeps
  "nothing reads the flag yet" true.

## Alternatives

- **Let the store compute the verdict by importing `internal/agenteval`.**
  Dropped: `agenteval` imports `db`, so this is an import cycle. Moving
  `Score` into `db` would couple storage to the harness. A scorer callback
  keeps scoring server-side and atomic with the last task's write.
- **Finish the run in a separate `CompleteForkEvalRun` call after the last
  task.** Dropped: between the two calls a run would sit with all tasks done
  but unscored, and a crash there would need another sweep state. The issue
  also names exactly five store functions.
- **Enforce the global 20/day limit with a global advisory lock or an
  in-memory counter.** Dropped: an in-memory counter is wrong with more than
  one replica. A global lock serializes every account's eval writes for a
  limit the ADR treats as approximate. The #1403 design accepts a rare 21st
  run.
- **Start the expiry sweeper only when the flag is on.** Dropped: the flag
  would then be read beyond the startup log, which the issue forbids for this
  slice. Runs left open across a flag flip would also never expire.

## Platform impact

- **Migrations.** These are additive only: two new tables and three indexes,
  `IF NOT EXISTS`, on both engines. No existing table or column changes. No
  backfill.
- **Backward compatibility.** The flag is off and no route writes the
  tables, so they stay empty in every deployment. `DeleteAssistantFork` gains
  one `UPDATE` that matches nothing today. `purgeAgentData` gains two
  `DELETE`s that match nothing today. An older binary ignores the tables.
- **Resource impact.** One indexed `UPDATE` every 15 minutes per replica.
  It is idempotent, so running it on several replicas is safe.
- **Risks and mitigations.**
  - *A limit check is bypassed by a concurrent request of the same account.*
    Mitigation: all per-account checks and the insert run under
    `beginForkTx`. A test runs two concurrent creates for one account and
    expects exactly one to succeed.
  - *A non-scored run backs a promotion later.* Mitigation: one shared
    `scored` predicate, with tests for each of `incomplete`, `expired` and
    `cancelled`.
  - *Private text lands in `result_json`/`report_json`.* Mitigation: the
    store has no text fields of its own. The caller contract is documented,
    and task 5 owns the no-text test (T10 of #1403). No new field is logged,
    so `internal/audit/redact.go` needs no change.
  - *SQLite/PG divergence (`FILTER`, `FOR UPDATE`, time types).* Mitigation:
    portable `SUM(CASE ...)`, the existing `beginForkTx` dialect handling, and
    every store test run on both engines through the `assistant_forks_test.go`
    pattern.
