# Tasks: issue-79-remove-unauthenticated-access-from-githu

- [ ] 1. Confirm whether `POST /repos/sync` (router.ts:530) is already
      implicitly authenticated by Backstage's default-deny (no explicit
      `addAuthPolicy` entry today, and `addAuthPolicy` path matching is
      exact per `vault-secrets-backend/src/plugin.ts`'s comment), by
      writing a failing-then-passing test against the running router. — DoD:
      documented in a code comment near the route and covered by T2/T3
      below regardless of the answer.

- [ ] 2. Wire `httpAuth`, `userInfo`, `db`, `isPostgres` into
      `plugins/github-app-connect-backend/src/plugin.ts`'s
      `env.registerInit({ deps })` and pass them into `createRouter(...)`,
      following `plugins/vault-secrets-backend/src/plugin.ts`'s pattern
      (`coreServices.httpAuth`, `coreServices.userInfo`,
      `database.getClient()`, `db.client.config.client === 'pg'`). — DoD:
      `RouterOptions` in `router.ts` gains `httpAuth: HttpAuthService`,
      `userInfo: UserInfoService`, `db: Knex`, `isPostgres: boolean`;
      plugin compiles and starts locally against SQLite.

- [ ] 3. Add a `requireTenantRole`-equivalent check to
      `github-app-connect-backend/src/router.ts`, either by importing
      `requireTenantRole`/`checkTenantRole` from
      `plugins/vault-secrets-backend/src/router.ts` or by adding a local
      wrapper that calls `getTenantMember`/`isAdminUser` from
      `plugins/tenant-backend/src/membershipLookup.ts` directly (depends
      on 2). — DoD: a single reusable function exists in this plugin that,
      given `req` and a `team` string, returns 401 (no/invalid Backstage
      user credentials), 403 (authenticated but not a member of `team` and
      not an admin), or an auth-context object on success.

- [ ] 4. Gate `GET /repos` (router.ts:502): require `team` (400 if
      missing, dropping the no-`team` "all installations" fallback for
      non-admins), then apply the task-3 check with `minimumRole:
      'viewer'`; preserve the all-installations fallback only when
      `isAdminUser` is true (depends on 3). — DoD: 401/403/200 behavior
      matches requirements.md; admin-without-team-param behavior
      unchanged.

- [ ] 5. Gate `GET /repo-access` (router.ts:370) and `GET /install-status`
      (router.ts:470) with the task-3 check on `team` (depends on 3). —
      DoD: both existing `team` 400-validations run first, membership
      check runs once `team` is known.

- [ ] 6. Gate `GET /install-url` (router.ts:179) and `GET /service-config`
      (router.ts:702) with the task-3 check on `team` (depends on 3). —
      DoD: same 401/403/200 contract; response bodies unchanged on
      success.

- [ ] 7. Gate `GET /repo-tags` (router.ts:635) with an
      any-authenticated-user check (`httpAuth.credentials(req, {allow:
      ['user']})`, 401 on failure) — no team-membership check, per
      design.md alternative 3 (depends on 2).

- [ ] 8. Apply the task-3 team check to `POST /repos/sync` (router.ts:530)
      (depends on 1, 3).

- [ ] 9. Remove the `httpRouter.addAuthPolicy` entries for `/repos`,
      `/repo-tags`, `/service-config`, `/repo-access`, `/install-url`,
      `/install-status` from `plugin.ts`; keep `/callback`, `/popup-done`,
      `/webhook` unchanged. Add an exported `registerAuthPolicies`
      function (mirroring `custom-domains-backend/src/plugin.ts`) so a
      unit test can assert the removed policies stay removed (depends on
      4, 5, 6, 7, 8). — DoD: only `/callback`, `/popup-done`, `/webhook`
      remain in the unauthenticated list.

