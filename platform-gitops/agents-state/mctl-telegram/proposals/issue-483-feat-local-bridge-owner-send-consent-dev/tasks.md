# Tasks: issue-483-feat-local-bridge-owner-send-consent-dev

## Mandatory pre-approval security corrections

Read `security-amendments.md` before implementation. The three corrections below are **authoritative** and supersede any conflicting wording elsewhere in this proposal:

- [ ] 0a. Device-bound credentials MUST NOT be accepted by legacy `POST /api/mcp/worker-token/renew`. Use a dedicated device credential audience/marker that legacy renew does not accept, or explicitly reject any presented token with non-empty `Claims.DeviceID` before renewal. Legacy admin-minted Local Bridge tokens without `DeviceID` must keep their current renew behavior. DoD: device credential → legacy renew is rejected; legacy non-device Local Bridge credential → legacy renew remains green.
- [ ] 0b. Use one stable revocable credential lineage/JTI per device. The first successful self-service issuance creates it; every PoP refresh carries the same lineage forward. Do not generate a fresh independently revocable JTI per refresh and do not model revocation as "latest token only". DoD: issue A → refresh B → refresh C → revoke device → A/B/C and their derived bridge tokens all fail revocation checks.
- [ ] 0c. Preserve `DeviceID` through bridge-token derivation. `auth.Identity` gets `DeviceID` from the device credential, `NewBridgeTokenHandler` copies it into the `aud=bridge` JWT, bridge authentication restores it, and `/bridge` registers `(userID, deviceID)`. DoD: device credential → bridge token → websocket → device revoke actively closes the matching socket while another device for the same user is unaffected.

- [ ] 1. Add `local_bridge_devices` columns `device_pubkey` (BLOB/BYTEA,
      nullable), `device_pubkey_algo` (TEXT, default `'ed25519'`), and
      `credential_jti` (TEXT, nullable) via `addColumnIfMissing` in
      `internal/db/db.go`, both SQLite and Postgres schema blocks — DoD:
      migration runs clean on an existing local dev DB and a fresh one;
      `store_migration_test.go`-style coverage confirms idempotent re-run.
- [ ] 2. Extend `RegisterDevice` (`internal/db/local_bridge_devices.go`) to
      accept and persist a `pubkey []byte` (and implicitly `'ed25519'` as
      algo for now), and `GetDevice` to return it — DoD: unit tests cover
      insert-with-pubkey and the existing idempotency-retry path unchanged
      when pubkey is re-submitted identically.
- [ ] 3. Generate and persist a device Ed25519 keypair in `cmd/local`
      (new file, e.g. `devicekey.go`), `0600`-permissioned, separate from
      the existing idempotency `device_registration_key` — DoD: `activate`
      submits the public key at `POST /api/local-bridge/activate/start`;
      `activateStartRequest`/`handleActivateStart` accept and validate a
      `device_pubkey` field (fixed 32-byte length after decode); a restart
      of `activate` reuses the same keypair rather than regenerating it.
- [ ] 4. Thread the submitted `device_pubkey` through
      `localBridgeActivation` and `approveActivation` into `RegisterDevice`
      (depends on 1, 2, 3) — DoD: an approved activation's
      `local_bridge_devices` row has a non-null `device_pubkey`; existing
      activation tests (`T1-T26` per `local_bridge_activate.go`'s own
      references) remain green with an additional pubkey-presence
      assertion.
- [ ] 5. Add `set_send_consent` MCP tool in `internal/mcp/tools.go`, acting
      only on `auth.From(ctx).UserID`, wrapping `s.Store.SetSendEnabled`,
      audited under tool name `"set_send_consent"` (depends on nothing) —
      DoD: grant and revoke both succeed for an authenticated caller with
      no `admin:users` scope and no `telegram_id` argument exists on the
      tool; `set_account_send`'s existing tests are unmodified and still
      pass.
- [ ] 6. Add `workertoken.MintForDevice` in `internal/workertoken/minter.go`:
      shares `allowedLocalBridgeScopes`/`allowedReadOnlyScopes` and the
      `Claims` construction with `Mint`, but uses new
      `defaultDeviceCredentialTTL`/`maxDeviceCredentialTTL` constants
      (hours-scale, e.g. 6h/24h) instead of `defaultWorkerTokenTTL`/
      `maxWorkerTokenTTL`, always sets `Claims.DeviceID`, takes an explicit
      `Scopes []string`, and uses a device-only audience/marker that cannot
      enter legacy `/api/mcp/worker-token/renew` (or is accompanied by an
      explicit legacy-renew rejection for non-empty `DeviceID`). The first
      issuance creates the device's stable `credential_jti`; PoP refreshes
      must pass that same lineage JTI back into minting rather than generate
      a new one — DoD: TTL/device-id/scope tests pass; device credential is
      rejected by legacy renew; refresh preserves the original JTI.
