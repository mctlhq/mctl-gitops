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
- [ ] 3. Change `ReadOutcome` to select `result - 'lease_token'`. Append the
  idempotent historical scrub
  `UPDATE bridge_commands SET result = result - 'lease_token' WHERE result ? 'lease_token';`
  to `bridgeSchema`. — DoD: a row seeded with a token-bearing result reads
  back without it, and the stored row is scrubbed after `NewStore`.
- [ ] 4. Extract `expireTx` (scoped or unscoped, `LIMIT`, `FOR UPDATE SKIP LOCKED`,
  `RETURNING old_status`) from `claimTx`. Lazy expiry in `claimTx` uses the
  provider/tenant scope. — DoD: transition `from_status` is the locked prior
  status, and lazy-expiry behaviour is otherwise unchanged.
- [ ] 5. In `claimTx`, select `c.status` with `command_id` under
  `FOR UPDATE OF c SKIP LOCKED` and pass it as `from_status` to the lease
  transition. (depends on 4) — DoD: a reclaim records `leased -> leased` with
  the new epoch, and a first lease records `pending -> leased`.
- [ ] 6. Add `Store.ExpireDue(ctx, limit)` and `internal/bridge/expiry.go::Expirer`
  (`RunOnce`, `Run`, default 30s interval and 100 batch, actor
  `system:expiry-sweep`; logs counts and errors only). Add the additive
  partial index `bridge_commands_expiry`. (depends on 4) — DoD: unit tests with
  a fake store, plus the PG tests below.
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
  string. `result_digest` equals `ParseResult(body).Digest()`.
- [ ] T2. (PG) Replay after redaction: the same body returns `replayed: true`,
  a changed `completed_at` returns `result_conflict`, and there is exactly one
  outbox row.
- [ ] T3. (PG) Historical row: write a token-bearing `result` with raw SQL,
  run the schema again (a new `NewStore`), and assert the key is gone and
  `ReadOutcome` is clean.
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
- [ ] T9. Unit test: the `Expirer`'s `RunOnce` with a fake store respects the
  batch and the loop cap. A captured slog JSON handler across `Expirer`,
  `Dispatcher` and handler failure paths contains no `lt_` substring.
- [ ] T10. Unit test: the redacted stored form and `Digest()` stability
  against fixtures (task 1).

## Rollback

The bridge is dark by default and not enabled in the deployed configuration,
so the primary rollback is to revert the PR. The only data effect is the
historical scrub, which removes a secret that must not be restored, and the
expired/transition rows the sweep wrote. Both are valid states under the old
code. The additive partial index can stay or be dropped with
`DROP INDEX IF EXISTS bridge_commands_expiry`. If the bridge were ever enabled
and the sweep misbehaved, unsetting `MCTL_BRIDGE_ENABLED` stops it, as
documented in `docs/bridge.md`.
