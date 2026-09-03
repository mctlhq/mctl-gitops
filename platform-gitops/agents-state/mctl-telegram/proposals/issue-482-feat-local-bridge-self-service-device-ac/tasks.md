# Tasks: issue-482-feat-local-bridge-self-service-device-ac

- [ ] 1. Add `localBridgeActivation` type and the three `Server` indexes
      (`activations` by device_code, `activationsByState`,
      `activationsByUserCode`), the failed-submission rate limiter, and the
      two removal helpers: `unindexActivation` (secondary indexes only, used
      on resolution, so a finished activation stays pollable by `device_code`)
      and `dropActivation` (all three, used only by eviction and `sweep`).
      Getting these the wrong way round loses the CLI's result silently. Plus
      `MaxPendingActivations int`, `ActivationTTL time.Duration`,
      `ActivationFailBudget int`, `ActivationFailWindow time.Duration` and
      `TrustedProxyCIDRs []netip.Prefix` on `oauth.Config` (defaulted in
      `oauth.New` alongside `MaxPendingAuth`/`MaxPendingEnable`;
      `TrustedProxyCIDRs` parsed from `TRUSTED_PROXY_CIDRS`, defaulting to
      `10.42.0.0/16` and `10.43.0.0/16`, and an empty or unparseable value
      meaning trust nothing — never trust everything) — DoD: package compiles;
      new fields have doc comments matching the style of `Server.enables` /
      `Config.MaxPendingEnable`; no behavior change yet (nothing populates or
      reads the new maps).

