# Tasks: issue-481-feat-local-bridge-device-registry-and-an

- [ ] 1. Add `local_bridge_devices` table (plus its three indexes) to both
      `sqliteSchema()` and `pgSchema()` in `internal/db/db.go`, following the
      column set in design.md (`id`, `user_id`, `device_id`, `device_label`,
      `idempotency_key`, `registered_at`, `last_seen_at`, `revoked_at`,
      `revoked_reason`) — DoD: `db.Migrate` run against a fresh SQLite DSN
      and a fresh Postgres DSN both create the table and all three indexes
      with no error; running `Migrate` a second time against the same DB is
      a no-op (idempotent `CREATE TABLE/INDEX IF NOT EXISTS`).
- [ ] 2. Add `Device` struct and `ErrDeviceNotFound` sentinel plus
      `RegisterDevice`, `GetDevice`, `RevokeDevice`, `TouchDeviceLastSeen`
      methods on `*Store` in new file `internal/db/local_bridge_devices.go`
      (depends on 1) — DoD: methods compile, follow the existing
      `(s *Store) Method(ctx, ...) (..., error)` / `fmt.Errorf("context:
      %w", err)` conventions from `worker_token_revocations.go`, and use
      the dialect-specific `ON CONFLICT ... WHERE idempotency_key IS NOT
      NULL DO NOTHING` (Postgres, via `s.isPostgres(ctx)`) /
      `INSERT OR IGNORE` (SQLite) pair for `RegisterDevice`'s idempotent
      insert.
- [ ] 3. Generate the server-side `device_id` value in `RegisterDevice`
      using `crypto/rand` (no new dependency — no UUID library is imported
      by this repo today) (depends on 2) — DoD: generated ids are
      collision-resistant (128 bits of randomness, hex or base32 encoded)
      and stable once returned (the same id is what a retried call with the
      same `idempotency_key` gets back).
- [ ] 4. Add optional `DeviceID string \`json:"device_id,omitempty"\`` field
      to `localjwt.Claims` in `internal/auth/localjwt/issuer.go`, with a doc
      comment matching the style of the `Jti`/`OriginalIssuedAt` comments
      (who sets it, why old tokens omit it, that `Mint`/`Verify` need no
      other changes) — DoD: `go build ./...` passes with no other file
      touched; `Mint`/`Verify` function bodies are unmodified.
- [ ] 5. Unit tests for the `Store` methods in
      `internal/db/local_bridge_devices_test.go` (depends on 2, 3) — DoD:
      see `## Tests` below; tests run against both the SQLite and Postgres
      test harnesses already used by `worker_token_revocations_test.go` /
      `store_migration_test.go` (check for a `testDB(t)`-style helper and
      reuse it rather than hand-rolling a new one).
- [ ] 6. Unit tests for `localjwt.Claims.DeviceID` in
      `internal/auth/localjwt/issuer_test.go` (depends on 4) — DoD: see
      `## Tests` below.

## Tests

- [ ] T1. `TestRegisterDevice_Insert`: `RegisterDevice` with a fresh
      `idempotency_key` inserts exactly one row and returns a non-empty
      `device_id`.
- [ ] T2. `TestRegisterDevice_IdempotentRetry`: calling `RegisterDevice`
      twice with the same `(userID, idempotencyKey)` returns the same
      `device_id` both times and leaves exactly one row in the table
      (covers the issue's explicit "idempotent-retry" DoD item, and
      exercises the Postgres `ON CONFLICT` partial-index path, not just
      SQLite's `INSERT OR IGNORE`).
- [ ] T3. `TestGetDevice_Lookup`: `GetDevice` on a registered id returns a
      `Device` with the expected `user_id`/`device_label`/`registered_at`
      and `revoked_at == nil`.
- [ ] T4. `TestGetDevice_NotFound`: `GetDevice` on an unknown id returns
      `ErrDeviceNotFound` (via `errors.Is`).
- [ ] T5. `TestRevokeDevice`: `RevokeDevice` sets `revoked_at`/
      `revoked_reason`; a subsequent `GetDevice` reflects the revoked state.
- [ ] T6. `TestRevokeDevice_Idempotent`: revoking an already-revoked device
      twice does not error and does not change the original `revoked_at`
      (mirrors `RevokeWorkerToken`'s "re-revoking is a no-op" contract) —
      or, if the design instead updates `revoked_at` on re-revoke, pins
      whichever behavior is actually implemented so it cannot silently
      drift later.
- [ ] T7. `TestTouchDeviceLastSeen`: updates `last_seen_at` on an existing
      device; a call against an unknown `device_id` returns no error
      (0 rows affected is not a failure at this layer, per design.md).
- [ ] T8. `TestMint_Verify_DeviceIDRoundtrip`: `Mint` with `Claims{...,
      DeviceID: "dev_abc"}` followed by `Verify` returns
      `Claims.DeviceID == "dev_abc"`.
- [ ] T9. `TestMint_OmitsEmptyDeviceID`: `Mint` with `DeviceID` unset
      produces a token whose decoded base64 payload does not contain the
      `"device_id"` key at all (not just an empty string) — asserts the
      `omitempty` behavior directly, not just the round-trip.
- [ ] T10. `TestVerify_LegacyTokenWithoutDeviceID` (the regression test the
      issue's Definition of Done explicitly requires): hand-construct (or
      reuse a fixture of) a token payload shaped like one minted before
      this change — no `device_id` key present at all — and assert
      `Verify` succeeds and returns `Claims.DeviceID == ""`, with every
      other claim intact. This must use a raw/fixture payload rather than
      round-tripping through the new `Mint`, so it actually exercises "a
      token that predates the field" rather than "a token that sets the
      field to its zero value."

## Rollback

- All changes are additive with no reads/writers wired in yet, so rollback
  is a plain revert of the PR (or a follow-up commit dropping the new file
  and the `Claims.DeviceID` field) with no data-migration concerns:
  - `local_bridge_devices` will contain zero rows until a follow-up
    sub-issue adds a caller (this issue introduces none), so dropping the
    table loses no user data.
  - No JWT issued elsewhere in the codebase sets `device_id` after this
    issue merges (it is add-only, unused by any caller), so removing the
    claim field cannot break in-flight tokens — the field's absence is
    already the behavior every existing token exercises today.
  - If the table needs to be dropped from a live database for any reason,
    `DROP TABLE IF EXISTS local_bridge_devices` is safe at any point before
    a follow-up sub-issue starts writing to it; coordinate with whichever
    sub-issue is in flight once one lands.
