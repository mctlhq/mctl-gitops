# Tasks: issue-90-beta-capacity-profile-load-test-tuned-co

> **IMPLEMENTER SCOPE (this PR): tasks 1, 2, 3 and tests T1, T2, T3 ONLY.**
> These are pure code/test deliverables: the `DB_MAX_*` config wiring, the
> `db.Open` pool parameters, the `test/load/` binary, and the CI build step.
>
> **Tasks 4-8 are DEFERRED — DO NOT attempt them in this PR.** They require
> running the load-test binary against live 1 GiB / 2 GiB staging pods and
> recording *measured* numbers (saturation points, RSS curves, DB pool
> pressure). The implementer cannot run a real load test, so it MUST NOT
> fabricate, estimate, or guess any of those values. Tasks 4-8 (the load-test
> runs, `docs/load-test-beta.md`, `deploy/profiles/beta.env`, and the
> `docs/hpa.md` capacity-table update) are a manual operational follow-up
> after this code PR merges.

- [ ] 1. Add DBMaxOpenConns and DBMaxIdleConns to config.Config —
  In `internal/config/config.go`, add two fields to the Config struct after
  the existing `TelegramMaxSessions` field:
  ```go
  DBMaxOpenConns int // DB_MAX_OPEN_CONNS; 0 = use driver default
  DBMaxIdleConns int // DB_MAX_IDLE_CONNS; 0 = use driver default
  ```
  Wire them in `Load()` using the existing `envInt()` helper with 0 as the
  sentinel for "use existing default":
  ```go
  c.DBMaxOpenConns = envInt("DB_MAX_OPEN_CONNS", 0)
  c.DBMaxIdleConns = envInt("DB_MAX_IDLE_CONNS", 0)
  ```
  DoD: `go vet ./...` passes; the two fields appear in the struct and are
  populated in `Load()`; no other files changed in this task.

- [ ] 2. Consume pool config in db.Open (depends on 1) —
  In `internal/db/db.go`, update the `Open()` function signature to accept
  `maxOpenConns, maxIdleConns int` as additional parameters after `dsn`.
  In the Postgres branch (lines 36-38), replace the hardcoded values:
  ```go
  open := 10
  if maxOpenConns > 0 { open = maxOpenConns }
  idle := 2
  if maxIdleConns > 0 { idle = maxIdleConns }
  dbConn.SetMaxOpenConns(open)
  dbConn.SetMaxIdleConns(idle)
  ```
  The SQLite branch stays unchanged (MaxOpenConns=1).
  Update the single production call site in `cmd/server/main.go` (line 61)
  to pass `cfg.DBMaxOpenConns, cfg.DBMaxIdleConns`.
  DoD: `go build ./...` succeeds; all existing `go test ./...` tests pass;
  `db.Open` called with 0/0 produces identical pool limits to the prior
  hardcoded values.

- [ ] 3. Create test/load/ binary package (depends on 1, 2) —
  Create `test/load/main.go` as a standalone Go binary (`package main`).
  Implement:
  - Flag parsing: `-users int`, `-ramp duration`, `-hold duration`,
    `-target string`, `-tokens string` (path to bearer-token file, one per
    line), `-peer string` (Telegram peer for get_messages), `-out string`
    (JSON results path, default "results.json").
  - Virtual-user goroutine loop: weighted random tool selection (70/25/5);
    HTTP POST to `<target>/mcp` as JSON-RPC; latency measurement from
    request send to response read; result recorded in a mutex-protected
    result store. Inter-call sleep: uniform random 0-500 ms per goroutine.
  - Dry-run send sequence: POST prepare_send_message, extract
    `confirmation_id` from response, POST send_message with that ID and no
    `mode` field (server defaults to draft).
  - Metrics poller goroutine: scrape `<target>/metrics` every 5 s; parse
    Prometheus text format; maintain running peaks for
    mctl_telegram_client_pool_size, mctl_sessions_active,
    process_resident_memory_bytes, go_goroutines, and per-tool
    mctl_telegram_flood_wait_events_total.
  - Linear ramp: start one goroutine every `ramp / users` interval.
  - Final report: Markdown tables to stdout; JSON summary to `-out`.
  DoD: `go build ./test/load/` succeeds from the repo root; running the
  binary with `-users 1 -ramp 0s -hold 5s -target http://localhost:8080
  -tokens /dev/stdin -peer @test` produces a non-empty report with no
  compilation or panic errors (even with a non-reachable target, the report
  should show 100% errors gracefully rather than crashing).

- [ ] 4. Run load test against staging 1 GiB pod (depends on 3) —
  Provision a 1 GiB staging pod with pre-provisioned canary session(s) from
  issue #89. Set TELEGRAM_MAX_SESSIONS=270 (the existing 1 GiB
  recommendation from docs/hpa.md). Run the binary at user counts
  100, 200, and 270+ to identify the saturation point. Record raw
  results.json files in `docs/load-test-beta/raw/1gi/` (gitignored from CI
  but committed manually). Identify the concurrent-session count at which
  p99 latency exceeds the SLO threshold or error rate exceeds 1%.
  DoD: saturation point identified and noted; raw results files committed.

