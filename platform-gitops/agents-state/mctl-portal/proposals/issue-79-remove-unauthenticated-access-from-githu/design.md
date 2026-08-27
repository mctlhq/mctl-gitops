# Design: issue-79-remove-unauthenticated-access-from-githu

## Current state

`plugins/github-app-connect-backend/src/plugin.ts` (`register` -> `init`,
lines 96-131) calls `httpRouter.addAuthPolicy({ path, allow:
'unauthenticated' })` for every route the plugin's router exposes:
`/callback`, `/install-url`, `/repo-access`, `/install-status`, `/repos`,
`/popup-done`, `/repo-tags`, `/service-config`, `/webhook`. The router
itself (`plugins/github-app-connect-backend/src/router.ts`) never inspects
`req` for a Backstage identity — every handler trusts whatever `team`,
`service`, or `repo` query parameters the caller supplies:

- `GET /repos` (router.ts:502) — lists repos for `?team=`, or all
  installations if `team` is omitted.
- `GET /repo-tags` (router.ts:635) — semver tags for `?repo=`.
- `GET /service-config` (router.ts:702) — reads a service's
  `values.yaml` from `mctlhq/mctl-gitops` and returns parsed env var
  names/values and secret key names for `?team=&service=`.
- `GET /repo-access` (router.ts:370) — connection status for
  `?team=&service=&repo=`.
- `GET /install-url` (router.ts:179) — mints an encrypted state token for
  `?team=&service=&repo=` and returns a GitHub App install URL.
- `GET /install-status` (router.ts:470) — polls connection status for
  `?team=&service=&repo=` or a `state` token.
- `GET /callback` (router.ts:244) — GitHub's OAuth-install redirect
  target; gated by `decryptState` (AES-256-CBC keyed off
  `sha256(privateKey)`, with a 10-minute `exp`) when a `state` param is
  present (Flows 1 and 2), or ungated when absent (Flow 3, trusts
  GitHub's `installation_id` directly, verified against GitHub's API).
- `GET /popup-done` (router.ts:197) — static HTML, no query params
  consumed, posts a `BroadcastChannel`/`postMessage` and closes the popup.
- `POST /webhook` (router.ts:783) — gated by `X-Hub-Signature-256` HMAC
  verification against `webhookSecret` (`crypto.timingSafeEqual`).

The platform already has an established pattern for exactly this problem,
used by two other plugins:

- `plugins/tenant-backend/src/membershipLookup.ts` exports
  `getTenantMember(db, isPostgres, tenantName, userId)` (reads
  `tenant_members` from the canonical `tenant-management` schema/table) and
  `isAdminUser(db, isPostgres, userId)` (true iff the user has `owner` role
  in the `admins` tenant).
- `plugins/vault-secrets-backend/src/router.ts` builds on top of that:
  `requireTenantRole(req, httpAuth, userInfo, db, isPostgres, team,
  minimumRole)` resolves the caller via `httpAuth.credentials(req, {allow:
  ['user']})` + `userInfo.getUserInfo(credentials).ownershipEntityRefs`,
  extracts the GitHub login (`extractUserId`, matching
  `user:default/<login>`), and calls `checkTenantRole` which does the
  admin-bypass-then-membership check and returns a typed
  `{ok:true,...} | {ok:false,status,error}` result. Route handlers do:
  ```ts
  const auth = await requireTenantRole(req, httpAuth, userInfo, db, isPostgres, team, 'viewer');
  if (!auth.ok) { res.status(auth.status).json({ error: auth.error }); return; }
  ```
  and log successful reads via `auditSecretRead`.
- `plugins/custom-domains-backend/src/plugin.ts` already documents the
  target end state for a plugin like this in a comment: only `/health` is
  public, everything else "falls back to the Backstage default of
  requiring authentication" (no explicit route-level `unauthenticated`
  policy needed once Backstage's own default kicks in), and it exports
  `registerAuthPolicies` specifically so a unit test can assert the old
  unauthenticated policies are not reintroduced.
- On the frontend, `CurrentConfigField.tsx` already calls
  `vault-secrets`'s team-scoped `/teams/:team/:app/secrets` (which is
  auth-gated via the pattern above) using `fetchApi.fetch(...)` from
  `@backstage/core-plugin-api`'s `fetchApiRef` — this is what attaches the
  Backstage bearer token. By contrast, `GitHubRepoPicker.tsx` (lines 87,
  103) and `GitTagPicker.tsx` (line 78) call `github-app-connect`'s
  `/repos`, `/repos/sync`, and `/repo-tags` with the raw global `fetch()`,
  which sends no Authorization header at all.

