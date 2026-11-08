# Tasks: issue-971-hardening-bridge-lease-token-redaction-e

- [ ] 1. Add a redacted stored form of `Result` in `internal/bridge/schema.go`:
  a `redacted()` method or an unexported `storedResult` type that omits
  `lease_token` and keeps the field order. Leave `Result.Digest()` unchanged.
  — DoD: unit test shows the redacted JSON has every field except
  `lease_token`, and `Digest()` output is unchanged for the `testdata/result.valid.json`
  fixture.
- [ ] 2. In `internal/bridge/store.go::submitTx`, store the redacted bytes
  instead of `json.Marshal(res)`. (depends on 1) — DoD: the stored
  `bridge_commands.result` has no `lease_token` key. The replay and
  `result_conflict` paths are unchanged.
- [ ] 3. Change `ReadOutcome` to select `result - 'lease_token'` immediately. Add bounded
  `ScrubLegacyResultBatch(ctx, limit)` under `FOR UPDATE SKIP LOCKED`, short transactions/timeouts,
  idempotent `result - 'lease_token'` updates, progress/remaining/error metrics and a separate
  operator-controlled invocation **not** called from `NewStore` or `bridgeSchema`.
  — DoD: old rows read clean before migration; 100+ legacy rows scrub in restartable bounded batches
  without stalling startup; zero remaining independently verified before activation.
- [ ] 4. Extract `expireTx` (scoped or unscoped, `LIMIT`, `FOR UPDATE SKIP LOCKED`,
  `RETURNING old_status`) from `claimTx`. Lazy expiry in `claimTx` uses the
  provider/tenant scope. — DoD: transition `from_status` is the locked prior
  status, and lazy-expiry behaviour is otherwise unchanged.
- [ ] 5. In `claimTx`, select `c.status` with `command_id` under
  `FOR UPDATE OF c SKIP LOCKED` and pass it as `from_status` to the lease
  transition. (depends on 4) — DoD: a reclaim records `leased -> leased` with
  the new epoch, and a first lease records `pending -> leased`.
- [ ] 6. Add `Store.ExpireDue(ctx, limit)` and `internal/bridge/expiry.go::Expirer`
  (`RunOnce`, `Run`, 30s interval, 100 batch, finite max batches/tick, actor
  `system:expiry-sweep`; logs only counts/errors). Emit processed, oldest-overdue age,
  backlog, error and last-success metrics, with defined alert thresholds and continuation across ticks.
  Add additive partial index `bridge_commands_expiry`. (depends on 4) — DoD: test >batch backlog,
  lock skips, concurrent replicas, progress and PG race tests.
- [ ] 7. Wire the `Expirer` in `cmd/api/main.go`: it starts only when
  `bridgeStore != nil`, independent of `TEMPORAL_ADDRESS`, with an optional
  `MCTL_BRIDGE_EXPIRY_SWEEP_INTERVAL` override. (depends on 6) — DoD: with
  `MCTL_BRIDGE_ENABLED` unset, nothing new starts.
