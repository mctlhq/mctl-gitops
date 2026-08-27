# Tasks: issue-80-enforce-tenant-ownership-in-custom-domai

- [ ] 1. Wire `httpAuth`, `userInfo`, and a raw Knex `db`/`isPostgres` pair
      into `plugins/custom-domains-backend/src/plugin.ts`'s `registerInit`
      deps and pass them through to `createRouter`, following
      `plugins/vault-secrets-backend/src/plugin.ts:24,63-76` exactly
      (`const isPostgres = db.client.config.client === 'pg'`). — DoD: the
      plugin compiles, `createRouter`'s `RouterOptions` interface in
      `router.ts` includes `httpAuth: HttpAuthService`,
      `userInfo: UserInfoService`, `db: Knex`, `isPostgres: boolean`
      alongside the existing `logger`/`store`.

- [ ] 2. Add `resolveCallerId(req, httpAuth, userInfo)` and
      `authorizeForTeam(db, isPostgres, userId, team)` helpers in
      `plugins/custom-domains-backend/src/router.ts`, importing
      `getTenantMember`/`isAdminUser` from
      `../../tenant-backend/src/membershipLookup` (same relative-import
      pattern as `vault-secrets-backend/src/router.ts:9` and
      `argo-workflows-backend/src/teamAccessAction.ts:3`). (depends on 1)
      — DoD: `resolveCallerId` returns `{ userId }` or `{ status: 401,
      error }`; `authorizeForTeam` returns `{ ok: true }` when
      `isAdminUser` is true or `getTenantMember(db, isPostgres, team,
      userId.toLowerCase())` finds a row, else `{ ok: false, status: 403,
      error }`. Unit-testable in isolation (no Express `req`/`res`).

- [ ] 3. Gate `GET /domains` and `POST /domains`: after the existing
      required-field validation, call `resolveCallerId` then
      `authorizeForTeam(..., team)` (the client-supplied `team`) before
      any `store.*` call; return `401`/`403` per the helper result.
      (depends on 2) — DoD: a member of `team` or an `admins`-tenant owner
      gets the unchanged existing response; a non-member authenticated
      caller gets `403` and no `store.list`/`store.create`/`store
      .getByDomain` call happens; an unauthenticated caller gets `401`
      before any DB call.

- [ ] 4. Gate `POST /domains/:id/verify` and `DELETE /domains/:id`: call
      `resolveCallerId` first (`401` on failure) → `store.getById(id)`
      (`404` if missing, unchanged from today) → `authorizeForTeam(...,
      entry.team)` (`403` on failure) → existing logic. (depends on 2) —
      DoD: ordering is auth → existence → ownership; a non-member gets
      `403` without the DNS-verify side effect / delete happening; the
      existing 404-on-missing-id behavior is unchanged for authorized
      callers.

- [ ] 5. Gate `POST /domains/:id/activate` the same way as task 4, but
      `authorizeForTeam`'s failure path additionally accepts a Backstage
      service credential (`httpAuth.credentials(req, { allow: ['service']
      })`) as authorized, so the Argo ingress-update workflow is not
      broken. (depends on 2, 4) — DoD: a tenant member, an admin, and a
      service credential all reach the existing activate logic; a
      non-member user credential gets `403`; unauthenticated gets `401`.

- [ ] 6. Update `plugins/custom-domains-backend/src/plugin.test.ts` (or add
      a new test file) with membership-fixture tests analogous to
      `vault-secrets-backend/src/router.test.ts`'s `fakeDb(memberships)`
      helper, so the ownership logic is covered without a real Postgres.
      (depends on 2, 3, 4, 5) — DoD: see Tests below; all pass under
      `yarn --cwd plugins/custom-domains-backend test`.

- [ ] 7. Re-run the existing `plugin.test.ts` auth-policy regression suite
      unmodified to confirm `registerAuthPolicies` still only exposes
      `/health` — this proposal must not touch that function. (depends on
      1-5) — DoD: `plugin.test.ts`'s two existing `it(...)` cases pass
      without modification.

## Tests

- [ ] T1. Member of `team=acme` calling `GET /domains?team=acme` receives
      the same `200` + domain list as before the change (no regression).
- [ ] T2. Authenticated user who is a member of `team=other-co` (not
      `acme`) calling `GET /domains?team=acme` receives `403` and
      `store.list` is not invoked.
- [ ] T3. Anonymous (no credentials) call to `GET /domains?team=acme`
      receives `401` before any Knex query runs.
- [ ] T4. `admins`-tenant owner (via `isAdminUser`) calling
      `GET /domains?team=acme` or `POST /domains` with `team=acme`
      succeeds even without an `acme` membership row.
- [ ] T5. `POST /domains` with `team=acme` from a non-member of `acme`
      receives `403` and no row is inserted (`store.create` not called).
- [ ] T6. `POST /domains/:id/verify` where the stored row's `team=acme` and
      the caller is a member of `other-co` receives `403`; `store
      .updateStatus` is not called and no DNS lookup (`verifyDns`) is
      performed.
- [ ] T7. `DELETE /domains/:id` where the stored row's `team=acme` and the
      caller is a member of `acme` succeeds (`200`, `store.delete` called)
      — own-tenant flow unchanged.
- [ ] T8. `DELETE /domains/:id` for a nonexistent `id` still returns `404`
      for an authenticated caller (existence check ordering preserved).
- [ ] T9. `POST /domains/:id/activate` succeeds for a Backstage service
      credential even when no `tenant_members` row exists for any tenant.
- [ ] T10. Case-mismatched `userId` (e.g. GitHub login `Alice` vs. stored
      `alice`) still resolves membership correctly (lowercasing applied
      before `getTenantMember`), mirroring
      `vault-secrets-backend/src/router.ts:255`.

## Rollback

This is an additive authorization check confined to
`plugins/custom-domains-backend/src/plugin.ts` and
`plugins/custom-domains-backend/src/router.ts`, with no schema migration
and no changes to `CustomDomainStore` or `registerAuthPolicies`. If it
causes unexpected `403`s in production (e.g. the Argo activate-workflow
credential assumption in task 5 turns out wrong, or a legitimate
membership-sync lag causes false negatives):

1. Revert the commit(s) touching `plugin.ts`/`router.ts` for this plugin
   (`git revert`) — this is a pure code rollback via the normal deploy
   pipeline (`mctl_rollback_service` to the previous image tag, or a
   revert PR through the standard release process), no data to
   back out since no table schema changed.
2. Because the change only adds checks in front of existing logic (it does
   not alter `CustomDomainStore` or the `custom_domains` table), rolling
   back is safe at any time and restores exactly the pre-fix (vulnerable)
   behavior with no data loss or migration to undo.
3. If only the activate-route service-credential assumption (task 5) is
   wrong while the rest is fine, the narrower fix is to widen
   `authorizeForTeam`'s accepted tiers for that one route rather than a
   full revert.
