# Design: issue-970-fix-bridge-postgresql-signal-outbox-proo

## Current state
- `internal/bridge/dispatcher.go`
  - `Store.LeaseSignals(ctx, limit, visibility)` runs one autocommit statement on `s.pool`:
    `UPDATE bridge_signal_outbox SET next_attempt_at = now() + ($2 * interval '1 second') WHERE command_id IN
    (SELECT command_id FROM bridge_signal_outbox WHERE status='pending' AND next_attempt_at <= now() ORDER BY
    next_attempt_at LIMIT $1 FOR UPDATE SKIP LOCKED) RETURNING command_id, workflow_id, run_id, result_digest, attempts`.
    The "lease" is a visibility timeout (`next_attempt_at` pushed forward). No row lock is held during delivery.
  - `MarkSignalSent`, `MarkSignalUnknown` and `RetrySignal` are single `UPDATE`s guarded by `status='pending'`. They
    discard `RowsAffected`, so a late call on a terminal row is a silent no-op.
  - `Dispatcher.RunOnce` leases a batch with a fixed 2-minute visibility. Only mock-tested, in `dispatcher_test.go`.
- `internal/bridge/store.go`
  - Schema `bridgeSchema`. `bridge_signal_outbox(command_id PK, workflow_id, run_id, result_digest, status
    CHECK IN ('pending','sent','unknown'), attempts, last_error_code, next_attempt_at, created_at, sent_at)` has a
    partial index `bridge_signal_outbox_due ON (next_attempt_at) WHERE status='pending'`. The table has no
    tenant/provider column.
  - Outbox rows are written by `submitTx` (on result completion, same transaction) and by `claimTx` (lazy expiry,
    `result_digest='expired'`, `ON CONFLICT DO NOTHING`).
  - `claimTx` sets `lease_expires_at = LEAST(now()+ttl, expires_at)`. Once the command TTL passes, the lease deadline
    has therefore passed as well.
  - `leaseLive(row, token)` checks, in order: status cancelled -> `ErrCommandCancelled`, expired ->
    `ErrCommandExpired`, pending/completed -> `ErrLeaseStale`, token mismatch -> `ErrLeaseStale`, then
    `LeaseExpiresAt == nil || !LeaseExpiresAt.After(now) || !ExpiresAt.After(now)` -> `ErrLeaseStale`. A row still
    stored as `leased` whose `ExpiresAt` has passed (the sweep only runs inside `Claim`) is therefore reported as
    `lease_stale`. This is agy P2.
  - Callers of `leaseLive`: `submitTx` (store.go, after `tokenEqual` and the completed-replay check) and
    `permit.go::permitTx` (after `tokenEqual`). Both reject a wrong token with `ErrLeaseStale` before calling
    `leaseLive`.
  - `Store.now` is an injectable clock (`time.Now().UTC()` by default) and is used only by `leaseLive`.
- `internal/bridge/errors.go`: `ErrCommandExpired` ("command_expired") and `ErrLeaseStale` ("lease_stale") are both
  in `codedErrors`.
- `internal/api/handlers_bridge.go::bridgeStatus` maps both codes to 409 (default branch).
  `write_fence_refused` maps to 403 and `write_fence_unavailable` to 503. `handlers_bridge_test.go` checks the
  mapping for `ErrLeaseStale` but not for `ErrCommandExpired`.
- `internal/bridge/store_pg_test.go`: `pgStore(t)` skips when `TEST_DATABASE_URL` is unset. Its helpers are
  `enqueue`, `claimOne` and `resultBody`. Tests cover claim/result/replay/tenancy, reclaim fencing, cancel and
  permits. None touches the outbox beyond a row count.
- `internal/pgshared/pool.go::Open` parses the connection string with `pgxpool.ParseConfig` (so extra keys such as
  `search_path` become runtime params) and shares pools per exact connection string.
- `.github/workflows/validate.yml` runs a `postgres:16` service, sets `TEST_DATABASE_URL` and runs
  `go test -p 1 ./...` without `-v`.
- `cmd/api/main.go:1012`: the bridge is wired only when `MCTL_BRIDGE_ENABLED == "true"`.

Deployed state checked:
- `/workdir/mctl-gitops/platform-gitops/services/`: grep for `MCTL_BRIDGE` found no matches. There is no
  `services/<tenant>/mctl-api/values.yaml` in this checkout; the tenants present are admins, karabu, labs and
  namax66. mctl-api's own deployed env therefore could not be observed here. This is recorded as not observed, not
  as "disabled".
- mctl MCP tools: not used. No deployed-state fact is needed for a test-and-classification change that ships
  nothing active.
- Local PostgreSQL: no `psql`, `postgres` or `docker` binary, and `TEST_DATABASE_URL` is unset in the investigation
  sandbox. The P1 SQL could not be executed during the investigation.

