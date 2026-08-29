# team-policy: deny requests without a user; stop blanket-allowing non-catalog permissions

## Context
`plugins/permission-backend-module-team-policy/src/module.ts` implements
`TeamBasedPermissionPolicy.handle()`, the single permission policy wired into
the portal's `@backstage/plugin-permission-backend` (see
`packages/backend/src/index.ts`). Today it fails open in two places:

1. `if (!user) { return { result: AuthorizeResult.ALLOW }; }` (module.ts:43-46)
   — any request the framework cannot resolve to a user identity is allowed
   outright. The comment calls this "unauthenticated service-to-service
   calls", but nothing in the code distinguishes a real internal service
   call from a request that simply carries no/invalid credentials.
2. The final fallback `return { result: AuthorizeResult.ALLOW };`
   (module.ts:122-123) allows every permission that is not a
   `catalog-entity` resource permission — this covers scaffolder
   (`scaffolder.task.create`, `scaffolder.action.execute`, ...), search
   (`search.read`), catalog non-entity permissions such as
   `catalog.location.create`/`catalog.location.delete` (resource type
   `catalog-location`, NOT caught by `isResourcePermission(..., 'catalog-entity')`
   above it), kubernetes, notifications/signals, and any permission any
   future plugin introduces.

Because the portal is publicly reachable (per the issue), both gaps mean the
permission framework is close to a no-op outside of catalog entity reads:
an anonymous caller can trigger scaffolder task creation or register a new
catalog location, and any newly added permission is allowed by default
unless a developer remembers to special-case it here.

## User stories
- AS a platform operator I WANT unauthenticated/unresolvable requests denied
  by default SO THAT the portal cannot be driven anonymously.
- AS a platform operator I WANT only a small, explicit, reviewed set of
  service subjects to bypass the "no user" denial SO THAT legitimate
  internal plugin-to-plugin calls keep working without reopening the
  original hole.
- AS a logged-in team member I WANT catalog, scaffolder, search, and the
  custom plugins I already use to keep working exactly as before SO THAT
  this security fix causes no regression in daily portal use.
- AS a maintainer I WANT non-catalog permissions decided explicitly
  (allow-by-name or deny) instead of a blanket ALLOW SO THAT adding a new
  plugin/permission in the future requires a conscious decision, not a
  silent opt-in.
- AS a maintainer I WANT unit tests for the policy SO THAT this class of
  regression (fail-open defaults) is caught before it reaches production.

## Acceptance criteria (EARS)
- WHEN `handle()` is invoked with no resolvable `user` and the request is
  not from an allowlisted service subject THE SYSTEM SHALL return
  `{ result: AuthorizeResult.DENY }`.
- WHEN `handle()` is invoked with no resolvable `user` and the request
  matches an entry in the explicit service-subject allowlist THE SYSTEM
  SHALL return `{ result: AuthorizeResult.ALLOW }` for that request.
- WHEN `handle()` is invoked for a permission that is not a `catalog-entity`
  resource permission AND is not in the explicit allow set THE SYSTEM SHALL
  return `{ result: AuthorizeResult.DENY }`.
- WHEN `handle()` is invoked for a permission in the explicit allow set
  (e.g. the scaffolder and search permissions the portal UI depends on)
  THE SYSTEM SHALL return the same decision it returns today (ALLOW, or the
  existing viewer-role scaffolder DENY where applicable).
- WHILE a request carries a resolvable `user` with
  `group:default/admins-owners` ownership THE SYSTEM SHALL continue to
  ALLOW all permissions, unchanged from current behavior.
- WHILE a request carries a resolvable `user` with a viewer marker group
  (`group:default/viewer-*`) THE SYSTEM SHALL continue to DENY
  `scaffolder.*` permissions, unchanged from current behavior.
- WHILE a request is a `catalog-entity` resource permission for a
  resolvable, non-admin user THE SYSTEM SHALL continue to return the
  existing conditional decision (group/user/system/component/template
  ownership filtering), unchanged from current behavior.
