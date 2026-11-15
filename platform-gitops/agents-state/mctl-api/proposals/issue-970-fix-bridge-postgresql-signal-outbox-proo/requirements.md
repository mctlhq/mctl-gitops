# Fix bridge: real-PostgreSQL proof of the signal outbox and expired-command classification (follow-up to #968)

## Context
PR #968 (merge `eeea203f`) added the provider bridge store (`internal/bridge`). The merge went in while the agy reviewer
was still reporting `FAIL:P1,P2` on that head, so its two findings are unresolved. P1 says the
`Store.LeaseSignals` statement in `internal/bridge/dispatcher.go` (an `UPDATE ... WHERE command_id IN (SELECT ...
ORDER BY ... LIMIT $1 FOR UPDATE SKIP LOCKED)`) is rejected by PostgreSQL with SQLSTATE 0A000. The Claude review and
the PostgreSQL documentation disagree with that. P2 says `Store.leaseLive` in `internal/bridge/store.go` returns
`ErrLeaseStale` for a command whose `expires_at` has passed while its stored status is still `leased`, before the
lazy sweep in `claimTx` has moved it to `expired`. In that case it should return `ErrCommandExpired`. Today
`internal/bridge/store_pg_test.go` never runs `LeaseSignals`, `MarkSignalSent`, `MarkSignalUnknown` or `RetrySignal`
against a real database.

This proposal is a narrow corrective change. Real-PostgreSQL integration tests will settle P1 by running it. The SQL
is rewritten only if those tests show it fails or is unsafe. A minimal change to `leaseLive` fixes P2. Nothing is
activated or deployed.

## User stories
- AS a platform owner I WANT the disputed `LeaseSignals` SQL run on real PostgreSQL, including under concurrency,
  SO THAT the P1 dispute is settled by evidence, not opinion.
- AS a provider worker I WANT a result or permit call on a command past its TTL to fail with `command_expired`
  SO THAT I stop retrying instead of treating it as a lost lease and reclaiming.
- AS a reviewer I WANT outbox state transitions covered by `TEST_DATABASE_URL`-gated tests that CI does not skip
  SO THAT a regression in queue SQL or a queue race fails the build.

## Acceptance criteria (EARS)
- WHEN `TEST_DATABASE_URL` is set THE SYSTEM SHALL run the new outbox tests against PostgreSQL, using the exact SQL
  of `Store.LeaseSignals`, `Store.MarkSignalSent`, `Store.MarkSignalUnknown` and `Store.RetrySignal`.
- WHEN `TEST_DATABASE_URL` is unset THE SYSTEM SHALL skip those tests with a message that names the missing variable.
- WHEN `LeaseSignals(limit, visibility)` runs and pending rows with `next_attempt_at <= now()` exist THE SYSTEM SHALL
  select at most `limit` eligible rows using oldest `next_attempt_at` as *selection priority* (ties may be arbitrary). The returned `[]Signal` is unordered because SQL `UPDATE ... RETURNING` does not guarantee row order. Move every selected row's `next_attempt_at` to about
  `now() + visibility`.
- WHILE a row has `next_attempt_at > now()` or a status other than `pending` THE SYSTEM SHALL NOT return it from
  `LeaseSignals`.
- WHEN two transactions run `LeaseSignals` concurrently over the same due rows THE SYSTEM SHALL return disjoint sets
  of `command_id`s, and neither call shall fail or block until the other commits.
- WHEN a leased row's visibility timeout elapses without a terminal mark THE SYSTEM SHALL make it leasable again.
- WHEN `RetrySignal(id, code, after)` runs on a pending row THE SYSTEM SHALL increment `attempts`, set
  `last_error_code=code` and set `next_attempt_at` to about `now() + after`.
- WHEN `MarkSignalSent` runs on a pending row THE SYSTEM SHALL set `status='sent'` and `sent_at`, increment
  `attempts` and clear `last_error_code`.
- WHEN `MarkSignalUnknown(id, code)` runs on a pending row THE SYSTEM SHALL set `status='unknown'`, increment
  `attempts` and set `last_error_code=code`.
- IF a row is already `sent` or `unknown` THEN THE SYSTEM SHALL leave every column unchanged when a late
  `MarkSignalSent`, `MarkSignalUnknown` or `RetrySignal` arrives, and `LeaseSignals` shall never return that row.
