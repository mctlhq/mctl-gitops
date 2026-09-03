# Tasks: issue-479-feat-local-bridge-make-onboarding-fully

- [ ] 1. Add `local_bridge_devices` table to `internal/db/db.go`
      (`sqliteSchema()` and `pgSchema()`), plus Store methods for register,
      lookup, revoke, and last-seen updates. — DoD: migrations pass on both
      dialects; insert/lookup/revoke/idempotent retry are unit-tested.
- [ ] 2. Add optional `device_id` claim to `localjwt.Claims` and thread it
      through Mint/Verify. — DoD: legacy tokens without `device_id` verify
      exactly as before.
- [ ] 3. Implement OIDC-proof + local-claim identity matching for activation,
      reusing `internal/auth/telegramoidc.Authenticator`. — DoD: mismatched
      claimed-vs-OIDC Telegram id is refused with no DB mutation.
- [ ] 4. Implement `POST /api/local-bridge/activate/start` and
      `POST /api/local-bridge/activate/poll` plus browser verification flow.
      The CLI may start activation with only its locally learned Telegram id,
      device id/public key, and pending activation transaction; it MUST NOT
      require a pre-existing worker token, bridge token, hosted session, or
      authenticated MCP session. Browser Telegram OIDC is the authority that
      approves exactly one pending device activation. — DoD: start returns a
      device code + verification URL; poll returns pending/denied/done; OIDC
      mismatch is refused; idempotent retry does not duplicate account/device
      rows.
- [ ] 5. Keep activation strictly read-only: successful activation always
      leaves `send_enabled=false`. Add a separate non-admin owner-controlled
      send-consent grant/revoke path scoped to the caller's own account.
      `set_account_send` remains unchanged for admin support/recovery. — DoD:
      activation alone never enables send; explicit owner grant enables it;
      revoke disables it; all transitions produce distinguishable audit rows.
- [ ] 6. Implement self-service Local Bridge credential issuance through an
      internal mint path with an hours-scale TTL and device binding, without
      exposing the admin worker-token mint endpoint to the user. The initial
      activation credential is read-only because activation cannot grant
      send. — DoD: activation returns a working read-only credential and
      existing `POST /api/mcp/worker-token` behavior/tests remain unchanged.
- [ ] 7. Add device-bound proof-of-possession refresh using a server-issued,
      short-lived, single-use nonce and Ed25519 (or equivalent reviewed
      primitive) signature verification. On every refresh, load current
      device/account state and derive scopes from current `send_enabled`;
      never copy scopes blindly from the previous JWT. — DoD: wrong/missing/
      replayed signature fails; legacy no-device tokens retain current renewal
      behavior; send grant is reflected after refresh and send revoke removes
      send scope after refresh.
- [ ] 8. Wire device/account revocation into refresh and bridge lifecycle.
      Refresh must fail immediately after revocation. For an already-active
      websocket, either actively disconnect that device through the Hub or
      define an explicit bounded maximum revocation latency no longer than the
      derived bridge credential TTL. — DoD: tests cover revoked refresh, new
      connection refusal, and the chosen active-connection revocation SLA.
- [ ] 9. Add `cmd/local activate`: generate/persist an Ed25519 device keypair
      (`0600`), call activation start, print verification URL, poll completion,
      and persist the first credential + device id. — DoD: `init && login &&
      activate && daemon` completes onboarding for a brand-new Telegram id
      with zero operator calls.
- [ ] 10. Extend `cmd/local daemon` to perform automatic device-signed refresh
      and keep the existing bearer-only renewal path as legacy fallback. —
      DoD: both new and legacy credential shapes reconnect/refresh correctly.
- [ ] 11. Add activation codes, nonce/signature fields, device secret material,
      and new credential fields to `internal/audit/redact.go`. — DoD: targeted
      tests prove secrets never appear unredacted.
- [ ] 12. Rewrite `docs/local-bridge.md` as a required deliverable, not a
      follow-up: make `init -> login -> activate -> daemon` the primary
      zero-admin setup; split **Client / owner actions** from **Operator:
      support and recovery only**; document read-only-by-default activation,
      the separate owner send-consent grant/revoke flow, hours-scale
      credential TTL + automatic refresh, device binding, revocation behavior,
      and the legacy manually minted worker-token path as compatibility only.
      — DoD: no normal onboarding step requires `provision_local_account`,
      `set_account_send`, `set_account_mode`, or manual
      `POST /api/mcp/worker-token`.
- [ ] 13. Update `internal/bridge/DESIGN.md` in the same implementation PR:
      remove/close the "No self-serve enablement" gap, document the final
      bootstrap trust boundary, device-bound credential lifecycle, scope
      derivation from current consent state, revocation semantics/SLA, and
      legacy compatibility. — DoD: design doc and `docs/local-bridge.md`
      describe the same shipped architecture and do not contradict runtime.

## Tests

- [ ] T1. Unit: activation idempotency and hosted-account refusal.
- [ ] T2. Unit: identity mismatch writes no account/device state.
- [ ] T3. Unit: initial self-service credential is hours-scale, device-bound,
      and read-only.
- [ ] T4. Unit: refresh proof-of-possession covers valid, missing, wrong-key,
      wrong-device, expired-nonce, and nonce-replay cases.
- [ ] T5. Unit: refresh derives scopes from current `send_enabled`; grant adds
      send on next refresh and revoke removes it on next refresh.
- [ ] T6. Unit/integration: device revocation stops refresh immediately and
      enforces the documented active-connection revocation behavior/SLA.
- [ ] T7. Integration/E2E: fresh install -> `init` -> local Telegram `login`
      -> `activate` -> read call -> explicit owner send grant -> send call ->
      credential refresh -> daemon reconnect. Assert throughout that
      `telegram_accounts.session_encrypted` remains NULL.
- [ ] T8. Regression: existing hosted fresh-user flow and hosted->local
      migration pass unmodified.
- [ ] T9. Regression: manually minted Local Bridge worker tokens continue to
      connect/renew through the migration window.
- [ ] T10. Audit: activation, consent, device registration/revocation, and
      credential lifecycle events are distinguishable and secret-free.
- [ ] T11. Docs regression: examples in `docs/local-bridge.md` match actual CLI
      flags/routes and the zero-admin E2E sequence tested in T7.

## Rollback

All new paths are additive. The self-service activation/refresh routes can be
disabled while preserving the existing operator-mediated `connect` and legacy
worker-token flow. `local_bridge_devices` and optional `device_id` claims are
backward-compatible schema/claim additions. Documentation changes must be
reverted together with any code rollback so the documented happy path never
points at unavailable behavior.