- [ ] 5. Run load test against staging 2 GiB pod (depends on 3) —
  Same procedure against a 2 GiB pod. Set TELEGRAM_MAX_SESSIONS=500 as an
  initial ceiling (above the 470 estimate) to avoid the cap masking the
  true saturation point. Run at user counts 200, 350, 470, 500+.
  Capture memory growth curve by recording peak RSS at each user count
  step. Capture DB pool pressure by querying `pg_stat_activity` or
  `db.Stats()` during the hold phase.
  DoD: saturation point identified; memory growth curve captured with at
  least four data points; DB pool pressure (max in-use vs max idle)
  recorded for each user-count step; raw results files committed.

- [ ] 6. Commit docs/load-test-beta.md (depends on 4, 5) —
  Create `docs/load-test-beta.md` with all required sections: test
  environment, saturation point table (1 GiB and 2 GiB), memory growth
  curve, DB connection pool pressure, FLOOD_WAIT events per tool,
  recommendations. All table cells must contain measured values; "TBD" is
  not acceptable in the committed version.
  DoD: file passes `go vet`-equivalent Markdown lint; all numeric cells
  contain values derived from task 4 and 5 data; the recommended
  TELEGRAM_MAX_SESSIONS for the 2 GiB tier is explicitly stated.

- [ ] 7. Commit deploy/profiles/beta.env (depends on 6) —
  Create `deploy/profiles/beta.env` with the eight required env vars set to
  values confirmed by the load-test results. Replace any values marked
  "estimate" in the initial draft with measured/derived values from
  docs/load-test-beta.md. Include inline comments citing the load-test
  result that justifies each value (e.g., "# saturation at 430 sessions on
  2 GiB pod; 10% headroom -> 387; rounded to 380").
  DoD: sourcing the file and starting the server with AUTH_MODE=local-dev
  produces no config-load errors; all eight required vars are present;
  no value is the same as the stub estimate without a comment explaining
  why the estimate was confirmed.

- [ ] 8. Update docs/hpa.md (depends on 6) —
  Append the 2 GiB row to the capacity table with the measured
  TELEGRAM_MAX_SESSIONS value. Add a "Beta scale-out guidance" section
  documenting: the measured saturation point; the 70% pool-utilization
  HPA trigger (unchanged); the SLO reference from issue #88; and the
  minReplicas=2 recommendation for Beta.
  DoD: the updated file renders correctly as Markdown; all numeric values
  in the new row and new section cite the load-test data; no existing rows
  or sections are removed.

## Tests

- [ ] T1. Unit test: config.Load reads DB pool env vars (task 1) —
  In `internal/config/config_test.go` (create if absent), add test cases:
  - `DB_MAX_OPEN_CONNS=25` -> `Config.DBMaxOpenConns == 25`
  - `DB_MAX_OPEN_CONNS` unset -> `Config.DBMaxOpenConns == 0`
  - `DB_MAX_IDLE_CONNS=5` -> `Config.DBMaxIdleConns == 5`
  DoD: `go test ./internal/config/... -run TestLoad` passes.

- [ ] T2. Unit test: db.Open respects pool arguments (task 2) —
  In `internal/db/` add or extend a test that calls `db.Open` against a
  SQLite in-memory DSN with maxOpenConns=0/maxIdleConns=0 (verifies healthy
  connection and existing behavior preserved) and with explicit non-zero
  values (verifies `db.Stats().MaxOpenConnections` reflects the passed
  value). Note: `SetMaxIdleConns` does not surface in `db.Stats()` on SQLite
  (single-conn mode), so the non-zero test may need a Postgres DSN from a
  test environment variable or be skipped with `t.Skip` when unavailable.
  DoD: `go test ./internal/db/... -run TestOpenPool` passes; no existing
  db tests are broken.

- [ ] T3. CI: load test binary compiles (task 3) —
  Add a step to the existing CI workflow (`.github/workflows/` or equivalent
  in mctl-gitops) that runs `go build ./test/load/` to prevent the binary
  from drifting out of compilation. This must be added alongside the PR that
  introduces the package (task 3 PR).
  DoD: CI passes on the PR introducing `test/load/`; subsequent PRs that
  break the binary fail CI.

## Rollback

If beta.env values cause issues after promotion to a staging or Beta
environment:

1. **DB pool**: Remove or set DB_MAX_OPEN_CONNS=0 and DB_MAX_IDLE_CONNS=0
   from the deployment env. The server falls back to the hardcoded defaults
   (10/2 for Postgres) because 0 is the sentinel for "use default." No
   restart of any other service is required.

2. **Session cap**: Reduce TELEGRAM_MAX_SESSIONS to the value in the 1 GiB
   row of docs/hpa.md (270) or to the confirmed saturation point minus 20%.
   Existing live sessions are not evicted; the lower cap only prevents new
   sessions from being allocated once the cap is reached.

3. **Rate limit**: Reduce RATE_LIMIT_PER_USER back to 30 (the Pilot default
   hardcoded in internal/config/config.go:74). This takes effect on the next
   server restart; in-flight requests complete normally.

4. **Audit retention**: Increasing AUDIT_RETENTION_DAYS (e.g., back to 90)
   after it was running at 30 is safe; it only extends the retention window
   for future rows. Rows already deleted by the sweeper cannot be recovered.

5. **Code changes (tasks 1 and 2)**: The config and db.Open changes are
   decoupled from the load test binary and beta.env. Reverting the config PR
   (tasks 1+2) requires reverting three files: `internal/config/config.go`,
   `internal/db/db.go`, and `cmd/server/main.go`. The load test package
   (`test/load/`) and documentation files are additive and carry no runtime
   risk; they can remain in the tree after a code rollback.