## Proposed solution
1. **Evidence first, SQL unchanged by default.** Add `internal/bridge/outbox_pg_test.go`, gated by `pgStore` /
   `TEST_DATABASE_URL`.
   - Isolation: a helper `pgIsolatedStore(t)` opens a plain `pgx.Connect`, runs `CREATE SCHEMA bridge_t_<rand>`, and
     builds a `Store` via `NewStore(ctx, conn+"&search_path=bridge_t_<rand>")`. `NewStore` applies `bridgeSchema`
     inside that schema. `t.Cleanup` closes the store and runs `DROP SCHEMA ... CASCADE`. Because the table is
     tenant-agnostic, this is the only way to assert exact `LeaseSignals` results without picking up rows left by
     other bridge tests. If the runtime search-path parameter fails or `SELECT current_schema()` does not match the created schema,
     **fail test setup**, not a shared-table fallback. No unscoped DELETE in the shared test database.
   - Fixtures: outbox rows are produced by the real path (`enqueue` -> `claimOne` -> `SubmitResult`), so at least
     one test proves the production write and lease work together. Scenario rows (due/not-due/terminal) are inserted
     directly with explicit `next_attempt_at`.
   - Tests (names prefixed `TestPGOutbox*` so they match `-run TestPG`):
     - Lease basics: lease due rows, respect `limit` and *oldest-first selection priority* (not RETURNING order), exclude future and terminal
       rows, check `next_attempt_at` was moved to about now + visibility, and check a second immediate lease returns
       nothing.
     - Visibility expiry: with a 1-second visibility, or after backdating `next_attempt_at` in SQL, the row is
       leasable again.
     - Concurrency, deterministic: tx A runs `SELECT ... FOR UPDATE` on k due rows and stays open. `LeaseSignals`
       under a 5-second context deadline must return without blocking and exclude those k rows. A SQL error,
       including any SQLSTATE 0A000, fails the test and the error is logged verbatim.
     - Concurrency, racing: N goroutines (N >= 4) start `LeaseSignals` together over M due rows (barrier start,
       repeated about 20 times). The returned id sets are pairwise disjoint and their union is at most M.
     - `RetrySignal`: attempts+1, `last_error_code`, new `next_attempt_at`; the row is not due until then, then is
       leasable.
     - `MarkSignalSent` / `MarkSignalUnknown`: columns as specified. Then late `MarkSignalSent`, `MarkSignalUnknown`
       and `RetrySignal` calls on the terminal row leave a full-row snapshot unchanged, and `LeaseSignals` never
       returns it.
     - Error branch: a cancelled context causes `LeaseSignals` to return an error wrapped with
       `bridge: lease signals:`. Mark/retry on an unknown id is a no-op with nil error (documents current contract).
     - Dispatcher on real PG: `Dispatcher.RunOnce` with a fake `BridgeSignaler` returning nil,
       `ErrSignalTargetNotFound`, and a transient error, over three real rows -> sent / unknown / pending with
       attempts=1.
   - Each test logs `SELECT version()` once, so CI logs show the tests ran on PostgreSQL.
2. **Conditional SQL rewrite.** Only if step 1 shows an error or overlapping sets on PostgreSQL 16, replace the
   statement with:
   ```sql
   WITH due AS (SELECT command_id FROM bridge_signal_outbox
                WHERE status='pending' AND next_attempt_at <= now()
                ORDER BY next_attempt_at LIMIT $1 FOR UPDATE SKIP LOCKED)
   UPDATE bridge_signal_outbox o SET next_attempt_at = now() + ($2 * interval '1 second')
   FROM due WHERE o.command_id = due.command_id AND o.status='pending'
   RETURNING o.command_id, o.workflow_id, o.run_id, o.result_digest, o.attempts
   ```
   The PR must show the failing run on the old SQL and the passing run on the new SQL. If step 1 passes, keep the
   SQL byte-identical. The PR description then records the PG version, the test names and the CI job link as
   evidence against agy P1.
3. **`leaseLive` fix (P2).** In `internal/bridge/store.go`, check command TTL before the lease deadline:
   ```go
   if !tokenEqual(row.LeaseToken, token) { return ErrLeaseStale }
   now := s.now()
   if !row.ExpiresAt.After(now) { return ErrCommandExpired }
   if row.LeaseExpiresAt == nil || !row.LeaseExpiresAt.After(now) { return ErrLeaseStale }
   ```
   The status switch above it is unchanged. Precedence, to be documented in the function comment: cancelled >
   stored-expired > not-leased (stale) > wrong token (stale) > command TTL elapsed (expired) > lease deadline elapsed
   (stale). The token is checked before the TTL so a non-holder cannot probe a command's TTL, consistent with the
   existing `tokenEqual` checks in `submitTx` and `permitTx`. No database write is added. The lazy sweep in `Claim`
   still owns the `expired` transition and the outbox row.