`github-app-connect-backend`'s `RouterOptions` (router.ts:9-20) currently
receives `logger, store, appSlug, appId, privateKey, baseUrl,
webhookSecret, catalogClient, scaffolderClient, notifications` — no
`httpAuth`, `userInfo`, `db`, or `isPostgres`. `plugin.ts`'s `env.registerInit`
`deps` (lines 14-22) likewise omits `coreServices.httpAuth`,
`coreServices.userInfo`, and doesn't yet obtain a Knex handle typed for
cross-schema tenant lookups the way `vault-secrets-backend/src/plugin.ts`
does (`database.getClient()` + `isPostgres = db.client.config.client ===
'pg'`).

## Proposed solution

1. **Wire the same auth dependencies `vault-secrets-backend` uses.** Add
   `httpAuth: coreServices.httpAuth` and `userInfo: coreServices.userInfo`
   to `plugin.ts`'s `env.registerInit({ deps: {...} })`, obtain `db` and
   `isPostgres` the same way (`database.getClient()` /
   `db.client.config.client === 'pg'`), and pass all four through to
   `createRouter(options)`.

2. **Reuse `checkTenantRole` / `getTenantMember` / `isAdminUser` directly**
   from `plugins/tenant-backend/src/membershipLookup.ts`, the same way
   `vault-secrets-backend/src/router.ts` imports them
   (`import { getTenantMember, isAdminUser } from
   '../../tenant-backend/src/membershipLookup'`). Add a local
   `requireTenantRole`-equivalent helper in
   `github-app-connect-backend/src/router.ts` (or factor
   `vault-secrets-backend`'s `requireTenantRole`/`checkTenantRole` pair
   into a small shared module both plugins import — see Alternatives) that
   resolves the caller's identity and checks membership with
   `minimumRole: 'viewer'`.

3. **Gate each team-scoped handler** (`/repos`, `/repo-access`,
   `/install-status`, `/install-url`, `/service-config`) with that helper
   at the top of the handler, before any existing param validation that
   doesn't need `team` (missing-`team` 400s stay first where they already
   run first; membership checks run once `team` is known to be present):
   ```ts
   const auth = await requireTenantRole(req, httpAuth, userInfo, db, isPostgres, team, 'viewer');
   if (!auth.ok) { res.status(auth.status).json({ error: auth.error }); return; }
   ```
   `/repos` currently allows `team` to be omitted (falls back to
   `findAllInstallations()` across all teams) — that fallback is itself a
   cross-tenant leak once anonymous access is removed it must require a
   `team` (400 if missing) so there is always a tenant to check membership
   against; the "all installations" mode is dropped unless the caller is a
   platform admin (`isAdminUser`), in which case it is preserved.

4. **`/repo-tags`** is not team-scoped (keyed only by `repo`), so instead
   of a membership check it gets a plain "any authenticated Backstage
   user" check: `await httpAuth.credentials(req, { allow: ['user'] })`,
   401 on failure. This matches the requirement that no route stays
   reachable anonymously while not inventing a team-membership model the
   route has no `team` parameter to support.

5. **`POST /repos/sync`** gets the same team-membership check as `/repos`
   (task 1 confirms whether it needs an explicit `addAuthPolicy` removal
   or was already implicitly covered by Backstage's default-deny once the
   `/repos` unauthenticated entry is gone).

