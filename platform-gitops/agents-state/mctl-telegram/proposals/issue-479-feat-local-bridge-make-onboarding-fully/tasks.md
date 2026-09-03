# Tasks: issue-479-feat-local-bridge-make-onboarding-fully

- [ ] 1. Add `local_bridge_devices` table migration (sqlite + postgres
      branches) in `internal/db/db.go`, following the existing
      `addColumnIfMissing`/`CREATE TABLE IF NOT EXISTS` pattern used for
      `telegram_accounts.mode`. — DoD: fresh DB and an existing DB both
      migrate cleanly (new + upgrade test, mirroring
      `internal/db/local_account_test.go`'s style); columns
      `device_id, user_id, telegram_user_id, public_key, created_at,
      last_refreshed_at, revoked_at` exist with an index on
      `(user_id) WHERE revoked_at IS NULL`.

- [ ] 2. Add `Store.ActivateLocalAccount` in `internal/db/store.go`
      (depends on 1) — DoD: unit tests cover (a) fresh telegram id → new row
      + new device row, `existing=false`; (b) same user+device re-run →
      no duplicate rows, `existing=true`; (c) existing `mode='hosted'` row →
      returns `ErrAccountAlreadyActive` unchanged; (d) existing `mode='local'`
      row from a *different* device → device row added, account row
      untouched. Reuses `ProvisionLocalAccount`'s `WHERE NOT EXISTS` insert
      for the account row rather than duplicating its SQL.

- [ ] 3. Add `internal/localbridgecred` package: mint/verify helpers for
      `aud=["local-bridge-access"]` JWTs carrying `DeviceID`, scopes derived
      from send-consent state, and hours-scale TTL, built on
      `internal/auth/localjwt.Issuer`/`Claims` (depends on 1) — DoD: unit
      tests for mint, verify, expiry, and scope derivation
      (read-only vs read+send+pin), mirroring
      `internal/workertoken/tokenhandler_test.go`'s structure.

- [ ] 4. Add nonce-challenge + Ed25519 signature verification for device
      refresh: `GET /api/local-bridge/refresh/nonce`,
      `POST /api/local-bridge/refresh` (depends on 2, 3) — DoD: refresh
      succeeds only with a valid signature over an unexpired, single-use
      nonce for a non-revoked device; reused/expired/wrong-key/wrong-device
      attempts are rejected with tests for each; scopes/telegram id on the
      renewed token are copied forward, never widened (mirrors
      `internal/workertoken/renewhandler_test.go`'s escalation-refusal
      tests).

- [ ] 5. Add `internal/oauth/activate_local.go`: `GET /telegram/activate`
      (OIDC-proof + send-consent checkbox, reusing
      `telegramoidc.Authenticator` already wired into `oauth.Server`) and
      `POST /api/local-bridge/activate` (device pubkey + activation code →
      calls `ActivateLocalAccount` + mints first `local-bridge-access`
      token) (depends on 2, 3) — DoD: end-to-end handler test proves a
      caller with only an OIDC-proven identity (no `admin:users` scope) can
      activate; a caller attempting to activate a `telegram_id` they did not
      prove via OIDC is rejected; re-running activation for the same
      device is idempotent (asserts against task 2's idempotency).

- [ ] 6. Add `POST /api/local-bridge/send-consent` for post-activation
      grant/revoke, calling `Store.SetSendEnabled` under the caller's own
      identity and writing a distinguishable audit tool_name
      (`local:consent:grant` / `local:consent:revoke`) via
      `Store.LogToolCall` (depends on 5) — DoD: grant and revoke both
      round-trip through `get_my_audit_log`; a read-only activation followed
      by no consent call leaves `send_enabled=false` and `send_message`
      still returns the existing dry-run behavior unchanged.

- [ ] 7. Add admin tool `revoke_local_bridge_device` in `internal/mcp/tools.go`,
      following `revoke_worker_token`'s structure (depends on 1, 4) — DoD:
      sets `local_bridge_devices.revoked_at`, denylists the device's current
      `Jti` via the existing `internal/auth/localjwt/revocation.go` path,
      and a subsequent refresh attempt for that device is rejected end to
      end (test extends `internal/mcp/revoke_worker_token_test.go`'s
      pattern).

- [ ] 8. Wire all new handlers into `cmd/server/main.go` alongside the
      existing `internal/bridge`/`internal/workertoken` mounts, behind the
      same `auth.Middleware(provider, true, m)` chain (depends on 3, 4, 5,
      6) — DoD: `cmd/server/main_test.go`-style smoke test confirms the
      routes exist and reject unauthenticated requests.

- [ ] 9. `cmd/local`: generate and persist an Ed25519 device keypair at
      `init` (encrypted the same way the session DB key is; `0600`,
      `writeFileAtomic`), add an `activate` subcommand that drives the
      device-code exchange against `/telegram/activate` +
      `/api/local-bridge/activate` and writes the returned
      `local-bridge-access` token + `device_id` into `bridge_token.json`
      (depends on 5) — DoD: `cmd/local` unit/integration tests
      (`daemon_test.go`-style, with a fake server) cover a full
      `init` → `activate` → token-on-disk round trip; private key file
      permissions asserted the same way `cmd/local/perms_test.go` already
      asserts for existing secrets.

- [ ] 10. `cmd/local/daemon.go`: prefer `local-bridge-access` +
      device-signed refresh over the legacy worker-token renewal path when
      both are available in `bridge_token.json`; fall back to the existing
      `POST /api/mcp/worker-token/renew` path when only a legacy worker
      token is present (depends on 4, 9) — DoD: daemon tests cover both
      credential shapes reconnecting/refreshing successfully, and a
      revoked device failing to refresh and surfacing the same style of
      explicit, actionable error `docs/local-bridge.md` already documents
      for `local-bridge daemon not connected`.

- [ ] 11. Rewrite `docs/local-bridge.md`'s "What the operator has to do"
      section into two explicit sections, "Client / owner actions" (local
      login, `activate`, optional send consent, `daemon`) and "Operator
      actions" (support/recovery/revocation only), and update "Set up" to
      show the new zero-admin sequence as the primary path while keeping
      the existing `connect`-with-hand-minted-token flow documented as the
      legacy/support path (depends on 9, 10) — DoD: doc no longer lists any
      step under "before you run `connect`" as required for a fresh user;
      `internal/bridge/DESIGN.md`'s "Remaining gaps" #5 ("No self-serve
      enablement") entry is updated to reflect what shipped.

## Tests

- [ ] T1. Unit: `ActivateLocalAccount` idempotency and hosted-refusal cases
      (task 2's DoD, extends `internal/db/local_account_test.go`).
- [ ] T2. Unit: `local-bridge-access` JWT mint/verify/scope-derivation
      (task 3's DoD).
- [ ] T3. Unit: device refresh nonce/signature verification, including
      replay of a used nonce and signature-with-wrong-key rejection
      (task 4's DoD).
- [ ] T4. Integration: OIDC-proof → activation → first credential issuance,
      asserting no `telegram_accounts.session_encrypted` value is ever
      written during this path (direct DB assertion, satisfying the issue's
      "E2E assertions prove no hosted Telegram session is stored" criterion)
      (task 5's DoD).
- [ ] T5. Integration: read-only activation (no send consent) completes
      successfully and `send_message` still dry-runs; a later
      `send-consent` grant flips it to a real send path (task 6's DoD).
- [ ] T6. Integration: device revocation blocks refresh and the next bridge
      connection attempt is refused (task 7's DoD, extends
      `internal/bridge/server_reconnect_test.go`'s style).
- [ ] T7. End-to-end (closest existing analogue: `cmd/canary`): fresh
      install → local Telegram login (`cmd/local login`) → self-service
      `activate` → a read call through the bridge → explicit send consent →
      a send call → credential refresh → daemon reconnect after refresh —
      covering the issue's acceptance-criteria E2E bullet in one scripted
      run against a test server.
- [ ] T8. Regression: existing `provision_local_account`, `set_account_mode`,
      `set_account_send`, `POST /api/mcp/worker-token`,
      `POST /api/mcp/worker-token/renew` test suites
      (`internal/mcp/tools_test.go`, `internal/workertoken/*_test.go`) pass
      unmodified, proving the operator/support path is untouched.

## Rollback

Every change here is additive: a new table, new handler files, a new CLI
subcommand, and fallback-preserving changes to `daemon.go`. Nothing modifies
the schema or behavior of `provision_local_account`, `set_account_mode`,
`set_account_send`, or the existing worker-token mint/renew endpoints.

- **Application-level rollback**: redeploy the previous image. The new
  `local_bridge_devices` table and any rows in it are simply unused by the
  old binary; no destructive migration needs reverting. Daemons that already
  upgraded to `activate`-based credentials keep a `local-bridge-access`
  token that the old server binary's `/mcp` provider still accepts as an
  ordinary JWT for read/send scopes (audience checking remains opt-in, same
  as today's worker-token audiences) — but the old binary cannot refresh it
  once it expires (hours-scale), so an operator must fall back to minting a
  legacy worker token via `POST /api/mcp/worker-token` and running
  `cmd/local connect` for any daemon that was mid-migration at rollback
  time. This is the same "manual operator mint" path that exists today, not
  a new failure mode.
- **Partial rollback (disable self-service only)**: gate the new
  `/telegram/activate` and `/api/local-bridge/*` routes behind a config flag
  in `cmd/server/main.go` (consistent with how other optional wiring in this
  codebase is toggled) so they can be turned off without a redeploy, leaving
  the operator-mediated path as the only route while the schema/handlers
  stay in place for a follow-up retry.
- **Data cleanup**: revoking a device (`revoke_local_bridge_device`, task 7)
  is non-destructive (`revoked_at` timestamp, row retained for audit) and
  needs no special rollback handling.
