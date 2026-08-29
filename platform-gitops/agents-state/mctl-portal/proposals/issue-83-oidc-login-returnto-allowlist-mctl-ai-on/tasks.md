# Tasks: issue-83-oidc-login-returnto-allowlist-mctl-ai-on

- [ ] 1. Add `DEFAULT_POST_LOGIN_PATH`, `isAllowedReturnTo(returnTo: string): boolean`,
      and `sanitizeReturnTo(returnTo: string): string` helpers to
      `plugins/oidc-provider-backend/src/router.ts` (near the other
      `returnTo`/URL helpers such as `deriveCookieDomain` and
      `summarizeUrlHost`) — DoD: helpers compile under the plugin's
      `strict: true` TypeScript config, are pure functions with no `req`/
      `res` dependency, and implement: relative paths (starting with `/`,
      not `//` or `/\`) allowed; absolute URLs allowed only when
      `protocol === 'https:'` and `hostname` is exactly `mctl.ai` or ends
      with `.mctl.ai`; everything else rejected; invalid/unparseable URLs
      rejected (caught, not thrown).
- [ ] 2. Wire `sanitizeReturnTo` into the `/login` handler (depends on 1) —
      DoD: the handler computes the sanitized `returnTo` once, immediately
      after the existing `if (!returnTo) { ... Missing returnTo }` check,
      and uses that single sanitized value for both the
      already-authenticated branch (`buildSessionCookie` +
      `res.redirect`) and the `buildGitHubAuthRedirect(returnTo)` call, so
      a rejected value never reaches `store.savePendingAuth` or
      `res.redirect` unsanitized.
- [ ] 3. Add a `logger.warn` on rejection (depends on 1, 2) — DoD: when
      `isAllowedReturnTo` returns false for a non-empty raw `returnTo`, the
      handler logs a warning including the rejected host via the existing
      `summarizeUrlHost` helper (consistent with existing `[OIDC]`-prefixed
      log lines in this file), without logging the full raw value verbatim
      beyond what `summarizeUrlHost` exposes.
- [ ] 4. Create `plugins/oidc-provider-backend/src/router.test.ts` (depends
      on 1) — DoD: unit tests import and exercise `isAllowedReturnTo`
      (exported for testability, or tested indirectly through a small
      exported `sanitizeReturnTo` if the team prefers not to export the
      boolean predicate) covering the required cases below, following the
      existing `describe`/`it` Jest style used in `sessionAuth.test.ts`.
- [ ] 5. Update the `/login` route's inline comment (depends on 2) — DoD:
      the comment above `router.get('/login', ...)` documents the
      allowlist behavior (relative paths and `https://mctl.ai` /
      `https://*.mctl.ai` only, default-page fallback otherwise) so future
      readers don't reintroduce the open redirect.

## Tests
- [ ] T1. `isAllowedReturnTo('/catalog')` returns `true` (relative path
      accepted).
- [ ] T2. `isAllowedReturnTo('https://app.mctl.ai/x')` returns `true`
      (subdomain of mctl.ai, https, accepted).
- [ ] T3. `isAllowedReturnTo('https://mctl.ai/')` returns `true` (bare
      apex domain accepted).
- [ ] T4. `isAllowedReturnTo('https://evil.example/')` returns `false`
      (unrelated host rejected).
- [ ] T5. `isAllowedReturnTo('//evil.example')` returns `false`
      (protocol-relative value rejected, not treated as a safe relative
      path).
- [ ] T6. `isAllowedReturnTo('https://mctl.ai.evil.example/')` returns
      `false` (lookalike host containing `mctl.ai` as a substring but not
      a dot-boundary suffix, rejected).
- [ ] T7. `isAllowedReturnTo('http://app.mctl.ai/x')` returns `false`
      (correct host but wrong scheme, rejected — https only).
- [ ] T8. `isAllowedReturnTo('not a url')` returns `false` (unparseable,
      non-relative input rejected without throwing).
- [ ] T9. Integration-style test on the `/login` handler (supertest or
      equivalent already used elsewhere in the repo, if available):
      `GET /login?returnTo=https://evil.example/` with no session cookie
      results in the GitHub OAuth redirect (or eventual final redirect)
      targeting `DEFAULT_POST_LOGIN_PATH`, never `https://evil.example/`.
- [ ] T10. Integration-style test: `GET /login?returnTo=/catalog` with a
      valid session cookie redirects to `/catalog` unchanged (normal
      round-trip preserved).

## Rollback
The change is confined to `plugins/oidc-provider-backend/src/router.ts`
(plus a new test file) with no schema or config migration. If the
allowlist proves too strict for a legitimate production caller after
deploy:
1. Revert the commit/PR that introduced `isAllowedReturnTo` /
   `sanitizeReturnTo` and their call site in `/login` (single-file diff,
   straightforward `git revert`).
2. Redeploy `mctl-portal` via the normal `deploy-service` pipeline
   (`mctl_deploy_service action=deploy` in platform terms) to restore prior
   behavior immediately.
3. No data was migrated or persisted in a new shape, so no data cleanup is
   needed on rollback; any `store.savePendingAuth` rows written during the
   rollout window simply expire on their existing TTL as before.