- [ ] 8. Update `docs/bridge.md`: describe the stored-result redaction, note
  that the digest is unchanged, describe the expiry sweep and the transition
  semantics. Add the four-item FIXED/DEFERRED disposition list to the PR
  description. — DoD: the docs match the behaviour. The lease-token column item
  is DEFERRED with owner, dependency (mctl-gitops#2457) and criterion.
- [ ] 9. Run `go fmt`, `go vet` and `golangci-lint`, then `go test ./...` with
  `TEST_DATABASE_URL`. — DoD: all green. No change to `internal/bridge/schema/*`
  or `PROVENANCE` (`TestVendoredSchemasMatchProvenance` passes).

## Tests

All T-tests marked PG go in `internal/bridge/store_pg_test.go` and skip
without `TEST_DATABASE_URL`, like the existing tests.

- [ ] T1. (PG) Submit a result, then read `bridge_commands.result` directly
  and through `ReadOutcome`. Neither contains `lease_token` or the `lt_` token
  string. `result_digest` equals `ParseResult(body).Digest()`. This does NOT sanitize the plaintext
  `bridge_commands.lease_token` column; it has an independent activation decision gate.
- [ ] T2. (PG) Replay after redaction: the same body returns `replayed: true`,
  a changed `completed_at` returns `result_conflict`, and there is exactly one
  outbox row.
- [ ] T3. (PG) Historical row: seed token-bearing result, open a new `NewStore` and
  prove it does not run an unbounded scrub; `ReadOutcome` is redacted immediately.
  Run bounded `ScrubLegacyResultBatch` repeatedly, asserting batch limits, restartable progress, safe
  concurrent writes and zero remaining after completion.
- [ ] T4. (PG) No poller: enqueue for provider `p-idle`, set `expires_at` to
  the past, call `ExpireDue` (no `Claim` at all). Status is `expired`, there is
  one outbox row with digest `expired`, and the transition is
  `pending -> expired` with actor `system:expiry-sweep`.
- [ ] T5. (PG) Expire a leased row that holds a permit (via `allowFence`):
  `effect_state` becomes `unknown`. A row already `unknown` stays `unknown`.
  The transition is `leased -> expired`.
- [ ] T6. (PG) Active race: hold `FOR UPDATE` on a row in an open transaction.
  `ExpireDue` skips it and returns 0 for that row. After the holding
  transaction completes the command, the sweep leaves it `completed`.
  Conversely, after the sweep expires a row, `SubmitResult` is refused and the
  row stays `expired` (the error code is asserted per #970). Each case has one
  outbox row and one terminal transition.
- [ ] T7. (PG) Reclaim audit: claim, force `lease_expires_at` into the past,
  claim again. The transitions in `id` order are `'' -> pending`,
  `pending -> leased` (epoch 1), `leased -> leased` (epoch 2). Lazy expiry
  in `Claim` records the real prior status, not `open`.
- [ ] T8. (PG) Tenant isolation: provider-scoped lazy expiry in `Claim` never
  touches another tenant's due command. The unscoped sweep expires it, with its
  own transition row only.
- [ ] T9. Unit/PG tests: `Expirer.RunOnce` honors batch and loop caps, continues >batch backlog
  over ticks, reports metrics and alerts on persistent overdue age/error, and progresses around locked rows
  with concurrent replica workers. Captured slog JSON across `Expirer`, `Dispatcher` and failure paths
  contains no `lt_` substring.
- [ ] T10. Unit test: the redacted stored form and `Digest()` stability
  against fixtures (task 1).

## Rollback

The bridge is dark by default and not enabled in the deployed configuration,
so the primary rollback is to revert the PR. The only data effect from separately authorized maintenance is a bounded historical scrub that removes
secrets which must never be restored. The scrub does not run at startup; any expired/transition rows
from the sweep are valid terminal records. Both are valid states under the old
code. The additive partial index can stay or be dropped with
`DROP INDEX IF EXISTS bridge_commands_expiry`. If the bridge were ever enabled
and the sweep misbehaved, unsetting `MCTL_BRIDGE_ENABLED` stops it, as
documented in `docs/bridge.md`.

## AMEND 2026-11-08 owner/security gates

- [ ] Verify legacy scrub does not stall `NewStore` or API hot paths, works in bounded restartable batches, and reaches verified zero JSONB token copies before activation.
- [ ] Prove >batch backlog, locked rows and multi-replica sweeps make eventual observable progress, not an unsupported one-interval SLA.
- [ ] Record a separate approved security decision on plaintext live `lease_token` and backup retention before any provider credential issuance.
- [ ] Re-review the new proposal digest; fresh independent Claude and agy review for implementation PR; no autonomous merge with #240/#1040 reviewer-gate defects unresolved.
