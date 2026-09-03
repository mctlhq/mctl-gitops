# Tasks: issue-479-feat-local-bridge-make-onboarding-fully

- [ ] 1. Add `local_bridge_devices` table to `internal/db/db.go`
      (`sqliteSchema()` and `pgSchema()`), plus `Store` methods
      `RegisterDevice`, `DeviceByPubkey`, `RevokeDevice`, `TouchDeviceLastSeen`
      — DoD: schema migrations pass on both dialects (existing DB test suite,
      e.g. `internal/db/*_test.go` patterns), new methods unit-tested for the
      insert/lookup/revoke/idempotent-retry paths.
- [ ] 2. Add `device_id` (optional) claim to `localjwt.Claims`
      (`internal/auth/localjwt/issuer.go`) and thread it through `Mint`/
      `Verify` — DoD: existing localjwt tests (`issuer_test.go`,
      `revocation_test.go`) still pass unmodified; a new test confirms a
      token with no `device_id` verifies exactly as before (legacy
      compatibility).
- [ ] 3. Implement the OIDC-proof + local-claim identity match for
      activation as a small internal helper (parallel to
      `enable_access.go`'s `tgID != wantTgID` check), reusing
      `internal/auth/telegramoidc.Authenticator` — DoD: unit test proves a
      mismatched claimed-vs-OIDC-proven `telegram_id` is refused and writes
      no `telegram_accounts`/`users` row change.
- [ ] 4. Implement `POST /api/local-bridge/activate/start` and
      `POST /api/local-bridge/activate/poll` (new file, e.g.
      `internal/bridge/activation.go` or `internal/oauth/activate.go` —
      implementer's call based on which package's session-map helpers are
      more reusable) (depends on 3) — DoD: start returns a device code +
      verification URL; poll returns pending/denied/done; a browser-facing
      page runs the existing `telegramoidc` flow and, on match, calls
      `EnsureUserByTelegramID` + `ProvisionLocalAccount`, treating
      `ErrAccountAlreadyActive` as idempotent success. Table-driven handler
      tests modeled on `internal/oauth/enable_access_test.go`.
- [ ] 5. Add send-consent capture to the activation page (checkbox, parallel
      to `enable_access.go`'s `stepPermissions`/`sendOptIn`) and a
      non-admin self-service send-toggle path (endpoint or MCP tool) scoped
      to the caller's own `user_id` via the existing `actionableAccount`
      predicate (depends on 4) — DoD: granting/revoking send as the account
      owner works without `admin:users`; `set_account_send` (admin path)
      unaffected; both paths write distinguishable audit rows.
- [ ] 6. Implement self-service Local Bridge token issuance: an internal
      mint function reusing `workertoken`'s `allowedLocalBridgeScopes` /
      `workerBridgeAudience` / `Jti` / `OriginalIssuedAt` machinery with a
      new hours-scale default TTL constant, called from the activation
      completion path (not exposed as an admin HTTP handler) (depends on 1,
      4, 5) — DoD: activation returns a working bridge-capable worker token
      scoped read-only when send was not granted, read+send when it was;
      existing `POST /api/mcp/worker-token` behavior/tests untouched.
- [ ] 7. Add device-bound signature verification to the refresh path: extend
      `POST /api/mcp/worker-token/renew` (or add a sibling endpoint) to
      require and verify a signed nonce against the `device_pubkey` row when
      the presented token carries a `device_id` claim; tokens without one
      keep today's bearer-only behavior (depends on 1, 2, 6) — DoD: a
      forged/absent signature is refused for a device-bound token; a legacy
      (no `device_id`) worker token renews exactly as today;
      `renewhandler_test.go`-style table tests cover both branches.
- [ ] 8. Wire device revocation into the refresh check and confirm the
      existing `/bridge` gate (`internal/bridge/server.go`) already fails a
      revoked/expired daemon closed (depends on 1, 7) — DoD: test proves
      revoking a device stops refresh immediately and a daemon whose
      credential subsequently expires cannot reconnect; no changes needed
      to `internal/bridge/server.go` itself if the existing JWT-expiry gate
      already covers it (confirm, don't assume).
- [ ] 9. Add `cmd/local activate` subcommand: generates/persists a device
      Ed25519 keypair (new file under `cmd/local`, `0600`, next to
      `config.json`), calls `activate/start`, prints the verification URL,
      polls `activate/poll`, and on success writes `bridge_token.json`
      directly (reusing `config.go`'s existing atomic-write helpers)
      (depends on 4, 6) — DoD: `mctl-telegram-local init && login && activate
      && daemon` completes onboarding for a brand-new Telegram id with zero
      operator calls, verified locally against a dev server.
- [ ] 10. Extend `cmd/local daemon`'s existing token-renewal call site
      (`daemon.go`) to sign the refresh nonce with the persisted device key
      when one exists, falling back to today's bearer-only renewal for a
      daemon set up via legacy `connect` (depends on 7, 9) — DoD: a daemon
      set up via `activate` renews using device-bound refresh; a daemon set
      up via legacy `connect` (no device key on disk) keeps renewing exactly
      as today.
- [ ] 11. Add new sensitive field/claim names introduced by this work
      (device secret material, activation codes, nonce signatures) to
      `internal/audit/redact.go`'s matcher — DoD: a targeted test proves
      none of the new fields appear unredacted in a log line, matching the
      existing redaction test pattern for this file.
- [ ] 12. Rewrite `docs/local-bridge.md`: replace the "What the operator has
      to do" table and the `Set up` section's steps 1-3 with the
      `init`/`login`/`activate` self-service path; add a distinct
      "Operator: support and recovery" section covering
      `provision_local_account`, `set_account_mode`,
      `POST /api/mcp/worker-token`, and revocation, explicitly marked as not
      part of normal onboarding (depends on 9) — DoD: doc has no remaining
      claim that a fresh user must wait on an operator for the happy path;
      cross-checked against `internal/bridge/DESIGN.md`, which should also
      be updated to move "No self-serve enablement" out of "Remaining gaps."
- [ ] 13. Update `internal/bridge/DESIGN.md`'s "Remaining gaps" and
      "Migration story" sections to reflect the new self-service path and
      device-binding model (depends on 4-10) — DoD: the design doc no longer
      contradicts the shipped implementation; the "Rejected — do not
      implement" section is left intact (this proposal does not touch
      mctl-api/mctl-web).

## Tests

- [ ] T1. Unit: `ProvisionLocalAccount` idempotency contract as consumed by
      the activation caller — retrying activation for the same
      `owner/device/account` triggers `ErrAccountAlreadyActive` and produces
      no duplicate row (extends existing coverage implied by
      `internal/bridge/provision_test.go` / `store_test.go` patterns).
- [ ] T2. Unit: identity-mismatch refusal in activation (claimed
      `telegram_id` != OIDC-proven `telegram_id`) writes no state change.
- [ ] T3. Unit: self-service mint produces a token whose scopes are exactly
      `allowedLocalBridgeScopes` filtered by consent, with an hours-scale
      `exp` and a `device_id` claim.
- [ ] T4. Unit: refresh with a valid device signature succeeds; refresh with
      an invalid/missing signature on a device-bound token fails; refresh of
      a legacy (no `device_id`) token is unaffected — extends
      `internal/workertoken/renewhandler_test.go`.
- [ ] T5. Unit: revoking a device causes the next refresh attempt to fail
      with a clear, actionable error (matching this repo's existing
      "explicit errors, not silent failures" convention, e.g.
      `local-bridge daemon not connected`-style messaging).
- [ ] T6. Unit: send-consent grant/revoke via the new self-service path
      updates `send_enabled` and is scoped strictly to the caller's own
      account (attempting it against another `user_id` fails).
- [ ] T7. Integration/E2E (per issue's own acceptance criteria): fresh
      install -> `init` -> local Telegram `login` -> `activate` (OIDC +
      device binding + optional send consent) -> a read call via the bridge
      -> explicit send consent -> a send call -> credential refresh ->
      daemon reconnect after restart. Assert at every step that
      `telegram_accounts.session_encrypted` stays NULL for this account.
- [ ] T8. Regression: existing hosted fresh-user flow (`enable_access.go`)
      and existing hosted->local migration (`set_account_mode`) pass
      unmodified — run the existing `internal/oauth` and `internal/mcp` test
      suites as a gate, not just new tests.
- [ ] T9. Regression: a manually minted `POST /api/mcp/worker-token`
      (purpose `local-bridge`) issued before this change continues to
      `connect` and renew successfully through the end of its documented
      migration window.
- [ ] T10. Audit: activation, consent grant/revoke, device
      registration/revocation, and credential mint/refresh/revoke each
      produce a distinct, non-secret-leaking audit row (assert via
      `internal/audit` redaction tests plus an `audit_logs` content check).

## Rollback

Every new code path is additive and gated behind the new `activate`
subcommand / `activate/start`-`/poll` endpoints:

- If the self-service mint or device-binding refresh path misbehaves in
  production, disable the new HTTP routes (feature-flag or simply not
  mounting them, matching the existing pattern of conditionally mounting
  `/api/mcp/worker-token` only `if cfg.WorkerTokenEnabled`-style checks
  already used in `cmd/server/main.go` for the worker-token/agent routes) —
  daemons already onboarded via legacy `connect` are unaffected, since their
  renewal path (`renewhandler.go`) is untouched for tokens with no
  `device_id`.
- If a specific device/account activation is wrong (e.g. bound to an
  incorrect identity due to an OIDC edge case), an operator revokes the
  device row and/or the account via the existing `set_account_mode`/manual
  revocation tools — no data migration is needed to undo a single bad
  activation.
- The `local_bridge_devices` table and `device_id` claim are purely additive;
  rolling back the code that writes them leaves existing accounts and tokens
  unaffected (unknown/absent `device_id` was always the legacy-compatible
  case, not an error case).
- `docs/local-bridge.md` and `internal/bridge/DESIGN.md` changes are
  reverted with the code change in the same PR/revert to avoid documenting a
  flow that no longer exists.
