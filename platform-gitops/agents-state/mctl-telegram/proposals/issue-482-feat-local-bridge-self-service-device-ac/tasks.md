# Tasks: issue-482-feat-local-bridge-self-service-device-ac

- [ ] 1. Add `localBridgeActivation` type and `Server.activations` /
      `Server.activationsByState` maps, plus `MaxPendingActivations` and
      `ActivationTTL` fields on `oauth.Config` (defaulted in `oauth.New`
      alongside `MaxPendingAuth`/`MaxPendingEnable`) — DoD: package compiles;
      new fields have doc comments matching the style of `Server.enables` /
      `Config.MaxPendingEnable`; no behavior change yet (nothing populates or
      reads the new maps).

- [ ] 2. Implement `handleActivateStart` (`POST /api/local-bridge/activate/start`)
      (depends on 1) — DoD: validates `telegram_id > 0` and non-empty
      `device_registration_key`, returns 400 with a JSON `{"error": "..."}` body otherwise
      (reuse the package's existing `writeAuthorizeError`-style helper or
      `bridge.writeJSONError`'s pattern); on success stores a `pending`
      activation keyed by a fresh `randomToken(32)` device_code and returns
      `device_code`, `verification_uri`, `verification_uri_complete`,
      `expires_in`, `interval` as JSON; enforces `MaxPendingActivations` with
      oldest-eviction exactly like the existing `MaxPendingAuth`/
      `MaxPendingEnable` blocks; unit tests cover the validation and the
      shape of a successful response.

- [ ] 3. Implement `handleActivateVerify` (`GET /local-bridge/activate`)
      (depends on 2) — DoD: unknown/expired/non-pending `device_code` renders
      a "start over" page and makes no OIDC or store call; a valid pending
      activation gets a fresh `nonce`/PKCE verifier/`oidcState`, is indexed
      into `activationsByState`, and the handler 302s to
      `s.tgoidc.AuthCodeURL(oidcState, nonce, tgChallenge)`; test with a fake
      `Authenticator` (the package already has one for `oauth` tests) asserting
      the redirect target and that `activationsByState` gained exactly one
      entry.

- [ ] 4. Extend `handleTelegramCallback` to recognize an activation `state`
      before falling into the existing `pendingAuth` path, and implement
      `finishActivation` (depends on 3) — DoD: the added branch is the first
      thing in the function after reading `serverState`, is a pure early
      dispatch (`isActivation` false → identical behavior to before this
      change, verified by running the full existing `internal/oauth` test
      suite unmodified and green); `finishActivation` follows design.md's
      steps 1-7 exactly, in particular: zero `store.*` calls before the
      `identity.TelegramID == act.claimedTGID` check passes (T2 — grep the
      diff for this, it is the load-bearing property); `store.RegisterDevice`
      is called with `act.deviceRegKey` as the idempotency key (T1); a
      `db.ErrAccountAlreadyActive` whose `GetAccountMode` is not
      `db.ModeLocal` denies with a "hosted account" reason and returns before
      any `RegisterDevice` call.

- [ ] 5. Implement `handleActivatePoll` (`POST /api/local-bridge/activate/poll`)
      (depends on 4) — DoD: unknown/expired `device_code` → HTTP 400 with a
      body the CLI can distinguish from `{"status":"denied"}`; known →
      `{"status": "pending"|"denied"|"done", ...}` per design.md's field list;
      `done` response contains no bearer/worker/bridge token field of any
      kind (grep the response struct — this is the sub-issue-3 boundary);
      table-driven test covering all three statuses plus the unknown-code
      400.

- [ ] 6. Add the browser result page template(s) (start-over / denied / done /
      internal-error) (depends on 4) — DoD: denied-page copy for "identity
      mismatch" and "hosted account" does not reveal internal error details
      (matches the generic-copy requirement in design.md's platform-impact
      section); reuses the existing `renderEnableError`/`render*Page`
      helpers' style in `internal/oauth` rather than introducing a new
      templating approach.

- [ ] 7. Wire the three new routes into `Server.Register(mux)` and extend
      `Server.sweep` to purge expired entries from `activations` and
      `activationsByState` (depends on 2, 3, 5) — DoD: routes appear in
      `Register`'s doc-commented list next to the `enable_access` routes;
      `TestServer_Sweep`-style test (or a new one) asserts an
      artificially-aged activation is gone from both maps after `sweep` runs,
      matching the existing `enables`/`pending` sweep tests' shape.

- [ ] 8. `cmd/local`: add the `activate` subcommand (depends on 5) — DoD:
      generates/persists a local `device_registration_key` under
      `~/.config/mctl-telegram-local/` if one does not already exist (reused
      on subsequent `activate` runs, matching #481's idempotency-key
      contract); calls `/activate/start`, prints the verification URL,
      polls `/activate/poll` at the server-supplied interval; exits 0 and
      prints a "you're activated, an operator/`connect` step is still needed"
      message on `done`; exits non-zero and prints the reason on `denied` or
      on TTL expiry; covered by `cmd/local/*_test.go`-style tests against a
      `httptest.Server` stub, matching the existing test style in that
      package (e.g. `daemon_test.go`).

- [ ] 9. Update `docs/local-bridge.md`'s operator checklist (depends on 8) —
      DoD: the "What the operator has to do" table's step 1
      (`provision_local_account`/`set_account_mode`) is marked as no longer
      required for a brand-new account that goes through `activate` first;
      steps 2-3 (mint worker token, `set_account_send`) are explicitly called
      out as still operator/sub-issue-3 work, so the doc does not overclaim
      full self-service ahead of that follow-up landing.

## Tests

- [ ] T1. Idempotent retry: calling `start` twice with the same `device_registration_key`
      and completing the browser flow twice for the same Telegram identity
      results in exactly one `telegram_accounts` row and one
      `local_bridge_devices` row (mirrors
      `TestRegisterDevice_IdempotentRetry` and
      `TestProvisionLocalAccount_RefusesExistingActiveAccount`, exercised
      end-to-end through `finishActivation`).
- [ ] T2. Claimed-vs-OIDC mismatch: `start` with `telegram_id=A`, browser
      completes Telegram OIDC as verified identity `B != A` → activation
      `denied`; assert zero rows added to `users`, `telegram_accounts`, and
      `local_bridge_devices` compared to a snapshot taken before the callback
      (not just "no new telegram_accounts row" — the full snapshot, so a
      stray `EnsureUserByTelegramID` call would also fail the test).
- [ ] T3. Hosted account refused: seed an active `mode='hosted'`
      `telegram_accounts` row for a Telegram id, run `start` +
      OIDC-verified-as-that-id through the browser leg → `denied`, reason
      identifies a hosted account, no `local_bridge_devices` row created.
- [ ] T4. `poll` on an unknown `device_code` → HTTP 400, not 200
      `{"status":"pending"}` (a 200 here would make a CLI wait forever on a
      code the server has already forgotten).
- [ ] T5. `poll` before the browser leg has run at all → `{"status":"pending"}`.
- [ ] T6. Expired activation: age an activation past `ActivationTTL`, assert
      both `handleActivateVerify` (start-over page, no OIDC redirect) and
      `handleActivatePoll` (400) treat it as gone, and that `sweep` removes it
      from both maps.
- [ ] T7. `send_enabled` stays `false` and `session_encrypted` stays `NULL`
      on the resulting `telegram_accounts` row after a successful activation
      (regression guard on `ProvisionLocalAccount`'s existing contract, since
      this is the security property the issue calls out explicitly under
      "Security constraints").
- [ ] T8. Regression: the full pre-existing `internal/oauth` test suite
      (ordinary `/oauth/authorize` login, `enable_access`) passes unmodified
      after tasks 1-7, proving the `handleTelegramCallback` branch added in
      task 4 is behavior-preserving for non-activation `state` values.

## Rollback

Every change is additive: three new routes, two new in-memory maps on
`oauth.Server`, one new early-return branch in `handleTelegramCallback`, no
schema migration, no change to `provision_local_account`/`set_account_mode`/
`RegisterDevice` themselves. Rolling back is a plain revert of the PR(s) —
redeploying the previous image immediately removes the three routes (they
404) and drops the new branch in `handleTelegramCallback` (which was a no-op
for every pre-existing `state` value anyway). No data cleanup is required on
rollback: any `telegram_accounts`/`local_bridge_devices` rows a completed
activation created before the rollback remain valid, fully-formed local-mode
accounts indistinguishable from ones an operator provisioned by hand via
`provision_local_account` — the same rows, the same invariants, just created
through a different entry point. If a rollback happens mid-incident and an
operator wants to undo a specific self-service activation, `RevokeDevice`
and `set_account_mode mode="hosted"` (both already shipped, admin-only) are
the existing tools for that; this proposal adds no new revocation path and
needs none.