- IF a new non-catalog permission is introduced by a future plugin and is
  not added to the explicit allow set THEN THE SYSTEM SHALL deny it rather
  than silently allowing it.
- WHEN the module's test suite runs THE SYSTEM SHALL verify: anonymous/no-user
  denial, allowlisted-service-subject allow, admin-owner allow, viewer
  scaffolder denial, member catalog-entity conditional decision, and
  non-catalog-permission deny/allow-by-name behavior.

## Out of scope
- `vault-secrets-backend` viewer exposure — tracked as a separate issue per
  the issue body.
- Changes to how `tenant-backend`, `vault-secrets-backend`,
  `custom-domains-backend`, `github-app-connect-backend`,
  `resource-usage-backend`, `oidc-provider-backend`, and
  `proposals-backend` authenticate/authorize their own HTTP routes — those
  plugins gate access via `httpAuth`/`credentials` in their own routers,
  not via `PermissionPolicy.handle()`, and are unaffected by this change
  (confirmed: none of them call `definePermission`/`createPermission` or
  route through the permission framework).
- Changing the catalog-entity conditional-decision logic itself (group,
  user, system, component, template filtering) — out of scope, kept as-is.
- Building a UI/admin surface for managing the allowlist — it is a small
  static list maintained in code/config, not a runtime-configurable feature,
  for this proposal.

## Open questions
- The exact shape of `PolicyQuery`/`PolicyQueryUser` from
  `@backstage/plugin-permission-node@^0.11.0` cannot be verified in this
  read-only clone (no `node_modules` installed, so the installed `.d.ts`
  files are not available to read). Whether a service-to-service caller
  ever actually reaches `handle()` with `user === undefined` and, if so,
  what information distinguishes *which* service made the call
  (`credentials.principal.subject`, request headers, or nothing at all) is
  unverified. Resolution used for this proposal: implement the allowlist
  check defensively against whatever the installed permission-node
  version's `PolicyQuery` exposes for the caller's principal, and if the
  installed type genuinely exposes no distinguishing information for
  service calls, treat the allowlist as effectively empty (deny all `!user`
  requests) rather than guessing — the implementer must confirm this
  against `node_modules/@backstage/plugin-permission-node/dist/*.d.ts` once
  dependencies are installed, per Task 1 in tasks.md. Denying all `!user`
  requests until a real internal service call is observed failing is safe
  by construction (it can only be too strict, never too permissive).
- The exact set of non-catalog permission names the portal's wired plugins
  emit (`@backstage/plugin-scaffolder-backend`,
  `@backstage/plugin-search-backend`, `@backstage/plugin-kubernetes-backend`,
  `@backstage/plugin-notifications-backend`,
  `@backstage/plugin-signals-backend`, `@backstage/plugin-techdocs-backend`)
  cannot be enumerated from source alone in this clone for the same reason
  (no installed `node_modules`, and none of these plugins vendor their
  permission constants into this repo). Resolution used for this proposal:
  ship an allow set seeded with the well-known Backstage permission names
  that correspond to features this portal's frontend actually exercises
  (scaffolder task creation/read/cancel, scaffolder action/template
  parameter read, search read), and require the implementer to run
  `grep -rn "definePermission" node_modules/@backstage/plugin-*-common/dist`
  after `yarn install` to confirm exact names/typos before merging, plus
  watch backend logs for unexpected DENYs during a staging soak (see
  tasks.md Task 5) to catch anything missed. This is deny-by-default with a
  documented catch-up path, matching the issue's "enumerate from live
  plugin usage" instruction as closely as static analysis allows.
- Whether `catalog.location.*` permissions (currently blanket-ALLOWed
  because they are resource type `catalog-location`, not `catalog-entity`)
  should be allowed for admins only, or denied outright for everyone since
  no UI flow appears to call them. Resolution used: deny by default for
  non-admins (admins already ALLOW-all via the `admins-owners` branch
  earlier in `handle()`), consistent with "deny-by-default, allow only what
  the portal actually uses."
