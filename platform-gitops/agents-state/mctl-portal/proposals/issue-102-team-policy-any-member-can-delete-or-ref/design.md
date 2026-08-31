# Design: issue-102-team-policy-any-member-can-delete-or-ref

## Current state

`plugins/permission-backend-module-team-policy/src/module.ts` implements
`TeamBasedPermissionPolicy.handle()`, the single `PermissionPolicy` installed
for the `permission` backend plugin (registered in
`teamPolicyModule.register()` at the bottom of the file).

Flow today, in order:

1. No user -> DENY (module.ts:109-114).
2. `group:default/admins-owners` in ownership -> ALLOW everything
   (module.ts:120-122).
3. Viewer role (`isViewerRole`, matches `group:default/viewer-*` marker
   group) AND permission name starts with `scaffolder.` -> DENY
   (module.ts:125-127). This is the only viewer-specific gate; it is scoped
   to scaffolder by name prefix, not to catalog-entity actions.
4. `isResourcePermission(request.permission, 'catalog-entity')` -> always
   returns `createCatalogConditionalDecision(request.permission, { anyOf: [...] })`
   with six arms (module.ts:136-187), covering Group, User, System,
   Component/API/Resource, global-admin Template, and group-owned Template.
   This branch is reached identically for `catalog.entity.read` (action
   `read`), `catalog.entity.delete` (action `delete`), and
   `catalog.entity.refresh` (action `update`) — confirmed by the issue body
   and consistent with upstream Backstage's `catalog-common` permission
   definitions, all four of which set `resourceType:
   RESOURCE_TYPE_CATALOG_ENTITY`.
5. Otherwise, allow only names in `ALLOWED_NON_CATALOG_PERMISSIONS`
   (module.ts:86-95, 195-197), deny everything else with a warn log.

The global-admin-template arm (module.ts:169-176) matches `Template`
entities owned by `group:default/admins` without the `mctl.me/admin-only`
annotation. It is documented (module.ts:135) as existing "so members can see
and run" shared templates — i.e., intended for read/execute-adjacent access,
not for mutation of the template's catalog registration. Because step 4
ignores the action, this same arm authorizes `catalog.entity.delete` and
`catalog.entity.refresh` on those templates for any non-admin member,
letting a member unregister or force-refresh a shared platform template
(`DELETE /api/catalog/entities/by-uid/<uid>`, per the issue's failure
scenario). `EntityPage.tsx:74` (`disableUnregister: isAdmin ? false :
'hidden'`) only controls a frontend menu item and is not consulted by the
backend policy, so it provides no real protection.

`module.test.ts` currently has one test asserting
`catalog.entity.read` returns `AuthorizeResult.CONDITIONAL`
(lines 81-97) but nothing that inspects *which* arms are present in the
decision, and nothing that exercises `catalog.entity.delete` /
`catalog.entity.refresh`, or a viewer against a non-scaffolder mutating
permission.

## Proposed solution

Modify `TeamBasedPermissionPolicy.handle()` in
`plugins/permission-backend-module-team-policy/src/module.ts`:

1. **Compute the action once**, immediately after the ownership lookup:

   ```ts
   const action = request.permission.attributes?.action;
   const isReadAction = action === 'read';
   ```

   Reuse this for both the viewer gate and the catalog-entity branch so the
   two enforcement points cannot drift apart.

2. **Broaden the viewer gate** (replacing the `scaffolder.`-prefix-only
   check at module.ts:125-127) to also deny any catalog-entity resource
   permission whose action is not read:

   ```ts
   if (isViewerRole(ownership)) {
     if (request.permission.name.startsWith('scaffolder.')) {
       return { result: AuthorizeResult.DENY };
     }
     if (isResourcePermission(request.permission, 'catalog-entity') && !isReadAction) {
       return { result: AuthorizeResult.DENY };
     }
   }
   ```

   This is evaluated before the catalog-entity conditional branch, so a
   viewer never reaches the `anyOf` assembly for a mutating action — it is
   an outright DENY, per the issue's fix direction ("deny outright for
   viewers whenever `attributes?.action !== 'read'`").

3. **Gate the global-admin-template arm on the action** inside the
   catalog-entity branch (module.ts:136-187): keep the `anyOf` array
   assembly as-is for the five team-scoped arms (Group, User, System,
   Component/API/Resource, group-owned Template — these are unaffected,
   per the "out of scope" decision to leave team-owned-entity mutation
   behavior unchanged), and conditionally include the global-admin-template
   arm only when `isReadAction`:

   ```ts
   const arms = [
     /* Group */ { ... },
     /* User */ { ... },
     /* System */ { ... },
     /* Component/API/Resource */ { ... },
     /* Group-owned Template */ { ... },
   ];
   if (isReadAction) {
     arms.push({
       allOf: [
         catalogConditions.isEntityKind({ kinds: ['Template'] }),
         catalogConditions.isEntityOwner({ claims: ['group:default/admins'] }),
         { not: catalogConditions.hasAnnotation({ annotation: 'mctl.me/admin-only' }) },
       ],
     });
   }
   return createCatalogConditionalDecision(request.permission, { anyOf: arms });
   ```

   (Ordering/exact array construction is an implementation detail for the
   implementer; the requirement is that the global-admin-template arm is
   present in the `anyOf` if and only if the action is `read`.)