- IF the original `LeaseSignals` SQL errors on PostgreSQL (for example SQLSTATE 0A000) or fails the disjointness test
  THEN THE SYSTEM SHALL replace it with a row-locked `WITH due AS (SELECT ... ORDER BY next_attempt_at LIMIT $1
  FOR UPDATE SKIP LOCKED) UPDATE ... FROM due` that keeps the status guard, ordering, limit and visibility semantics.
  The same tests must pass against the new SQL.
- IF the original SQL passes every test THEN THE SYSTEM SHALL keep it unchanged, and the PR shall record the
  PostgreSQL server version and the passing CI test names as evidence against the alleged P1.
- WHEN `leaseLive` runs on a row with status `leased`, the presented token matches and `expires_at <= now()`
  THE SYSTEM SHALL return `ErrCommandExpired`, whatever the lease deadline is.
- WHEN `leaseLive` runs on a row with status `leased`, `expires_at > now()`, and either the token does not match or
  `lease_expires_at` is nil or has passed THE SYSTEM SHALL return `ErrLeaseStale`.
- IF the presented lease token does not match the stored token THEN THE SYSTEM SHALL return `ErrLeaseStale` from
  `SubmitResult` and `IssueWritePermit`, even when the command has expired. A non-holder learns nothing about the
  command's TTL state.
- WHEN the HTTP layer receives `ErrCommandExpired` or `ErrLeaseStale` THE SYSTEM SHALL answer 409 with code
  `command_expired` or `lease_stale` respectively (unchanged mapping in `internal/api/handlers_bridge.go::bridgeStatus`).
- WHILE these changes are in place THE SYSTEM SHALL keep `MCTL_BRIDGE_ENABLED` defaulting to false and the default
  `WriteFence` refusing (`refusingFence`).

## Out of scope
- The five non-blocking P3 cleanups from the #968 review (tracked separately).
- Any change to #962/#968 behaviour beyond `leaseLive` and, only if the tests require it, the `LeaseSignals` SQL.
- Provider credentials, Glovo traffic, OAuth activation, Temporal configuration, enabling a namespace, production
  deployment (held by mctl-gitops#2457) and rollback of #968.
- Reviewer-gate governance fixes (mctl-agents#240, mctl-gitops#1040). This proposal only states that a merge
  requires fresh Claude APPROVED plus agy PASS on the same head.
- Changing the `validate.yml` workflow, except to make sure the bridge PG tests are not skipped (see Open questions).

## Open questions
- Precedence when the token is wrong and the command has also expired. This proposal keeps the token check first,
  so the answer is `lease_stale`; only the token holder learns `command_expired`. That matches how `submitTx` and
  `permitTx` already call `tokenEqual` before `leaseLive`. The owner should confirm.
- "TEST_DATABASE_URL confirmed in logs, not skipped": `validate.yml` already sets `TEST_DATABASE_URL` and runs
  `go test -p 1 ./...` without `-v`, so skipped tests are not visible. Required additional `shell: bash` step:
  `set -euo pipefail`, then `go test -p 1 -count=1 -v -run 'TestPG' ./internal/bridge/ | tee bridge-pg.log`.
  Reject any `--- SKIP` and assert explicit `--- PASS` lines for the named required `TestPGOutbox*`
  tests (at least lease, concurrency, terminal transitions, and real submit result). A zero-test pass and a failed
  `go test` behind a successful `tee` must both fail CI. Log PostgreSQL server version. No broad workflow changes.
- Isolation: `bridge_signal_outbox` is tenant-agnostic and `LeaseSignals` scans the entire table. The tests
  MUST run in an isolated throwaway PostgreSQL schema/database with an effective `search_path`; verify this by
  reading `current_schema()` and confirming the expected test schema. If isolation cannot be established, fail the
  test setup. Unique-ID filtering against a shared outbox is **not** an acceptable fallback because it cannot prove
  global limit/disjointness and may lease other tests' rows.
- The P1 outcome could not be decided in this investigation: the investigation sandbox had no PostgreSQL server.
  The implementer's CI run decides it.

## AMEND 2026-11-08 — independent review corrections

- CI evidence gate is fail-closed: use Bash `set -euo pipefail`, fail on test error, any skipped bridge PG test, or missing named PASS evidence. Never accept a vacuous zero-test success.
- `ORDER BY` guarantees selection priority inside the lease subquery, **not the ordering of rows returned from `UPDATE ... RETURNING`**. Tests assert the eligible selected set and fair priority, not array order.
- Abort PG test setup when disposable schema isolation is not proven. No fallback to shared global outbox.
- These documentation changes grant **no implementation approval** and do not lift the #240/#1040 review gate or #2457 release hold.
