# Tasks: issue-483-feat-local-bridge-owner-send-consent-dev

- [ ] 1. Add `local_bridge_devices` columns `device_pubkey` (BLOB/BYTEA,
      nullable), `device_pubkey_algo` (TEXT, default `'ed25519'`), and
      `current_jti` (TEXT, nullable) via `addColumnIfMissing` in
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
      `maxWorkerTokenTTL`, always sets `Claims.DeviceID`, and takes an
      explicit `Scopes []string` (no purpose-default lookup — the caller
      decides read-only-only vs. state-derived) — DoD: unit tests confirm
      the TTL ceiling differs from `Mint`'s, `DeviceID` is set, and a
      request with scopes outside `allowedLocalBridgeScopes` is rejected
      exactly like `Mint`'s existing check.
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
      never from a presented token (depends on 7) — DoD: T4 (valid,
      missing, wrong-key, wrong-device, expired-nonce, nonce-replay) and T5
      (grant adds send on next refresh, revoke removes it on next refresh)
      pass.
- [ ] 9. Claim `current_jti` and `credential_issued_at` with ONE conditional
      UPDATE at first issuance (`WHERE device_id = ? AND current_jti IS NULL
      AND revoked_at IS NULL`, 0 rows affected -> 409), and have every
      refresh read both and stamp the same values (depends on 6, 7, 8) —
      DoD: a device that has issued once and
      refreshed several times still has exactly one jti across all its live
      credentials, and revoking it denylists every one of them; a test
      asserts that a credential obtained BEFORE a refresh is rejected by the
      revocation denylist after the device is revoked. Concurrent refreshes
      are safe by construction because they all stamp the same stored value;
      concurrent FIRST issuances are made safe by the conditional claim, not
      by assumption — the row is the lock, so nothing depends on both
      requests reaching the same process.
- [ ] 9b. Give `MintForDevice` its own audience marker
      (`workerDeviceAudience = "mcp-worker-device"`) instead of
      `workerBridgeAudience` (depends on 6) — DoD: `POST
      /api/mcp/worker-token/renew` presented with a device credential
      answers 403 "token is not a worker token", proven by a test; the renew
      handler itself is unmodified; the `/bridge` token path and the MCP
      auth middleware still accept the device credential.
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
      `UnregisterSend`'s discipline) (depends on 10) — DoD: `hub_test.go`
      covers evicting the right device, refusing to evict a mismatched
      device, and idempotence on a repeated `EvictDevice` call. Update
      `internal/bridge/server.go`'s `NewBridgeHandler` call site
      (`hub.Register(id.UserID)` → `hub.Register(id.UserID, id.DeviceID)`)
      and every existing caller/test of `Hub.Register`.
- [ ] 12. Add `revoke_local_bridge_device` MCP tool in
      `internal/mcp/tools.go`: verify device ownership via
      `store.GetDevice`, then `store.RevokeDevice` →
      `store.RevokeWorkerToken` (using the device's `current_jti`, when
      set) → `localjwt.RevocationCache.Refresh` (synchronous, not
      TTL-bound) → `hub.EvictDevice` (depends on 9, 11) — DoD: T6 passes
      (revocation stops refresh immediately — verified against task 8's
      live `GetDevice` check; refuses new connections; a live websocket for
      the revoked device is closed within the same request, not merely
      within the documented 15s/1h backstop). Ownership mismatch (device
      belongs to a different user) is refused without confirming whether
      the id exists.
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
      on the `local_bridge_devices` row; activation WITHOUT one is rejected
      at `activate/start` with 400 AND an error message that names the
      required client upgrade. Assert on the message, not only the status:
      a generic 400 satisfies the status check while leaving the user with
      no idea why their working client stopped working, which is the whole
      point of accepting this as a breaking change deliberately. Validate by
      mutation: replacing the message with a generic one makes this test
      fail.
- [ ] T2. `set_send_consent` grant/revoke: succeeds for the caller's own
      account with no `admin:users` scope; produces an audit row with
      `tool_name = "set_send_consent"` distinct from `"set_account_send"`;
      has no `telegram_id`-shaped parameter to target another account.
