# Design: issue-80-enforce-tenant-ownership-in-custom-domai

## Current state

`plugins/custom-domains-backend/src/plugin.ts` wires the plugin with only
`logger`, `httpRouter`, and `database` as dependencies:

```ts
env.registerInit({
  deps: {
    logger: coreServices.logger,
    httpRouter: coreServices.httpRouter,
    database: coreServices.database,
  },
  async init({ logger, httpRouter, database }) {
    const knex = await database.getClient();
    const store = new CustomDomainStore(knex);
    await store.initialize();
    const router = createRouter({ logger, store });
    httpRouter.use(router);
    registerAuthPolicies(httpRouter);
    ...
```

`registerAuthPolicies` (same file) only marks `/health` as unauthenticated,
so every other route already requires *some* valid Backstage credential
(the framework default). But `createRouter` in `src/router.ts` never reads
`httpAuth` or checks who the caller is relative to the `team` in the
request — every handler goes straight from the raw `req.query`/`req.body`/
`req.params` to `store.*` calls:

- `GET /domains` (`router.ts:54-67`) trusts `req.query.team` verbatim.
- `POST /domains` (`router.ts:70-119`) trusts `req.body.team` verbatim,
  including for the uniqueness check and the `autoDomain` string.
- `POST /domains/:id/verify` (`router.ts:122-145`) and
  `DELETE /domains/:id` (`router.ts:161-171`) fetch the row by `id` via
  `store.getById`, so the row's own `team` column is available, but it is
  never compared against the caller.
- `POST /domains/:id/activate` (`router.ts:148-158`) has the same shape as
  verify/delete.

The platform already solved this exact problem for other plugins.
`plugins/tenant-backend/src/membershipLookup.ts` exports two schema-aware
helpers built for cross-plugin use:

- `getTenantMember(db, isPostgres, tenantName, userId)` — reads
  `tenant_members` from the canonical `tenant-management` Postgres schema
  (or the local SQLite table in dev), returning the member row or
  `undefined`.
- `isAdminUser(db, isPostgres, userId)` — true if the user has `owner`
  role in the `admins` tenant, mirroring `resolveAuth()`'s admin check in
  `tenant-backend/src/router.ts`.

Two plugins already consume these: `plugins/vault-secrets-backend/src/
router.ts` (`checkTenantRole`, `requireTenantRole`, used to gate
`GET /teams/:team/:app/database` and `.../secrets`) and
`plugins/argo-workflows-backend/src/teamAccessAction.ts`. Both resolve
`userId` from `httpAuth.credentials(req, { allow: ['user'] })` +
`userInfo.getUserInfo(credentials).ownershipEntityRefs`, extracting the
GitHub login from the `user:default/{username}` ref — see
`extractUserId` duplicated in both `tenant-backend/src/router.ts` and
`vault-secrets-backend/src/router.ts`. `vault-secrets-backend/src/
plugin.ts:63-64` derives `isPostgres` once at init time:
`const isPostgres = db.client.config.client === 'pg'`.

## Proposed solution

Bring `custom-domains-backend` up to the same pattern used by
`vault-secrets-backend`, with no new authorization mechanism invented:

1. **Add `httpAuth` and `userInfo` to the plugin's deps** in
   `plugins/custom-domains-backend/src/plugin.ts`, and compute
   `isPostgres` from the Knex client the same way `vault-secrets-backend/
   src/plugin.ts:64` does. Pass `httpAuth`, `userInfo`, `db` (the raw
   Knex client, in addition to the `CustomDomainStore` wrapper), and
   `isPostgres` into `createRouter`.

2. **Add a `requireTenantAccess` helper in `router.ts`**, modeled directly
   on `vault-secrets-backend`'s `requireTenantRole`/`checkTenantRole` pair,
   but without the `minimumRole` parameter (the issue does not ask for
   role-tiered access within a tenant — see requirements.md's Open
   questions):

   ```ts
   async function requireTenantAccess(
     req: Request,
     httpAuth: HttpAuthService,
     userInfo: UserInfoService,
     db: Knex,
     isPostgres: boolean,
     team: string,
   ): Promise<{ ok: true; userId: string } | { ok: false; status: 401 | 403; error: string }>
   ```

   Internally: resolve `httpAuth.credentials(req, { allow: ['user'] })`,
   extract `userId` via the same `user:default/{username}` parsing used
   elsewhere; on failure return `{ ok: false, status: 401, ... }`. If
   `isAdminUser(db, isPostgres, userId)` is true, return `ok: true`
   immediately (admin bypass, same as `checkTenantRole`). Otherwise call
   `getTenantMember(db, isPostgres, team, userId.toLowerCase())`; if
   `undefined`, return `{ ok: false, status: 403, ... }`; else `ok: true`.