- [ ] 7. Add `internal/oauth/local_bridge_credential.go`: in-memory,
      TTL-bounded, capacity-bounded nonce store
      (`POST /api/local-bridge/devices/{device_id}/nonce`); Ed25519
      signature verification helper; `POST
      /api/local-bridge/devices/{device_id}/credential` (issuance, always
      read-only scopes, ignores `send_enabled`) (depends on 4, 6) — DoD: T3
      (initial credential is hours-scale, device-bound, read-only) passes;
      unknown/revoked `device_id` and bad signature both return the same
      generic rejection (no oracle).
- [ ] 8. Add `POST /api/local-bridge/devices/{device_id}/refresh` in the
      same file, sharing the nonce/signature verification from task 7 but
      deriving scopes from a live `store.IsSendEnabled` read every call,
      never from a presented token, and preserving the device's stable
      `credential_jti` lineage (depends on 7) — DoD: T4 (valid,
      missing, wrong-key, wrong-device, expired-nonce, nonce-replay) and T5
      (grant adds send on next refresh, revoke removes it on next refresh)
      pass.
- [ ] 9. Persist `credential_jti` on the device at first successful
      self-service issuance and reuse it for every successful PoP refresh;
      never overwrite it with a new per-refresh JTI (depends on 6, 7, 8) —
      DoD: concurrent refreshes from the same device all produce credentials
      carrying the same lineage; revoking that one lineage invalidates every
      still-live credential issued for the device.
- [ ] 10. Add `DeviceID` to `auth.Identity` (`internal/auth/identity.go`)
      and set it from `Claims.DeviceID` in
      `localjwt.Provider.Authenticate` (`internal/auth/localjwt/issuer.go`,
      next to the existing `Jti`/`OriginalIssuedAt` copy) — DoD: a token
      carrying `device_id` surfaces it on `auth.Identity`; existing
      `middleware_test.go` coverage for identity population extended with
      one case.