This keeps the branch structure of the file intact (no new top-level
control flow, no new marker groups, no changes to `isViewerRole` or
`ALLOWED_NON_CATALOG_PERMISSIONS`) and localizes the fix to the two places
the issue identifies: the viewer gate and the catalog-entity `anyOf`
assembly. Using `action !== 'read'` (deny-list of one safe value) rather
than enumerating `'delete'`/`'update'` matches the issue's own fix
direction and is safe-by-default against any other non-read action
upstream Backstage might add to `catalog-entity` in the future (e.g. a
hypothetical `catalog.entity.move`) — it would automatically lose the
admin-template arm and be denied for viewers without a code change here.

## Alternatives

1. **Add a new dedicated `catalog.entity.delete`/`.refresh` branch before
   the existing catalog-entity block**, entirely separate from the read
   path, duplicating the five team-scoped arms and simply omitting the
   admin-template arm. Rejected: duplicates the five unaffected arms
   verbatim, creating two places that must be kept in sync every time a
   team-scoped arm changes (e.g., if a future proposal adds a `Domain` arm
   for reads only, someone would have to remember to mirror it into the
   write branch too, or explicitly decide not to). The chosen approach
   keeps one `anyOf` assembly with one conditional arm, which is the
   smaller diff and the single source of truth the issue's own fix
   direction implies ("branch on the permission's action before assembling
   the conditions").

2. **Enumerate the specific non-read actions (`'delete'`, `'update'`) to
   deny for viewers and to gate the admin-template arm**, instead of
   checking `!== 'read'`. Rejected: brittle against future upstream
   permissions on `catalog-entity` with actions this codebase hasn't seen
   yet (e.g. Backstage could add a `move` or `bulk-import`-adjacent action);
   an allow-list-of-one (`read`) fails closed for anything unrecognized,
   matching the file's overall stated philosophy of denying by default
   (see the extensive comment at module.ts:39-85 justifying
   `ALLOWED_NON_CATALOG_PERMISSIONS` as an explicit allow-list for the same
   reason).

3. **Revoke non-admin delete/refresh entirely for all catalog-entity kinds**
   (not just the global-admin-template arm), forcing all mutation through
   admins. Rejected as the primary fix: the issue explicitly frames this as
   an open question ("Worth deciding at the same time whether non-admin
   members should be able to delete or refresh any catalog entity,
   including ones their own team owns") rather than a requirement, and
   entities are provider-managed (`TenantCatalogEntityProvider`, GitHub
   discovery) so team-owned deletes are transient/self-healing — changing
   that behavior is a separate, larger decision with its own tradeoffs
   (e.g., a team wanting to force a refresh of its own stale entity) that
   deserves its own proposal rather than being bundled into a P1 security
   fix. Recorded as an open question in requirements.md instead.

## Platform impact

- **Migrations**: none. This is a pure code change to the in-process
  permission policy; no data, schema, or GitOps config changes.
- **Backward compatibility**: no compatible API surface changes. Any
  non-admin member currently relying on being able to delete/refresh a
  *shared admin template* (the escalation itself) loses that ability — this
  is the intended fix, not a regression, since it was never an intended
  grant (module.ts's own comment says the arm exists so members can "see
  and run" templates, not mutate them). Team-owned entity delete/refresh
  and admin-owner behavior are unchanged. Viewers lose the ability to
  delete/refresh entities their own team owns (previously allowed by
  omission) — this is the P2 fix the issue asks for and is a narrowing of
  an already-documented-as-unintended gap ("contradicting the documented
  read-only definition of the role").
- **Resource impact**: negligible — one extra field lookup
  (`request.permission.attributes?.action`) and one extra boolean branch
  per request; no new I/O, no new dependencies.
- **Risks + mitigations**:
  - Risk: gating on `attributes?.action` assumes upstream Backstage
    reliably sets this attribute for all four catalog-entity permissions.
    Mitigation: the issue itself states this is confirmed upstream
    behavior ("`catalog.entity.read` (action `read`), `catalog.entity.delete`
    (action `delete`) and `catalog.entity.refresh` (action `update`)"); add
    a unit test per action name (see tasks.md) so any future upstream
    Backstage upgrade that changes these attributes is caught by CI rather
    than discovered in production.
  - Risk: silently breaking a legitimate current workflow that relies on
    member delete/refresh of shared templates. Mitigation: per the issue,
    this was never an intended capability (the templates are meant to be
    admin-managed, per `mctl.me/admin-only` annotation semantics already in
    the codebase) — no mitigation beyond the fix itself is needed, but the
    task list includes verifying no in-repo caller (frontend or template)
    depends on this path.
  - Risk: fixing the viewer gate too broadly could deny viewers *read*
    access by mistake if the boolean logic is inverted. Mitigation:
    explicit unit tests for both the allow (read) and deny (non-read) case
    for viewers, run to fail against pre-fix code first (mutation testing,
    per the issue's verification request).
