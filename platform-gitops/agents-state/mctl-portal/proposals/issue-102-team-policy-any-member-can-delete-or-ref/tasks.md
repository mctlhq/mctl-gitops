# Tasks: issue-102-team-policy-any-member-can-delete-or-ref

- [ ] 1. In `plugins/permission-backend-module-team-policy/src/module.ts`,
      compute `const action = request.permission.attributes?.action;` and
      `const isReadAction = action === 'read';` once in `handle()`, right
      after the ownership lookup (module.ts:116) and before the viewer gate
      (module.ts:125) — DoD: both values are computed exactly once per
      request and are in scope for both the viewer gate and the
      catalog-entity branch; no behavior change yet (values unused until
      tasks 2-3 wire them in).

- [ ] 2. Extend the viewer gate (module.ts:125-127) so that, in addition to
      denying `scaffolder.*` permission names, it denies any
      `catalog-entity` resource permission whose action is not `read` for
      viewer-role users, per the design's step 2 — DoD: a viewer requesting
      `catalog.entity.delete` or `catalog.entity.refresh` on any entity
      (including one their own team owns) gets `{ result:
      AuthorizeResult.DENY }`, evaluated before reaching the catalog-entity
      `anyOf` branch; a viewer requesting `catalog.entity.read` is
      unaffected (still falls through to the conditional branch as today).

- [ ] 3. (depends on 1) In the catalog-entity branch (module.ts:136-187),
      make inclusion of the global-admin-template arm (currently
      module.ts:169-176) conditional on `isReadAction`, per the design's
      step 3, while leaving the other five arms (Group, User, System,
      Component/API/Resource, group-owned Template) unconditional — DoD:
      for `catalog.entity.delete` and `catalog.entity.refresh` from a
      non-viewer, non-admin member, the returned conditional decision's
      `anyOf` does not contain the global-admin-template arm (an entity
      that matches only that arm is therefore denied by the policy engine);
      for `catalog.entity.read` the `anyOf` is unchanged from today
      (admin-template arm present); team-owned-entity behavior for
      delete/refresh is unchanged for all five other arms.

- [ ] 4. (depends on 2, 3) Update the doc comment block above the
      catalog-entity branch (module.ts:129-135) to state that the
      global-admin-template arm is read-only-gated, and update the
      `isViewerRole`/viewer-gate area comment to describe the broadened
      scope — DoD: comments accurately describe the new behavior, so a
      future reader does not reintroduce the bug by copying the old
      "any action" assumption.

- [ ] 5. (depends on 1, 2, 3) Add regression tests to
      `plugins/permission-backend-module-team-policy/src/module.test.ts`
      per the Tests section below — DoD: all new tests pass against the
      fixed code and are confirmed (by temporarily reverting tasks 2-3, or
      by inspection matching the issue's reasoning) to fail against
      today's pre-fix code, satisfying the issue's "validate by mutation"
      request.

- [ ] 6. Run the plugin's test suite and lint for
      `permission-backend-module-team-policy`
      (`yarn workspace @internal/plugin-permission-backend-module-team-policy test`
      and `... lint`, or the repo's equivalent script — confirm exact
      script names via `package.json`/`backstage.json` in that plugin
      directory before running) — DoD: full suite green, no new lint
      errors, no unrelated test regressions.

## Tests

- [ ] T1. Non-viewer, non-admin member + `catalog.entity.delete` on an
      entity matching only the global-admin-template shape: assert the
      returned decision's `conditions` (or the `anyOf` passed to
      `createCatalogConditionalDecision`) does NOT include an arm matching
      `isEntityOwner({ claims: ['group:default/admins'] })` combined with
      `isEntityKind({ kinds: ['Template'] })` — i.e. the admin-template arm
      is absent. (If asserting on the exact decision shape is impractical
      given how `createCatalogConditionalDecision` serializes conditions,
      assert equivalently by checking the decision's condition tree does
      not permit an entity that satisfies *only* the admin-template
      predicate, per the issue's own suggested assertion: "a conditional
      decision without the global-admin-template arm for
      `catalog.entity.delete`".)
- [ ] T2. Same as T1 but for `catalog.entity.refresh` (action `update`).
- [ ] T3. Non-viewer, non-admin member + `catalog.entity.read`: assert the
      admin-template arm IS present (no regression to template
      browse/run) — i.e. same shape as the existing test at
      module.test.ts:81-97, extended to check the arm's presence rather
      than only `decision.result === CONDITIONAL`.
- [ ] T4. Viewer-role member (`group:default/viewer-<tenant>` +
      `group:default/<tenant>` in ownership, matching the `fakeUser`
      pattern already used in module.test.ts) + `catalog.entity.delete`:
      assert `{ result: AuthorizeResult.DENY }`.
- [ ] T5. Viewer-role member + `catalog.entity.refresh`: assert
      `{ result: AuthorizeResult.DENY }`.
- [ ] T6. Viewer-role member + `catalog.entity.read`: assert
      `decision.result === AuthorizeResult.CONDITIONAL` (unchanged —
      viewers must remain able to read/browse the catalog).
- [ ] T7. Non-viewer, non-admin member + `catalog.entity.delete` on an
      entity owned by the user's own team group (i.e. matching e.g. the
      Component/API/Resource arm): assert the conditional decision still
      permits it (no regression to the explicitly out-of-scope
      team-owned-entity behavior) — assert the relevant team-scoped arm is
      still present in the `anyOf`.
- [ ] T8. Admin-owner user (`group:default/admins-owners`) +
      `catalog.entity.delete` on a global admin template: assert
      `{ result: AuthorizeResult.ALLOW }` (unchanged short-circuit,
      unaffected by this fix).

## Rollback

This is a single-file, dependency-free code change to
`plugins/permission-backend-module-team-policy/src/module.ts` (plus its
test file). To roll back:

1. Revert the commit/PR that lands tasks 1-4 (a plain `git revert`, since
   the change has no accompanying data migration, GitOps state, or schema
   change to unwind).
2. Redeploy the portal backend with the reverted image — the permission
   policy is re-registered on backend startup
   (`teamPolicyModule.register()`), so no additional cache-busting or
   restart-order concerns beyond a normal service redeploy.
3. No feature flag is introduced by this change, so there is no flag to
   toggle as an alternative to reverting — a straight revert is the
   rollback path.
4. If rollback is needed only for the viewer-gate broadening (task 2) but
   the admin-template gating (task 3) should stay, or vice versa, the two
   changes are independent enough to revert selectively by hand-editing
   `handle()` back to the pre-fix branch for just that part, since they
   touch different, non-overlapping lines of the same function.