- [ ] 11. Extend `bridge.Hub.Register` to `Register(userID int64, deviceID
      string) chan Envelope`, storing `deviceID` on `daemonConn`; add
      `Hub.EvictDevice(userID int64, deviceID string) bool` that only
      evicts when the connected device matches (mirroring
      `UnregisterSend`'s discipline) (depends on 10). Also update
      `internal/bridge/tokenhandler.go` so `NewBridgeTokenHandler` copies
      `DeviceID: id.DeviceID` into the derived `aud="bridge"` token; the
      bridge verifier must restore it into `auth.Identity` before
      `server.go` calls `hub.Register(id.UserID, id.DeviceID)` — DoD:
      `hub_test.go` covers right-device/mismatched-device/idempotent eviction,
      and an integration test proves `DeviceID` survives credential → bridge
      token → websocket authentication.
- [ ] 12. Add `revoke_local_bridge_device` MCP tool in
      `internal/mcp/tools.go`: verify device ownership via
      `store.GetDevice`, then `store.RevokeDevice` →
      `store.RevokeWorkerToken` using the device's stable `credential_jti`
      → `localjwt.RevocationCache.Refresh` (synchronous, not TTL-bound) →
      `hub.EvictDevice` (depends on 9, 11) — DoD: T6 passes (revocation
      stops refresh immediately; refuses new connections; all still-live
      credentials in the device lineage are denied; a live websocket for
      the revoked device is closed within the same request, not merely
      within the documented 15s/1h backstop). Ownership mismatch is refused
      without confirming whether the id exists.
- [ ] 13. Add `"user_code"`, `"device_code"`, `"consent_token"`, `"nonce"`,
      `"signature"`, `"device_registration_key"`, `"worker_token"`,
      `"bridge_token"` to `sensitiveKeys` in `internal/audit/redact.go`
      (depends on nothing, can land independently and early) — DoD: T-redact
      below passes; `device_pubkey` deliberately absent, with a comment at
      its logging call site explaining why.
- [ ] 14. Update `cmd/local`'s daemon loop to call the new refresh endpoint
      (with PoP) before the device credential's TTL lapses, replacing (for
      newly activated devices) the "operator still needs to issue this
      device a token" message in `cmd/local/activate.go` with instructions
      to run the (also new, this task) self-service issuance step (depends
      on 7, 8) — DoD: a freshly activated device reaches a working
      `daemon` session with zero operator intervention, matching
      `internal/bridge/DESIGN.md` gap 4 ("No long-lived MCP token to hand
      to `connect`") being closed for the self-service path specifically
      (the hand-signed-HS256 admin workaround remains available and
      unaffected).

## Tests

- [ ] T1. Activation approval with a submitted `device_pubkey` persists it
      on the `local_bridge_devices` row; activation without one is rejected
      at `activate/start` (400).
- [ ] T2. `set_send_consent` grant/revoke: succeeds for the caller's own
      account with no `admin:users` scope; produces an audit row with
      `tool_name = "set_send_consent"` distinct from `"set_account_send"`;
      has no `telegram_id`-shaped parameter to target another account.
- [ ] T3. Self-service issuance (task 7-DoD): first credential for a freshly
      activated device is hours-scale TTL, carries `DeviceID`, uses the
      device-only credential marker, and never carries
      `telegram:messages:send`/`:pin` even when the account's `send_enabled`
      is already true from a prior admin action.
- [ ] T4. PoP refresh matrix: valid signature+nonce succeeds; missing
      nonce/signature, wrong signing key, nonce issued to a different
      `device_id`, expired nonce, and nonce replay each fail with the same
      generic rejection and mint nothing. Every successful refresh retains
      the original device `credential_jti`.
- [ ] T5. Scope-derivation-from-state: grant `send_enabled` after issuance
      → next refresh includes send/pin; revoke → next refresh omits them;
      a refresh in between two grants never reflects a scope from the
      credential presented to trigger it (there is none — refresh takes no
      bearer token, only PoP).
- [ ] T6. Revocation: issue credential A → refresh B → refresh C → revoke
      device; A/B/C all fail authentication/revocation checks, and bridge
      tokens derived from any of them fail as well. Refresh for the revoked
      device fails immediately; a live `/bridge` websocket for the revoked
      device is closed by `EvictDevice` in the revoke call itself; a
      different, non-revoked device of the same user is unaffected.
- [ ] T7. Ownership: `revoke_local_bridge_device` for a `device_id`
      belonging to a different user is refused without revealing whether
      the id exists.
- [ ] T8. Untouched-admin-path regression: `POST /api/mcp/worker-token`'s
      existing test suite (`internal/mcp/mint_worker_token_test.go`,
      `internal/workertoken` handler tests) passes unmodified; no new code
      path calls `workertoken.NewHandler` or bypasses its `admin:users`
      gate. Legacy admin-minted Local Bridge tokens with empty `DeviceID`
      still renew as before, while device-bound credentials are explicitly
      rejected by `/api/mcp/worker-token/renew`.
- [ ] T9. Nonce-endpoint abuse: per-IP rate limiting on
      `/api/local-bridge/devices/{device_id}/nonce` mirrors activation's
      posture (bounded map growth, failure-budget window).
- [ ] T10. Bridge derivation/device eviction: device credential →
      `/api/bridge/token` → verify derived token carries the same `DeviceID`
      → open `/bridge` websocket → `revoke_local_bridge_device` → matching
      socket closes; another device for the same user stays connected.
- [ ] T-redact. Targeted audit/log test proves activation codes, PoP nonces,
      PoP signatures, `device_registration_key`, and minted
      worker/bridge token strings never appear unredacted in slog output,
      while `device_pubkey` (public, non-secret) is deliberately exempt and
      that exemption is asserted, not merely absent from the test.

## Rollback

- Every schema change in task 1 is additive (new nullable columns / a
  defaulted column) — rolling back the binary while the columns exist is
  safe; no down-migration is required, matching this codebase's existing
  additive-migration convention (`addColumnIfMissing`, used throughout
  `internal/db/db.go`).
- The new MCP tools (`set_send_consent`, `revoke_local_bridge_device`) and
  HTTP endpoints (`/api/local-bridge/devices/{device_id}/nonce`,
  `/credential`, `/refresh`) are all net-new routes/tools; reverting the
  deploy to the pre-#483 image removes them cleanly — no existing tool,
  route, or admin flow (`set_account_send`, `set_account_mode`,
  `POST /api/mcp/worker-token`, `POST /api/mcp/worker-token/renew`,
  `POST /api/bridge/token`) is modified in a way that depends on the new
  code being present.
- `Hub.Register`'s signature change (task 11) is the one call-site-breaking
  change; it is confined to `internal/bridge` and its direct callers
  (`server.go`, tests) in this same change set, so rollback is "redeploy the
  previous image", not a partial/mixed-version concern — the relay already
  runs `strategy: Recreate` at one replica, so there is no rolling-mixed-
  version window to worry about for this specific signature change.
- If self-service issuance/refresh needs to be pulled independently of the
  rest of the change (e.g. a signature-verification bug), the admin
  hand-mint path (`POST /api/mcp/worker-token`, purpose `local-bridge`)
  remains fully functional throughout. Legacy admin-minted credentials
  without `DeviceID` keep their existing renew path; device credentials do
  not fall back to that path.
- Revoking a device is only ever additive state (`revoked_at`,
  `worker_token_revocations` row); if a revocation is applied in error, the
  existing recovery path is unaffected: an admin re-mints a fresh worker
  token via `POST /api/mcp/worker-token`, or the owner re-runs `activate`
  to register a replacement device. There is no "un-revoke" primitive
  today (matching `RevokeWorkerToken`/`RevokeDevice`'s existing one-way
  semantics), so this is documented as intentional, not a gap introduced
  here.
