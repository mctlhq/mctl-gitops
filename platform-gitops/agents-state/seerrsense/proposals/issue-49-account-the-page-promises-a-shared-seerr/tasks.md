# Tasks: issue-49-account-the-page-promises-a-shared-seerr

- [ ] 1. Extract the household admission rule in `src/providers/seerr/tenants.ts`
      into a public `householdFallback(email: string): "household" | "none"` on
      `TenantResolver`, and make `householdTenant` (`tenants.ts:111-132`) use it
      on the `ownerOnly` path — DoD: the `!this.household` and
      `householdEmails.has(email.toLowerCase())` checks exist in exactly one
      place; the method is synchronous, makes no network call and does not touch
      the per-subject cache; `npm test -- tenants` still passes unchanged.

- [ ] 2. Report the effective answer from `GET /api/v1/account/connection`
      (`src/api/account.ts:72-85`) by adding `fallback:
      tenants.householdFallback(session.email)` (depends on 1) — DoD: the field
      is always present; it is derived from the resolver, not from
      `config.householdEmails`; no secret or new user-controlled value enters the
      payload; `cache-control: no-store` is unchanged.

- [ ] 3. Return `fallback` from `DELETE /api/v1/account/connection`
      (`account.ts:184-190`) alongside `connected: false` (depends on 2) — DoD:
      the page can state the post-disconnect situation without a second request.

- [ ] 4. Update the response-shape assertion in `tests/account.test.ts` (the
      `Object.keys(body).sort()` check listing `cfAccessConfigured, connected,
      email, seerrUrl, updatedAt`) to include `fallback` (depends on 2) — DoD:
      the assertion still enumerates allowed keys rather than searching for
      secrets, and the suite is green.

- [ ] 5. Give the session an identifier: `issueSession` in
      `src/auth/session.ts:20-34` sets a `jti` (`randomUUID()`), and
      `readSession` returns it as `Session.id` together with `expiresAt` from
      `exp` — DoD: a freshly issued cookie decodes with an `id`; a cookie without
      a `jti` still verifies and returns `id: undefined`.

- [ ] 6. Add `revokeSession(id, expiresAt)` and `isSessionRevoked(id)` to
      `AuthStore` and both implementations (depends on 5) — DoD:
      `MemoryAuthStore` keeps a `Map<string, number>`; `PostgresAuthStore.init`
      creates `revoked_sessions (jti TEXT PRIMARY KEY, expires_at BIGINT NOT
      NULL)` with `CREATE TABLE IF NOT EXISTS`; `purgeExpired` deletes rows past
      their expiry; no existing table is altered.

- [ ] 7. Enforce revocation on read: `readSession` accepts an optional
      `isRevoked` dependency and returns `undefined` for a revoked `jti`;
      `sessionOf` in `src/api/account.ts:56-60` passes
      `(id) => store.isSessionRevoked(id)` (depends on 5, 6) — DoD: every
      `/api/v1/account/*` route refuses a revoked cookie with the existing 401;
      the `/mcp` path is untouched.

- [ ] 8. Add `DELETE /api/v1/account/session` to `registerAccountRoutes`
      (depends on 6, 7) — DoD: it records a revocation when the cookie names a
      session; it clears `SESSION_COOKIE` with `path:"/"`, `httpOnly:true`,
      `sameSite:"lax"`, `secure: config.issuer.startsWith("https://")` — the same
      attributes as `src/api/server.ts:512-518`; it answers 200 even with a
      missing or unreadable cookie; it sets `cache-control: no-store`; it makes no
      call touching `oauth_refresh_tokens` or `user_connections`; no change is
      needed to `PUBLIC_PREFIXES` or `SESSION_PREFIXES` in `server.ts`.

- [ ] 9. Replace the two-arm status branch in `public/account.html:145-152` with
      a single `renderStatus(body)` producing three distinct sentences —
      connected to X / using the shared Seerr / nothing connected yet, attach
      yours below — defaulting to the third when `fallback` is absent or
      unrecognised (depends on 2) — DoD: the third state uses the neutral
      `.status` class, never `.is-bad`; `load()` and the disconnect handler
      (`account.html:180-185`) both go through it; the hardcoded "Disconnected.
      Using the shared Seerr again." sentence is gone.

- [ ] 10. Add a `Sign out` button inside `#signed-in` in `public/account.html`,
      placed above the status line and away from the form's `Disconnect` button
      (depends on 8, 9) — DoD: it is visible in every signed-in state; its
      handler issues `DELETE /api/v1/account/session` with
      `credentials: "same-origin"` and then reloads the page so no form value
      survives; no email address is rendered into the served HTML.