- [ ] 10. Add an audit log line on the admin-bypass path (mirroring
      `vault-secrets-backend`'s `auditSecretRead`) for
      `/repos`, `/repo-access`, `/install-status`, `/install-url`,
      `/service-config` (depends on 3). — DoD: log includes team, service
      (where applicable), caller user id, and whether admin bypass was
      used; never logs secret values (this plugin doesn't return secret
      values, only key names, so no new redaction is needed beyond what
      `/service-config` already returns).

- [ ] 11. Update `packages/app/src/components/scaffolder/
      GitHubRepoPicker.tsx`: replace the raw `fetch(url)` calls to
      `/repos` (line 87) and `/repos/sync` (line 103) with
      `fetchApi.fetch(url)`, adding `useApi(fetchApiRef)` (import from
      `@backstage/core-plugin-api`) alongside the existing `discoveryApi`
      and `identityApi` hooks (depends on 9). — DoD: component compiles;
      manual/E2E check shows repo list still loads for an authenticated
      team member.

- [ ] 12. Update `packages/app/src/components/scaffolder/
      GitTagPicker.tsx`: replace the raw `fetch(...)` call to
      `/repo-tags` (line 78) with the `fetchApi` already in scope (line
      28, currently only used for the catalog entity lookup) (depends on
      9). — DoD: component compiles; tag list still loads for an
      authenticated user.

- [ ] 13. Update `CLAUDE.md`/plugin docs if any documented API surface
      changed (check `README.md`'s plugin table entry for
      `github-app-connect-backend`, currently "Self-service GitHub App
      installation, Actions log streaming, catalog discovery" — no wording
      change expected, but confirm) (depends on 9). — DoD: docs still
      accurate; no stale "public endpoint" claims remain anywhere in the
      repo.

## Tests

- [ ] T1. Unauthenticated `curl`-equivalent (supertest, no Authorization
      header) to each of `/repos`, `/repo-tags`, `/service-config`,
      `/repo-access`, `/install-url` returns 401. (`/install-status`
      included per the Open-questions interpretation.)
- [ ] T2. Authenticated request from a user who is not a member of the
      `team` in the query string (and not an `admins`-tenant owner)
      returns 403 for `/repos`, `/service-config`, `/repo-access`,
      `/install-url`, `/install-status`.
- [ ] T3. Authenticated request from a genuine member of `team` returns
      200 with the existing response shape, unchanged, for each of the
      above routes.
- [ ] T4. Authenticated request from an `admins`-tenant owner succeeds for
      a `team` they are not a member of, and the audit log records
      `via_admin_bypass: true` (mirrors
      `vault-secrets-backend/src/router.test.ts`'s
      `checkTenantRole (admin bypass)` suite).
- [ ] T5. `/repo-tags` returns 401 with no credentials and 200 for any
      authenticated user, regardless of team membership (no team
      parameter exists on this route).
- [ ] T6. `/callback` (all three flows), `/popup-done`, and `/webhook`
      remain reachable with no Backstage credentials at all, unchanged
      from current behavior — regression test against the existing
      `router.test.ts` state-token suite plus a new supertest-based check
      that no auth header is required.
- [ ] T7. `registerAuthPolicies`-equivalent unit test (mirroring
      `custom-domains-backend`'s pattern) asserts the six routes never
      register an `unauthenticated` policy again.
- [ ] T8. `POST /repos/sync` behaves per task 1's finding: 401 anonymous,
      403 non-member, 200 member/admin.
- [ ] T9. End-to-end/manual check: as an authenticated team member, run
      the scaffolder onboarding template through `GitHubRepoPicker`
      (install popup -> `/callback` -> `/popup-done` ->
      postMessage/BroadcastChannel -> `/repos/sync` -> `/repos`) and
      confirm no 401/403 appears in the browser network tab, and
      `GitTagPicker`'s `/repo-tags` call succeeds too.

## Rollback

Revert the `plugin.ts` and `router.ts` changes (restore the six
`addAuthPolicy({ allow: 'unauthenticated' })` entries and drop the
membership checks) and revert the two frontend `fetch` -> `fetchApi.fetch`
changes in the same commit/PR — the three changes are interdependent
(gating the backend without fixing the frontend breaks the UI; fixing the
frontend without gating the backend is a no-op), so they should land and
roll back together as one unit. No data migration or state to unwind:
`tenant_members` is read-only from this plugin's perspective, and no new
tables or columns are introduced. If only the admin-bypass audit logging
(task 10) needs to be pulled back due to log-volume concerns, it can be
reverted independently without touching the auth-gating behavior.