- [ ] 2. Implement `handleActivateStart` (`POST /api/local-bridge/activate/start`)
      (depends on 1) — DoD: validates `telegram_id > 0` and non-empty
      `device_registration_key`, returns 400 with a JSON `{"error": "..."}` body otherwise
      (reuse the package's existing `writeAuthorizeError`-style helper or
      `bridge.writeJSONError`'s pattern); on success stores a `pending`
      activation keyed by a fresh `randomToken(32)` device_code, indexed by a
      fresh `user_code` regenerated on collision with a live one (T24), and returns `device_code`, `user_code`,
      `verification_uri`, `expires_in`, `interval` as JSON; enforces
      `MaxPendingActivations` with oldest-eviction exactly like the existing
      `MaxPendingAuth`/`MaxPendingEnable` blocks, evicting via
      `dropActivation`; unit tests cover the validation and the
      shape of a successful response. The response carries `user_code` and a
      parameterless `verification_uri`, and **no `verification_uri_complete`** —
      grep the response struct and the handler for that name and for any
      string-concatenated URL carrying `device_code`/`user_code`; its absence
      is a security property, not a style choice (see requirements.md's
      resolved open question).

- [ ] 3. Implement `handleActivateForm` (`GET /local-bridge/activate`) and
      `handleActivateVerify` (`POST /local-bridge/activate`) (depends on 2) —
      DoD: the `GET` takes no query parameters, renders the `user_code` entry
      form plus a double-submit CSRF token (hidden field + short-lived
      cookie), and makes no lookup, OIDC or store call; the `POST` resolves the
      submitted `user_code` under `s.mu` — refusing outright, before any
      lookup and without setting the state cookie, when the CSRF token is
      missing or does not match the cookie (T20) — and, for unknown/expired/
      already-resolved codes, or a client IP whose failed-submission budget is
      spent, re-renders the form with one generic message (a table-driven test
      asserts the four rejection cases are byte-identical, so the page is not
      an oracle); the lookup goes through `activationsByUserCode` — a test
      asserts no scan of `s.activations` by pinning O(1) behaviour with a
      large map; the redirect sets the `HttpOnly`/`Secure`/`SameSite=Lax`
      state-binding cookie — `Path=/`, host-only, `HttpOnly`/`Secure`/
      `SameSite=Lax`, since the callback that reads it back lands on the
      unrelated path `/oauth/telegram/callback` and a default-scoped cookie
      would never be sent there (T16, T18); a
      valid pending activation gets a fresh `nonce`/PKCE verifier/`oidcState`,
      is indexed into `activationsByState` after any superseded entry for that
      activation has been deleted, and the handler 302s to
      `s.tgoidc.AuthCodeURL(oidcState, nonce, tgChallenge)`; test with a fake
      `Authenticator` (the package already has one for `oauth` tests) asserting
      the redirect target, that `activationsByState` gained exactly one entry,
      and that re-submitting the same `user_code` leaves exactly one entry
      rather than two.

- [ ] 4. Extend `handleTelegramCallback` to recognize an activation `state`
      before falling into the existing `pendingAuth` path, and implement
      `finishActivation` (depends on 3) — DoD: the added branch is the first
      thing in the function after reading `serverState`, is a pure early
      dispatch (`isActivation` false → identical behavior to before this
      change, verified by running the full existing `internal/oauth` test
      suite unmodified and green); `finishActivation` follows design.md's
      steps 1-4 exactly and **makes no `store.*` call whatsoever** — on a
      verified identity that matches the claim it advances the activation to
      `awaiting_consent`, records `act.verifiedIdentity` (the **whole** identity —
      `Username` and display name are needed by the consent handler, which is
      a separate request, and storing only the id would provision accounts
      with empty metadata), mints `consentToken`, and
      renders the consent page. It receives `oidcVerifier`/`oidcNonce` as
      arguments copied by the caller under `s.mu`, and must not read those
      fields off `act` across the `Exchange` call (T15, T23). Grep the whole
      function for `store.` and expect zero hits; that is the load-bearing
      property here (T2, T9).

- [ ] 4b. Implement `handleActivateConsent`
      (`POST /local-bridge/activate/consent`) (depends on 4) — DoD: resolves
      the activation by the form's hidden `user_code` through
      `activationsByUserCode` (O(1); never a scan for a matching
      `consentToken`) and counts failures against the same IP limiter as the
      code form, using the same trusted-proxy-aware client-IP derivation
      (T19); compares `consentToken` in constant time under `s.mu` and
      requires
      `status == "awaiting_consent"`, so neither a replayed nor a
      cross-activation token is accepted; **still under `s.mu`** it flips the
      status to `resolving` and clears `consentToken` before releasing the
      lock and making any store call — and the later `done`/`denied`
      transitions are guarded on `resolving`, not on
      `pending`/`awaiting_consent`, or they abort silently and strand the
      activation (T22) — so a double-clicked Approve or two
      concurrent POSTs with the same token produce exactly one provisioning
      run (a store failure restores `awaiting_consent` with a fresh token);
      Deny
      calls `denyActivation` and returns with no store call; the approve path
      runs design.md's steps 5-8 — `EnsureUserByTelegramID` and
      `ProvisionLocalAccount` fed from `act.verifiedIdentity` (never the
      claimed id, and never empty username/display name), then
      `RegisterDevice` with `act.deviceRegKey` as the idempotency key (T1); a
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
      400, and explicitly covering that an activation sitting in
      `awaiting_consent` or `resolving` polls as `pending` — the CLI's contract
      names only three statuses and must never receive an internal one (T21).

- [ ] 6. Add the browser page templates — `user_code` entry form, **consent
      page**, start-over / denied / done / internal-error (depends on 4b) —
      DoD: the consent page names the device label and the signed-in Telegram
      account, shows the `user_code` so the user can check it against their
      own terminal, and offers Approve and Deny as separate POST actions
      carrying `consentToken` plus the `user_code` as a hidden field (the
      handler's O(1) lookup key); no page embeds `device_code` or `user_code` in
      a link or a redirect target. Denied-page copy for "identity
      mismatch" and "hosted account" does not reveal internal error details
      (matches the generic-copy requirement in design.md's platform-impact
      section); reuses the existing `renderEnableError`/`render*Page`
      helpers' style in `internal/oauth` rather than introducing a new
      templating approach.

- [ ] 7. Wire the five new routes into `Server.Register(mux)` and extend
      `Server.sweep` to purge expired activations (via `dropActivation` —
      resolution uses `unindexActivation` instead) and
      expired rate-limiter entries (depends on 2, 3, 5) — DoD: routes appear in
      `Register`'s doc-commented list next to the `enable_access` routes;
      `TestServer_Sweep`-style test (or a new one) asserts an
      artificially-aged activation is gone from all three maps after `sweep`,
      and that a *resolved* one is still present in `activations`,
      matching the existing `enables`/`pending` sweep tests' shape.

- [ ] 8. `cmd/local`: add the `activate` subcommand (depends on 5) — DoD:
      generates/persists a local `device_registration_key` under
      `~/.config/mctl-telegram-local/` if one does not already exist (reused
      on subsequent `activate` runs, matching #481's idempotency-key
      contract); calls `/activate/start`, prints the verification URL **and
      the `user_code`** with an instruction to type the code on that page —
      and constructs no URL containing the code, asserted by a test; polls
      `/activate/poll` at the server-supplied interval; exits 0 and
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
- [ ] T9. **Phishing guard — no consent, no write.** `start` with
      `telegram_id=V` (a victim) and the attacker's `device_registration_key`;
      drive the browser leg to completion with Telegram OIDC verifying
      identity `V` — i.e. the claimed id and the verified id *match* — and
      then stop, without submitting the consent form. Assert: `poll` does not
      return `done`, and a full snapshot of `users`, `telegram_accounts` and
      `local_bridge_devices` is unchanged. This is the test that would have
      failed on the pre-consent design, and it must be validated by mutation:
      delete the consent gate and confirm it goes red.
- [ ] T10. **Consent token cannot be forged or replayed.** Approving with an
      empty, wrong, or another activation's `consentToken` writes nothing;
      approving twice with the correct token produces exactly one
      `local_bridge_devices` row.
- [ ] T11. **`user_code` brute force is bounded server-side.** Wrong codes
      from one client IP stop being processed once its failed-submission
      budget is spent, and discarding cookies/session does not reset it;
      unknown / expired / already-resolved / budget-exhausted rejections all
      render the identical message.
- [ ] T12. **Double approval provisions once.** Two concurrent
      `POST /activate/consent` with the same valid `consentToken` produce
      exactly one `telegram_accounts` row and one `local_bridge_devices` row;
      the second is refused. Run under `-race`.
- [ ] T13. **Identity metadata survives the request boundary.** A completed
      activation's `telegram_accounts` row carries the username and display
      name from the OIDC identity, not empty strings — the regression guard
      for splitting the callback from the consent handler.
- [ ] T14. **No index leaks.** After eviction, resolution and `sweep`, none of
      `activations`, `activationsByState`, `activationsByUserCode` retains an
      entry for the removed activation.
- [ ] T15. **Race detector.** The whole `internal/oauth` activation suite runs
      under `go test -race` in CI, and at least one test drives `poll`
      concurrently with the browser leg and the sweeper against the same
      activation.
- [ ] T16. **The OIDC leg is not transferable between browsers.** Submit the
      `user_code` in browser A, capture the resulting Telegram authorization
      URL, and replay the callback from browser B (no cookie, or a mismatched
      one): the callback is refused, no consent page is shown, and nothing is
      written. This is the login-CSRF regression guard — without it the
      `user_code` step is decorative, since the attacker can type their own
      code themselves and forward the URL. Mutation-validate it: drop the
      cookie check and confirm it goes red.
- [ ] T17. **A resolved activation stays pollable.** After a `done` (and
      separately a `denied`) resolution, `poll` on the `device_code` still
      returns the terminal status and, for `done`, the `device_id` — it does
      not answer 400 "unknown". Only the TTL sweep removes it.
- [ ] T18. **The state cookie actually reaches the callback.** Drive
      `POST /local-bridge/activate` and then `/oauth/telegram/callback`
      through one `http.Client` with a `CookieJar`, asserting the activation
      is accepted. This is the guard against scoping the cookie to a path the
      callback never matches — which would reject every legitimate activation
      while still reading like a working defence. Assert the cookie is deleted
      afterwards. Mutation-validate by narrowing `Path`: the test must go red.
- [ ] T19. **Rate-limit keying survives the ingress, and only trusts a
      forwarding header from a trusted peer.** Two requests arriving from the
      same trusted-proxy peer with different `X-Forwarded-For` chains get
      separate budgets. A request from an **untrusted** peer carrying a forged
      `X-Forwarded-For` is keyed on its own peer address, so rotating that
      header does not reset the budget — assert the key directly, not just the
      budget, so the test cannot pass by accident. Covers both the `user_code`
      form and the consent endpoint.
- [ ] T20. **The code form is not cross-site submittable.** A
      `POST /local-bridge/activate` carrying a valid `user_code` but no CSRF
      token, or one that does not match the form cookie, is refused before any
      OIDC redirect and sets no state cookie. Mutation-validate: drop the CSRF
      check and confirm it goes red.
- [ ] T21. **`poll` never leaks an internal status.** An activation in
      `awaiting_consent`, and one in `resolving`, both poll as
      `{"status":"pending"}`. Table-driven over every state the machine can be
      in, so a state added later fails the test instead of reaching the CLI.
- [ ] T22. **The happy path completes out of `resolving`.** A full approve
      reaches `done` and `poll` returns the `device_id`; a hosted-account
      refusal discovered after the claim reaches `denied`. Mutation-validate by
      restoring the blanket `pending`/`awaiting_consent` precondition: both
      must go red, since that bug strands the activation silently.
- [ ] T23. **No activation field is read across the network call.** With
      `-race`, drive a second `POST /local-bridge/activate` for the same
      activation while the OIDC exchange is in flight; the run must be clean,
      proving `Exchange` uses copies rather than live fields.
- [ ] T24. **`user_code` collisions are impossible, not improbable.** With a
      stubbed generator that returns a duplicate first, `start` regenerates
      and both activations remain independently reachable by their own codes.

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