3. **Gate every `/domains*` route except `/health`:**
   - `GET /domains`: after validating `team` is present (existing check),
     call `requireTenantAccess(..., team)` before calling `store.list`.
   - `POST /domains`: after validating `team`/`service`/`domain` are
     present (existing check), call `requireTenantAccess(..., team)`
     before the uniqueness check / `store.create`.
   - `POST /domains/:id/verify` and `DELETE /domains/:id`: keep the
     existing `store.getById(id)` / 404 check first (order: 401 from auth
     resolution happens inside `requireTenantAccess` before any DB call in
     the *tenant-scoped* routes, but for `:id` routes the `team` needed by
     `requireTenantAccess` is only known after fetching the row — so the
     order becomes: resolve caller credentials only (401 if missing) →
     `store.getById` (404 if missing) → `getTenantMember`/`isAdminUser`
     against the row's `team` (403 if neither). To avoid duplicating the
     credential-resolution logic, split `requireTenantAccess` into two
     composable pieces: `resolveCallerId(req, httpAuth, userInfo)` →
     `401 | userId`, and `authorizeForTeam(db, isPostgres, userId, team)`
     → `403 | ok`. `GET`/`POST /domains` call both in sequence with the
     client-supplied `team`; the `:id` routes call `resolveCallerId`
     first, then `store.getById`, then `authorizeForTeam` with
     `entry.team`.
   - `POST /domains/:id/activate`: same `:id`-route treatment, but
     `authorizeForTeam` is satisfied by tenant membership, admin, OR a
     Backstage service credential (`httpAuth.credentials(req, { allow:
     ['service'] })`), so the Argo ingress-update workflow keeps working.
     This mirrors `tenant-backend`'s `resolveAuth()` Tier 3.
   - `GET /health` stays untouched and public.

4. **No changes to `CustomDomainStore`** (`store.ts`): ownership is
   enforced in the router layer, consistent with how `vault-secrets-
   backend` layers `checkTenantRole` in its router rather than pushing
   authorization into a data-access layer.

5. **No changes to `registerAuthPolicies`**: the existing policy (only
   `/health` public) is already correct and its regression test
   (`plugin.test.ts`) continues to guard it; tenant ownership is an
   additional, independent layer on top of the existing "must be
   authenticated" policy.

## Alternatives

1. **Push the tenant check into `CustomDomainStore`** (e.g.
   `store.list(team, service, callerUserId)` throws if unauthorized).
   Rejected: none of the reference implementations
   (`vault-secrets-backend`, `argo-workflows-backend`) do this: the DB
   layer stays a dumb Knex wrapper, and mixing HTTP-auth concerns
   (`HttpAuthService`, `UserInfoService`) into `store.ts` would diverge
   from the established layering and make the store harder to unit test
   in isolation (see `plugin.test.ts`'s existing pattern of testing the
   router/policy layer directly).

2. **Use Backstage's permission framework
   (`permission-backend-module-team-policy`)** instead of an inline
   membership check. Rejected for this proposal: that plugin implements
   RBAC via Backstage's `PermissionPolicy` for catalog/UI-level
   permissions; the two existing precedents for exactly this
   "cross-tenant IDOR on a custom Express route" problem
   (`vault-secrets-backend`, `argo-workflows-backend`) both bypass the
   permission framework and query `tenant_members` directly through
   `membershipLookup.ts`. Switching custom-domains-backend to a different
   mechanism than its two closest siblings would create inconsistency
   without a clear benefit, and would be a much larger change than the
   issue calls for.

3. **Require `owner` role for delete, any role for list/add/verify**
   (matching vault-secrets-backend's `minimumRole: 'owner'` gate on its
   sensitive Telegram-intake route). Rejected as the primary design: the
   issue's acceptance criteria only ask for member vs. non-member vs.
   anonymous, not role tiers. Recorded as an open question rather than
   silently added scope; `requireTenantAccess`/`authorizeForTeam` is
   written to accept an optional `minimumRole` parameter later without a
   redesign, if a future issue asks for it.

## Platform impact

- **Migrations**: none. No schema change to `custom_domains` or
  `tenant_members`.
- **Backward compatibility**: `GET`/`POST /domains` and
  `POST /domains/:id/verify` / `DELETE /domains/:id` responses are
  byte-for-byte unchanged for authorized callers (tenant members and
  `admins`-tenant owners). The only new behavior is a `403` for calls that
  previously succeeded across tenants — which is the intended fix, not a
  regression, per the issue's acceptance criteria.
- **Resource impact**: each gated route now performs one extra Knex query
  (`getTenantMember` or `isAdminUser`, which itself is one `getTenantMember`
  call against the `admins` tenant) against the `tenant-management` schema.
  This matches the existing per-request cost already paid by
  `vault-secrets-backend`'s equivalent routes; no new connection pool or
  service dependency is introduced since `custom-domains-backend` already
  holds a `database.getClient()` handle.
- **Cross-plugin coupling**: `custom-domains-backend` will import
  `getTenantMember`/`isAdminUser` from `../../tenant-backend/src/
  membershipLookup` via a relative path, exactly as `vault-secrets-
  backend/src/router.ts:9` and `argo-workflows-backend/src/
  teamAccessAction.ts:3` already do — this is an established, if slightly
  unusual (no package.json dependency edge, relying on yarn workspace
  resolution + TypeScript relative import), pattern in this repo, not a
  new one introduced by this proposal.
- **Risks + mitigations**:
  - *Risk*: the Argo ingress-update workflow calling
    `POST /domains/:id/activate` may not currently present service
    credentials Backstage recognizes, breaking domain activation.
    *Mitigation*: `authorizeForTeam` for the activate route accepts the
    service-credential tier in addition to tenant membership/admin (see
    Proposed solution, step 3); flagged as an open question in
    requirements.md to be verified against the actual workflow definition
    (which lives outside this repo) before merge.
  - *Risk*: SQLite local dev (no `tenant-management` Postgres schema)
    could make every membership check fail closed with a `500` instead of
    a clean `403`. *Mitigation*: `membershipLookup.ts`'s
    `isMissingTableError` already treats a missing-table SQLite error as
    "no membership" (returns `undefined`, not a throw), which
    `requireTenantAccess`/`authorizeForTeam` will treat as "not a member"
    (`403`), matching `vault-secrets-backend`'s existing behavior in the
    same environment.
  - *Risk*: case-sensitivity mismatches between the GitHub-login-derived
    `userId` and stored `tenant_members.user_id`. *Mitigation*: lowercase
    the `userId` before the `getTenantMember` call, exactly as
    `vault-secrets-backend/src/router.ts:255` and `tenant-backend/src/
    membershipLookup.ts:59` do.