4. **Regression tests for P2.**
   - Unit tests, no DB, in `store_lease_test.go`: table-driven over `leaseLive` with a fixed `s.now` and synthetic
     `cmdRow`s: valid; wrong token; nil lease; lease elapsed with command live (stale); command elapsed with lease
     live (expired); both elapsed (expired); wrong token with command elapsed (stale); status
     expired/cancelled/pending/completed.
   - Real PG, in `store_pg_test.go`: claim a command, backdate `expires_at` and `lease_expires_at` in SQL, then
     `SubmitResult` and `IssueWritePermit` (with `allowFence`) return `command_expired`, and the row and
     `bridge_write_permits` are unchanged. A lease-only backdate still gives `lease_stale`; a forged token on an
     expired command gives `lease_stale`.
   - HTTP: add `bridge.ErrCommandExpired: 409` to the mapping table in `handlers_bridge_test.go`.
5. **Fail-closed CI evidence.** In `validate.yml`, add a dedicated `shell: bash` step with the same
   `TEST_DATABASE_URL` as the main Go test step. Run:
   ```bash
   set -euo pipefail
   go test -p 1 -count=1 -v -run 'TestPG' ./internal/bridge/ | tee bridge-pg.log
   if grep -q -- '--- SKIP' bridge-pg.log; then echo 'PG bridge test skipped' >&2; exit 1; fi
   for t in TestPGOutboxLeaseDueOrderLimit TestPGOutboxConcurrentLeasersDisjoint TestPGOutboxTerminalStatesImmutable TestPGOutboxFromSubmitResult; do
     if ! grep -q -- "--- PASS: ${t} (" bridge-pg.log; then echo "missing required PG PASS: ${t}" >&2; exit 1; fi
   done
   ```
   Pipefail retains the Go test exit code; specific PASS evidence defeats vacuous zero-test success. This does
   **not** turn agy's green Actions job into an acceptable semantic verdict — reviewer-gate enforcement is #240/#1040.

Defaults are untouched: `MCTL_BRIDGE_ENABLED` and `refusingFence` are not modified.

## Alternatives
- **Rewrite `LeaseSignals` to a CTE unconditionally.** Dropped: the issue explicitly forbids rewriting blindly.
  PostgreSQL documents that locking clauses are allowed in sub-SELECTs. Changing working SQL without evidence would
  hide whether the reviewer was right.
- **Classify expiry by writing `status='expired'` inside `submitTx` / `permitTx`.** Dropped: it duplicates the
  `claimTx` sweep (transition plus outbox insert) inside a refused, rolled-back transaction. Errors are documented
  as leaving rows untouched, so the write would be discarded anyway. Classification alone fixes the wire code.
- **Return `command_expired` before the token check.** Dropped as default: it lets a non-holder learn TTL state, and
  it would change the precedence the callers already rely on. It is listed as an open question for the owner.
- **Share the default schema with cleanup by id.** Rejected even as fallback: `LeaseSignals` is global, and this
  would silently weaken limit/disjointness assertions and interfere with unrelated test rows.

## Platform impact
- Migrations: none. The schema is unchanged. Test schemas are created and dropped only in the test database.
- Backward compatibility: one observable change. Result and permit calls on a command past TTL but not yet swept now
  get `409 command_expired` instead of `409 lease_stale`. Same HTTP status; the code is more accurate. The bridge is
  disabled by default, and no provider is live (activation is held by #954 and mctl-gitops#2457).
- Resources: CI grows by a few seconds (one extra `-run TestPG` pass of a single package).
- Risks and mitigations:
  - Concurrency tests are timing-sensitive. Use the deterministic lock-holder test as the primary proof and a
    repeated barrier race as a secondary one. Add context deadlines so a hang fails rather than blocks.
  - Clock skew between `s.now()` (Go) and `now()` (DB) in the PG P2 tests. Backdate by hours, not seconds.
  - The `search_path` runtime param could be unsupported by a pooler. CI talks to PostgreSQL directly; the fallback
    is documented above.
- Merge gate: green `go test -p 1 ./...` with PG tests visibly run, lint, CodeQL, Trivy and govulncheck, plus fresh
  Claude APPROVED and agy PASS on the same head SHA, or an explicit manual hold. No autonomous merge while agy
  reports P1/P2.

## AMEND 2026-11-08 — independent evidence and isolation gates

Never equate PostgreSQL `RETURNING` iteration order to the selector's `ORDER BY`. Verify both the selected set and the oldest-due priority via controlled fixtures; the Go method does not currently promise stable return ordering. Test-schema `search_path` must be verified or setup fails. A green test pipeline alone is insufficient: specific PostgreSQL test PASS lines and no SKIP must be visible; reviewer verdicts require separate current-SHA governance before merge.
