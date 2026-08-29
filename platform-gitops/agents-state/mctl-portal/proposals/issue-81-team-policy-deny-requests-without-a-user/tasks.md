# Tasks: issue-81-team-policy-deny-requests-without-a-user

- [ ] 1. Confirm the installed `@backstage/plugin-permission-node@^0.11.0`
      `PolicyQuery`/`PolicyQueryUser` shape (run `yarn install`, then read
      `node_modules/@backstage/plugin-permission-node/dist/*.d.ts`) to
      determine what, if anything, distinguishes a genuine plugin-to-plugin
      service call from a plain unauthenticated request when `user` is
      undefined in `handle()`. — DoD: a short comment in `module.ts` (or the
      new allowlist file) states what was found and cites the type/field
      relied on, or explicitly states "no distinguishing information is
      exposed; the allowlist is a no-op today" if that's the case.

- [ ] 2. Implement the no-user branch: replace
      `if (!user) return { result: AuthorizeResult.ALLOW }` in
      `plugins/permission-backend-module-team-policy/src/module.ts:43-46`
      with a call to a new `isAllowlistedServiceRequest(request, user)`
      helper backed by an explicit, initially-empty (or minimally seeded,
      per Task 1's findings) allow list; DENY otherwise. (depends on 1) —
      DoD: no-user requests are denied unless they match the allowlist;
      admin/viewer/catalog-entity branches below it are unreached/unaffected
      for this case since they all require `user` to be truthy already, so
      ordering does not change.

- [ ] 3. Implement the non-catalog fallback: replace the trailing
      `return { result: AuthorizeResult.ALLOW }` at
      `plugins/permission-backend-module-team-policy/src/module.ts:122-123`
      with an explicit allow-set check against
      `ALLOWED_NON_CATALOG_PERMISSIONS` (seed with the scaffolder
      task/action/template-parameter/template-step permission names and
      `search.read`; verify exact names via
      `grep -rn "definePermission" node_modules/@backstage/plugin-*-common/dist`
      after `yarn install`), returning ALLOW for members whose permission is
      in the set and DENY otherwise. Also add an explicit
      `catalog-location` resource-permission branch (DENY for non-admins,
      consistent with the existing Domain/Location comment at
      module.ts:117) so it no longer falls through to the fallback.
      (depends on 1, independent of 2) — DoD: `catalog.location.*` and any
      permission name not in the allow set return DENY for non-admin
      members; permissions in the allow set return the same ALLOW decision
      as before this change.

- [ ] 4. Add `logger.warn` for every DENY returned by the new non-catalog
      fallback and the new no-user branch, including
      `request.permission.name` and (for the no-user case) whatever
      identifying detail Task 1 determined is available. Thread `logger`
      into the `TeamBasedPermissionPolicy` constructor from
      `register()`/`init()` (module.ts:130-141), where it is already
      available via `deps: { logger: coreServices.logger }`. (depends on 2,
      3) — DoD: constructing `TeamBasedPermissionPolicy` requires a logger;
      `packages/backend/src/index.ts` needs no changes since the module is
      imported, not constructed there directly.

- [ ] 5. Write
      `plugins/permission-backend-module-team-policy/src/module.test.ts`
      covering: no-user → DENY; allowlisted service subject → ALLOW (or, if
      the allowlist is empty per Task 1, a test asserting DENY-when-empty
      plus a code comment explaining why that's correct); admin-owner user
      → ALLOW for an arbitrary permission; viewer user +
      `scaffolder.task.create` → DENY; non-viewer member +
      `catalog-entity` permission → conditional decision object returned
      (matching pre-existing behavior, guards against regressions in the
      untouched branch); member + permission in
      `ALLOWED_NON_CATALOG_PERMISSIONS` (e.g. `search.read`) → ALLOW; member
      + arbitrary unrecognized non-catalog permission → DENY; member +
      `catalog.location.create` → DENY. (depends on 2, 3) — DoD:
      `yarn workspace @internal/plugin-permission-backend-module-team-policy test`
      (or the equivalent `backstage-cli package test` invocation) passes,
      and every branch of the rewritten `handle()` has at least one test
      exercising it.

- [ ] 6. Manual staging soak: deploy the changed module to a
      non-production/staging instance of `mctl-portal` (or run the backend
      locally against a copy of production-shaped config) and exercise
      catalog browsing, scaffolder template execution, and search as a
      real logged-in member, while tailing backend logs for the new
      DENY warnings from Task 4. (depends on 2, 3, 4) — DoD: no unexpected
      DENY warnings for actions a logged-in member performed during the
      soak; any that do appear are triaged into either an
      `ALLOWED_NON_CATALOG_PERMISSIONS` addition or a documented,
      intentional new restriction, before merging.

## Tests
- [ ] T1. `module.test.ts`: no `user` argument -> `AuthorizeResult.DENY`.
- [ ] T2. `module.test.ts`: no `user` argument but request matches the
      service allowlist (if non-empty) -> `AuthorizeResult.ALLOW`; if the
      allowlist is empty, assert DENY here instead and keep this as the
      regression guard for "empty allowlist really denies everything".
- [ ] T3. `module.test.ts`: user with `group:default/admins-owners`
      ownership -> `AuthorizeResult.ALLOW` for an arbitrary/unrecognized
      permission name (proves admin bypass still short-circuits before the
      new deny-by-default logic).
- [ ] T4. `module.test.ts`: user with `group:default/viewer-<team>`
      ownership + permission name `scaffolder.task.create` ->
      `AuthorizeResult.DENY` (unchanged existing behavior).
- [ ] T5. `module.test.ts`: non-viewer member + `catalog-entity` resource
      permission -> a conditional decision object is returned (not a plain
      ALLOW/DENY), matching current behavior.
- [ ] T6. `module.test.ts`: non-viewer member + permission name in
      `ALLOWED_NON_CATALOG_PERMISSIONS` (e.g. `search.read`) ->
      `AuthorizeResult.ALLOW`.
- [ ] T7. `module.test.ts`: non-viewer member + an arbitrary permission name
      not in `ALLOWED_NON_CATALOG_PERMISSIONS` and not a `catalog-entity`
      resource permission -> `AuthorizeResult.DENY`.
- [ ] T8. `module.test.ts`: non-viewer member + `catalog-location` resource
      permission (e.g. `catalog.location.create`) -> `AuthorizeResult.DENY`.

## Rollback
This is a single self-contained change to
`plugins/permission-backend-module-team-policy/src/module.ts` (plus a new
test file and possibly a small new allowlist/constants file in the same
plugin), deployed as part of the normal `mctl-portal` backend image/deploy
pipeline. If the staging soak or a post-deploy incident shows unexpected
DENYs breaking real portal usage:
1. Immediate mitigation: `mctl_rollback_service` to the previously deployed
   image tag for the `mctl-portal` backend service (per
   `mctl_get_service_config` to find the prior tag), which reverts to the
   old fail-open policy while a targeted fix is prepared. This is a
   deliberate, temporary step back to fail-open, not a permanent
   acceptance of it, so re-apply the fix (with the missing permission added
   to the allow set) as soon as possible.
2. Preferred mitigation if the gap is narrow: add the missing permission
   name to `ALLOWED_NON_CATALOG_PERMISSIONS` (or the service allowlist) and
   redeploy, rather than a full rollback, since the log line from Task 4
   should identify exactly which permission was denied.
3. No data migration or persisted state is touched by this change, so
   rollback is a pure code/image revert with no cleanup step required.

## Operator decisions (approve with rewritten scope, 2026-08-29)

- Task 1 REWRITTEN — the open question is answered, do not build the
  service-subject allowlist: ServerPermissionClient (permission-node
  0.11.0) decides for service principals locally and never reaches this
  policy, and permission-backend forwards only user/none principals. A
  request with !user here is therefore always an anonymous caller —
  implement an UNCONDITIONAL DENY with a logger.warn naming the
  permission. Drop test T2's allowlist premise. This cannot break the
  external:mctl-api custom-domains caller (it never traverses the
  permission framework).
- Task 3 corrections: there is NO 'catalog-location' resource type
  (catalog.location.* are basic permissions — the isResourcePermission
  branch is unreachable, remove it) and NO 'search.read' permission
  (search authorizes per-document via catalog.entity.read — do not seed
  it).
- Seed ALLOWED_NON_CATALOG_PERMISSIONS with: the six scaffolder
  permissions (scaffolder.action.execute, scaffolder.task.create,
  scaffolder.task.read, scaffolder.task.cancel,
  scaffolder.template.parameter.read, scaffolder.template.step.read)
  plus kubernetes.resources.read and kubernetes.clusters.read (member
  EntityPage Kubernetes tab depends on them). Add kubernetes.proxy only
  if it shows up in warn logs during soak.
- Soak (Task 6) MUST cover: a member opening the Kubernetes tab, running
  a scaffolder template, the scaffolder tasks page, search, and
  notifications.
- Land order: this PR lands LAST of the three portal proposals, after
  #83 and #82 are merged, with DENY warn-logging enabled from the start.