6. **Leave `/callback`, `/popup-done`, and `/webhook`'s `addAuthPolicy:
   'unauthenticated'` entries in place, unchanged.** `/callback` keeps its
   existing `decryptState`/HMAC gate (Flows 1-2) and its existing
   GitHub-API-verified `installation_id` trust (Flow 3) exactly as today —
   the issue explicitly asks for this. `/webhook` keeps its existing
   `X-Hub-Signature-256` HMAC check — the same category of crypto gate as
   `/callback`'s state token, and GitHub cannot present a Backstage bearer
   token to either. `/popup-done` stays public because it is a static,
   parameter-free confirmation page with no data to leak.

7. **Remove the six `httpRouter.addAuthPolicy({ path: ..., allow:
   'unauthenticated' })` calls** for `/repos`, `/repo-tags`,
   `/service-config`, `/repo-access`, `/install-url`, `/install-status`
   from `plugin.ts`, letting them fall back to Backstage's default
   (require authentication), matching `custom-domains-backend`'s
   documented end state. Add a `registerAuthPolicies`-style exported
   function (mirroring `custom-domains-backend/src/plugin.ts`) so a unit
   test can assert only `/callback`, `/popup-done`, `/webhook` remain
   unauthenticated and the six removed policies are never reintroduced.

8. **Fix the frontend call sites that will otherwise 401 once these routes
   require auth.** In `packages/app/src/components/scaffolder/
   GitHubRepoPicker.tsx`, replace the raw `fetch(url)` calls to `/repos`
   (line 87) and `/repos/sync` (line 103) with `fetchApi.fetch(url)` using
   `useApi(fetchApiRef)` (already imported and used this way in
   `CurrentConfigField.tsx` and, for the catalog call, in
   `GitTagPicker.tsx` itself). In `GitTagPicker.tsx`, replace the raw
   `fetch(...)` call to `/repo-tags` (line 78) with the `fetchApi` that
   component already has in scope (line 28) but currently only uses for
   the catalog entity lookup.

9. **Audit logging.** Add a log line on the admin-bypass path (mirroring
   `vault-secrets-backend`'s `auditSecretRead`) so a platform admin reading
   another team's repo/service-config data leaves a trace — this plugin
   currently has no equivalent.

## Alternatives

1. **Duplicate `requireTenantRole`/`checkTenantRole` locally in
   `github-app-connect-backend` instead of importing from
   `vault-secrets-backend`.** Rejected: `vault-secrets-backend` itself
   imports `getTenantMember`/`isAdminUser` from `tenant-backend`, so a
   third copy of the request-auth wrapper logic would be a second
   divergence point for cross-schema Knex handling and admin-bypass
   semantics. Importing the existing helper (or extracting it into a
   shared, small module, e.g. `plugins/tenant-backend/src/requireTenantRole.ts`)
   keeps one implementation. This proposal defaults to importing
   `vault-secrets-backend`'s `requireTenantRole`/`checkTenantRole` (they
   are already exported) rather than extracting a new shared package, to
   minimize surface area; extraction can happen later if a third
   consumer appears.

2. **Use Backstage's permission framework
   (`permission-backend-module-team-policy`) instead of ad hoc membership
   checks.** Rejected for this proposal: the issue explicitly scopes
   "team-policy default-allow fix" out, and every other tenant-scoped
   plugin in this codebase (`vault-secrets-backend`) uses the direct
   `tenant_members` lookup rather than the permission framework for HTTP
   route authorization, so following that precedent keeps the fix
   consistent with the rest of the codebase rather than introducing a
   second authorization mechanism.

3. **Require team membership on `/repo-tags` too, by inferring `team`
   from the `repo` via `store.findByRepo`.** Rejected: `/repo-tags` fetches
   directly from the GitHub API for any repo the App happens to be
   installed on, independent of any stored team/service association (it
   works even for repos never registered via `/callback`), so there is no
   reliable `team` to check membership against. Falling back to "any
   authenticated user" is the closest match to the issue's intent without
   fabricating a team scope the route doesn't have.

4. **Leave `/install-status` unauthenticated since the issue's "Expected
   fix" list doesn't name it.** Rejected: it returns the same connection
   data as `/repo-access` for the same `team/service/repo` triple (or via a
   decrypted `state` token), so leaving it open would defeat the purpose of
   gating `/repo-access`. Treated as in-scope; documented as an
   interpretation call in requirements.md's Open questions.

## Platform impact

- **Migrations:** none. No schema change in this plugin; it reads the
  existing `tenant_members` table owned by `tenant-backend` via the
  established cross-plugin read path (`membershipLookup.ts`'s
  `withSchema('tenant-management')` on Postgres, plain table access on
  SQLite dev).
- **Backward compatibility:**
  - Anonymous callers of `/repos`, `/repo-tags`, `/service-config`,
    `/repo-access`, `/install-url`, `/install-status` will start receiving
    401 instead of 200/400. This is the intended fix, but is a breaking
    change for any caller that isn't the Backstage frontend (see Open
    questions re: undiscovered CLI callers).
  - `/repos` dropping its no-`team` "all installations" fallback for
    non-admins is a behavior change; admins keep the old behavior.
  - The frontend fixes (task 8) are required for the in-repo callers
    (`GitHubRepoPicker.tsx`, `GitTagPicker.tsx`) to keep working; without
    them the onboarding/deploy-version scaffolder templates would break
    for every user, not just attackers.
- **Resource impact:** negligible — one extra DB read (`tenant_members`
  lookup) per request on previously-unauthenticated routes, same cost
  profile as `vault-secrets-backend`'s existing routes.
- **Risks + mitigations:**
  - *Risk:* an undiscovered external caller (CLI, script) of
    `/install-url` or `/repo-access` breaks. *Mitigation:* flagged as an
    open question for the human reviewer before merge; if confirmed, add a
    service-credential bypass (`httpAuth.credentials(req, {allow: ['user',
    'service']})`) the same way other plugins distinguish user vs.
    plugin-to-plugin callers, rather than reopening anonymous access.
  - *Risk:* SQLite local-dev cross-plugin schema access fails silently.
    *Mitigation:* already handled by `membershipLookup.ts`'s
    `isMissingTableError` fallback (treats a missing table as "not a
    member", i.e. fails closed to 403, not open); no new code needed here.
  - *Risk:* forgetting to update `GitHubRepoPicker.tsx`/`GitTagPicker.tsx`
    ships a working backend fix that silently breaks the UI. *Mitigation:*
    task list makes the frontend fix and an end-to-end acceptance check
    explicit, and tests assert both the 401/403 backend behavior and that
    the picker components use `fetchApi.fetch`.
