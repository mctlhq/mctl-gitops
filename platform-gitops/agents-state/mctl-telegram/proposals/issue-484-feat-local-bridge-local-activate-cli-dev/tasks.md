# Tasks: issue-484-feat-local-bridge-local-activate-cli-dev

- [ ] 1. Generate and persist an Ed25519 device identity in `cmd/local`.
      Extend the existing device identity artifact with `private_key` and
      `public_key` alongside `device_registration_key`. Generate once with
      `ed25519.GenerateKey`, write atomically at `0600`, and reuse on every
      later `activate` run. — DoD: repeated activation uses identical public
      key bytes and registration key; private material never leaves the
      machine.

- [ ] 2. Send `device_pubkey` on activation start (depends on 1).
      Add the base64 Ed25519 public key to `activateStartRequest`. — DoD: a
      real server round trip no longer fails with
      `devicePubkeyRequiredMessage`; request-body tests assert exact wire
      encoding.

- [ ] 3. Complete credential bootstrap inside `activate` (depends on 1-2).
      After browser activation returns `device_id`, perform nonce -> sign
      `device_id + "." + nonce` -> `/credential`, persist
      `{device_id, worker_token, expires_at, jti}`, and replace the stale
      operator-token message with `daemon` as the next step. Preserve the
      identity across partial failures. Treat already-claimed lineage as an
      already-activated condition and recover through the device refresh path.
      — DoD: `activate` ends with a usable device credential and zero operator
      instructions.

- [ ] 4. Implement device-signed daemon refresh (depends on 3).
      Add nonce -> sign -> `/refresh` -> `/api/bridge/token` flow and make
      device identity/credential presence select that path. Keep the existing
      bearer-only path unchanged for configs that contain only legacy token
      artifacts. — DoD: a device-onboarded config connects to `/bridge`
      without a manually minted MCP token; a legacy-only config behaves
      exactly as before.

- [ ] 5. Prove refresh works after the previous access JWT has expired
      (depends on 4). The device private key/PoP must be sufficient to obtain
      a nonce and refresh; a still-valid old access bearer must not be a
      prerequisite. If the current server boundary accidentally requires the
      old JWT, change that boundary narrowly while preserving generic
      unknown/revoked/bad-signature failures and the nonce-capacity DoS fix.
      — DoD: T13 passes with the old JWT expired/invalid and no operator action.

- [ ] 6. Fix the Hub `daemonConn` lifecycle race.
      Replace close/send channel races with a single safe teardown mechanism
      (`done`/context cancellation or equivalent). Apply it consistently to
      `Register` replacement, `Unregister`, `UnregisterSend`, and
      `EvictDevice`; ensure `Hub.Call` can observe retirement without sending
      to a closed queue or hanging forever. Do not use panic `recover` as the
      primary fix. Preserve exact `(userID, deviceID)` eviction semantics. —
      DoD: no `send on closed channel` path remains and deterministic
      concurrency tests plus `go test -race` pass.

- [ ] 7. Keep live consent derivation correct (depends on 4-5).
      Verify the device refresh path always derives scopes from current
      `send_enabled` state and never copies stale scopes from a prior JWT. —
      DoD: owner `set_send_consent` changes the next refreshed credential's
      scopes without reactivation; first issuance remains read-only.

- [ ] 8. Rewrite `docs/local-bridge.md` (depends on 1-7).
      Make **Client / owner actions** (`init`, `login`, `activate`, `daemon`,
      `set_send_consent`) the primary path. Move `connect --token`, manual
      worker-token minting, `set_account_mode`, `set_account_send`, and
      provisioning into **Operator: support and recovery only**. Document
      device binding, expired-access PoP refresh, live-state scopes,
      revocation/eviction, legacy compatibility, and the guarantee that the
      self-service flow stores no hosted MTProto session. — DoD: no normal
      onboarding instruction requires an operator.

- [ ] 9. Update the user-facing landing/connect/onboarding UX (depends on 1-8).
      Present `init -> login -> activate -> daemon` as the default Local Bridge
      path. Legacy/admin paths must be visibly support/migration/recovery only.
      Remove wording that implies manual provisioning, token minting, or
      `set_account_send` is required for a fresh user. — DoD: a new user can
      discover the zero-admin flow without opening the operator docs.

- [ ] 10. Update `internal/bridge/DESIGN.md` (depends on 1-9).
      Close the self-service gap; document Ed25519 bootstrap trust, first
      issuance vs refresh, stable JTI lineage, live-state scope derivation,
      bridge-token derivation, expired-access recovery, safe Hub connection
      lifecycle, revocation SLA, and legacy bearer compatibility. — DoD:
      `DESIGN.md`, runtime behavior, and `docs/local-bridge.md` describe the
      same architecture.

## Tests

- [ ] T7. Zero-admin E2E: fresh install -> `init` -> local Telegram `login`
      -> `activate` -> read call -> explicit owner `set_send_consent` ->
      forced refresh -> send call -> daemon reconnect/restart. Assert
      `telegram_accounts.session_encrypted IS NULL` throughout and assert no
      operator/admin onboarding action is invoked.

- [ ] T8. Regression: existing hosted fresh-user flow and hosted->local
      migration continue to pass unmodified.

- [ ] T9. Regression: a manually minted legacy worker token still
      authenticates `connect`, refreshes the bridge token via the legacy
      bearer-only path, and reconnects.

- [ ] T10. Activation idempotency: two completed `activate` runs against the
      same config reuse the same registration key, Ed25519 identity, and
      device; already-claimed lineage is handled through refresh semantics.

- [ ] T11. Product/docs regression: every documented command/flag/route
      matches the actual CLI, and landing/connect/onboarding presents the
      self-service path first with operator actions only under
      support/migration/recovery.

- [ ] T12. Hub lifecycle race regression: exercise `Hub.Call` concurrently
      with `EvictDevice`, `Register` replacement, `Unregister`, and
      `UnregisterSend`. No panic, no send-to-closed, no permanently stuck
      pending call, and no request delivery to a retired connection. Run the
      affected bridge tests under `go test -race`.

- [ ] T13. Expired-access PoP refresh: issue a device credential, move beyond
      its access JWT expiry, then successfully perform nonce -> signed
      `/refresh` -> `/api/bridge/token` -> websocket reconnect with no valid
      old bearer and no operator/admin action.

- [ ] T14. Live consent scopes: grant and revoke owner send consent around
      forced refreshes and assert newly issued credentials reflect current DB
      state while old credentials are not mutated.

- [ ] T15. Private key permissions: assert the device identity/private-key
      artifact is `0600` on a POSIX-permission-respecting filesystem and is
      reused after restart.

## Rollback

- All protocol-facing behavior remains additive and backward-compatible.
- Legacy bearer recovery stays available if the new device path is reverted.
- No database rollback is expected; any narrow server adjustment required for
  expired-access PoP refresh must remain compatible with #483 credentials.
- The Hub lifecycle fix is independently safe to keep because it removes a
  general process-crash race from existing close paths.
- Product/docs changes roll back with code so the advertised happy path never
  points at unavailable behavior.

## Completion gate

Do not mark #484 complete and do not close #479 until T7, T11, T12, and T13 are green. In particular, the Hub lifecycle race and expired-access refresh are blockers, not follow-up cleanup.