- [ ] 11. Update `README.md` (depends on 8) — DoD: the "Whose Seerr" and
      "Security Model" sections state that the account page reports what the
      caller actually reaches; the new `DELETE /api/v1/account/session` is
      documented as ending the browser session only, with `POST /oauth/revoke`
      (`src/auth/routes.ts:533`) named as the MCP-grant revocation path; the
      `MemoryAuthStore` caveat (revocations lost on restart) is noted.

- [ ] 12. Run `npm run typecheck` and `npm test` (depends on all) — DoD: both
      clean, including `tests/source-hygiene.test.ts`.

## Tests

New tests follow the existing `tests/account.test.ts` style: env reshaped in
`beforeAll`, dynamic `import` of `buildServer`, `stubFetch`, `signIn(app)` for
the cookie.

- [ ] T1. `GET /api/v1/account/connection` for a signed-in subject with no
      connection whose address **is** in `SEERRSENSE_HOUSEHOLD_EMAILS` reports
      `fallback: "household"`; the same call for an address **not** in it reports
      `fallback: "none"`. Removing the membership check from
      `householdFallback` in `tenants.ts` must break the second assertion.
- [ ] T2. With `SEERR_API_KEY` unset (no household client), `fallback` is
      `"none"` even for a listed address — the case a second copy of the email
      list in `account.ts` would have got wrong.
- [ ] T3. `fallback` and `tenant.source` agree: for the same subject and email,
      `TenantResolver.resolve` returns `source: "household"` exactly when the API
      reports `fallback: "household"` (unit-level, in `tests/tenants.test.ts`).
- [ ] T4. The served `/account` page carries all three distinct sentences and
      still branches on `fallback`, so the household case and the none case
      cannot silently converge; the page payload still contains no email address.
- [ ] T5. `DELETE /api/v1/account/connection` returns `fallback` alongside
      `connected: false`, and it matches what a follow-up `GET` reports.
- [ ] T6. Sign-out clears the cookie: `DELETE /api/v1/account/session` answers
      200 with a `Set-Cookie` for `seerrsense_session` that expires it, carrying
      `Path=/`, `HttpOnly` and `SameSite=Lax` — the same attributes it was set
      with.
- [ ] T7. Sign-out ends the session: a follow-up `GET
      /api/v1/account/connection` presenting the *old* cookie value returns 401.
- [ ] T8. Sign-out does not touch MCP grants: a refresh token obtained for the
      same subject still redeems at `POST /oauth/token` after sign-out, and the
      `oauth_refresh_tokens` row survives.
- [ ] T9. Sign-out leaves `user_connections` alone: after attaching a Seerr and
      signing out, signing in again reports `connected: true` with the same
      `seerrUrl`.
- [ ] T10. Sign-out is idempotent and self-authenticating: called with no cookie,
      with an expired cookie, and twice in a row, it answers 200 each time and
      never 500s; called with an MCP access token in the `authorization` header
      or pasted into the cookie, it does not act on any session (audience
      mismatch), matching the existing "does not accept an MCP access token"
      test.
- [ ] T11. Sign-out is not reachable as a `GET`: `GET /api/v1/account/session`
      does not clear the cookie.
- [ ] T12. `purgeExpired` deletes revocation rows past their expiry and leaves
      live ones (`tests/store.test.ts`), and a pre-`jti` cookie still verifies.

## Rollback

Every change is additive and independently revertible.

- **Fastest revert:** redeploy the previous image tag. `revoked_sessions` is left
  behind, unread and harmless; no existing table was altered, so there is no
  down-migration. Any session revoked before the rollback becomes valid again for
  the remainder of its 8 hours, which is the pre-change behaviour.
- **Partial revert of the copy only:** restore the two-arm branch in
  `public/account.html` (static file, no rebuild of server logic needed). The
  extra `fallback` field is then simply ignored by the page.
- **Partial revert of sign-out only:** remove the `DELETE
  /api/v1/account/session` route and the `Sign out` button. `readSession` keeps
  its `isRevoked` hook with an empty denylist, which is a no-op.
- **If the denylist misbehaves** (for example an outage on the revocation
  lookup), stop passing `isRevoked` from `sessionOf` in `src/api/account.ts`: the
  cookie clearing continues to work and sessions revert to stateless
  verification, one line changed.
- Watch after deploy: 401 rate on `/api/v1/account/*` (a spike means the
  revocation check is refusing live sessions) and the row count of
  `revoked_sessions` (steady growth means `purgeExpired` is not running).