- [ ] T3. Self-service issuance (task 7-DoD): first credential for a freshly
      activated device is hours-scale TTL, carries `DeviceID`, and never
      carries `telegram:messages:send`/`:pin` even when the account's
      `send_enabled` is already true from a prior admin action.
- [ ] T4. PoP refresh matrix: valid signature+nonce succeeds; missing
      nonce/signature, wrong signing key, nonce issued to a different
      `device_id`, expired nonce, and nonce replay each fail with the same
      generic rejection and mint nothing.
- [ ] T5. Scope-derivation-from-state: grant `send_enabled` after issuance
      → next refresh includes send/pin; revoke → next refresh omits them;
      a refresh in between two grants never reflects a scope from the
      credential presented to trigger it (there is none — refresh takes no
      bearer token, only PoP).
- [ ] T5b. Renew is not a way around state-derived scopes: mint a device
      credential while `send_enabled` is true, revoke send consent, then
      present that credential to `POST /api/mcp/worker-token/renew` — it
      MUST be refused, not renewed with the stale send scope carried
      forward. Validate by mutation: stamping `workerBridgeAudience` instead
      of the device marker makes this test fail.
- [ ] T5c. One lineage per device: issue, refresh twice, then revoke the
      device — the credential from BEFORE the refreshes must be rejected by
      the revocation denylist, not merely the newest one.
- [ ] T5d. Concurrent first issuance: fire two `/credential` requests for the
      same freshly activated device at once — exactly one succeeds, the other
      gets 409 with nothing minted, and the device's row names the jti of the
      credential that was actually handed out. Validate by mutation:
      replacing the conditional claim with read-then-write makes this test
      fail with two live credentials and one of them unnamed.
- [ ] T5e. Issuance racing revocation: revoke the device between the PoP
      check and the claim — the conditional UPDATE's `revoked_at IS NULL`
      predicate must make the issuance lose, with no credential minted.
- [ ] T5f. `OriginalIssuedAt` survives refresh: issue, refresh, and assert
      the refreshed credential carries the SAME `OriginalIssuedAt` as the
      first one, read back from `credential_issued_at`. Validate by
      mutation: stamping `time.Now()` on refresh makes this test fail.
- [ ] T6. Revocation: refresh for a revoked device fails immediately
      (same request cycle as the revoke call, not merely within a TTL);
      `POST /api/bridge/token` and `POST /api/mcp/worker-token/renew`
      against the revoked device's jti fail within
      `localjwt.MaxRevocationCacheTTL`; a live `/bridge` websocket for the
      revoked device is closed by `EvictDevice` in the revoke call itself;
      a different, non-revoked device of the same user is unaffected by
      the eviction.
- [ ] T7. Ownership: `revoke_local_bridge_device` for a `device_id`
      belonging to a different user is refused without revealing whether
      the id exists.
- [ ] T8. Untouched-admin-path regression: `POST /api/mcp/worker-token`'s
      existing test suite (`internal/mcp/mint_worker_token_test.go`,
      `internal/workertoken` handler tests) passes unmodified; no new code
      path calls `workertoken.NewHandler` or bypasses its `admin:users`
      gate.
- [ ] T9. Nonce-endpoint abuse: per-IP rate limiting on
      `/api/local-bridge/devices/{device_id}/nonce` mirrors activation's
      posture (bounded map growth, failure-budget window).
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
  remains fully functional throughout, since it shares only the `Claims`
  shape and `allowedLocalBridgeScopes` — not the new mint/verify code path
  — with the self-service tools. An operator can always fall back to
  hand-minting for an affected user while a fix ships.
- Revoking a device is only ever additive state (`revoked_at`,
  `worker_token_revocations` row); if a revocation is applied in error, the
  existing recovery path is unaffected: an admin re-mints a fresh worker
  token via `POST /api/mcp/worker-token`, or the owner re-runs `activate`
  to register a replacement device. There is no "un-revoke" primitive
  today (matching `RevokeWorkerToken`/`RevokeDevice`'s existing one-way
  semantics), so this is documented as intentional, not a gap introduced
  here.
