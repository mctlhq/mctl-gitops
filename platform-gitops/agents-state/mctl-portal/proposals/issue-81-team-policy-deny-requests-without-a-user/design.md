# Design: issue-81-team-policy-deny-requests-without-a-user

## Current state

`plugins/permission-backend-module-team-policy/src/module.ts` defines
`TeamBasedPermissionPolicy` and wires it via `createBackendModule` into the
`policy` extension point of `@backstage/plugin-permission-backend`
(`plugins/permission-backend-module-team-policy/src/module.ts:130-143`). It
is registered in `packages/backend/src/index.ts` right after
`@backstage/plugin-permission-backend`, and it is the only permission policy
in the app, so every permission check performed anywhere in the backend
(catalog, scaffolder, search, kubernetes, notifications, signals, techdocs)
flows through its single `handle()` method.

`handle()` today (module.ts:39-124):
1. `if (!user) return ALLOW` — the fail-open the issue targets. `user` is
   the resolved `PolicyQueryUser` (comment says "Allow unauthenticated
   service-to-service calls", but there is no check of *which* service or
   any credential at all — every request that fails to resolve a user
   identity takes this branch).
2. `admins-owners` ownership → ALLOW everything (kept, correct, and already
   scoped to the *-owners marker group per the comment at module.ts:24-26,
   deliberately narrower than the general `admins` group which also
   contains developer/viewer members).
3. Viewer role (`group:default/viewer-*` in `ownershipEntityRefs`) +
   `scaffolder.*` permission name → DENY (kept, correct).
4. `isResourcePermission(request.permission, 'catalog-entity')` → returns a
   conditional decision built from `catalogConditions` filtering by
   ownership (kept, correct, and the part of this module with the most
   logic — group/user/system/component/template rules at module.ts:76-118).
5. Fallback: `return ALLOW` — the second fail-open the issue targets. This
   catches every permission that is neither caught by step 1-3 nor a
   `catalog-entity` resource permission: scaffolder permissions for
   non-viewers, search, kubernetes, notifications, signals, techdocs, and
   critically `catalog-location` resource permissions (`catalog.location.*`
   — a *different* resource type than `catalog-entity`, so it is NOT
   filtered by step 4 and falls through here today).

There are no tests for this module (`find plugins -name "*.test.ts"` shows
test files for every other backend plugin — `custom-domains-backend`,
`tenant-backend`, `vault-secrets-backend`, `github-app-connect-backend`,
`oidc-provider-backend`, `proposals-backend` — but none for
`permission-backend-module-team-policy`). Notably,
`plugins/custom-domains-backend/src/plugin.test.ts` is a regression test for
an almost identical class of bug (accidental unauthenticated access to
`/domains*`), which sets a precedent in this codebase for writing a small,
targeted regression test per closed fail-open bug rather than broad
coverage.

None of the eight other custom backend plugins listed in `CLAUDE.md`
(`tenant-backend`, `vault-secrets-backend`, `custom-domains-backend`,
`github-app-connect-backend`, `resource-usage-backend`,
`oidc-provider-backend`, `argo-workflows-backend`) call
`definePermission`/`createPermission` or otherwise register permissions
with the framework — they gate their own HTTP routes directly via
`HttpAuthService`/`credentials` in their own routers (confirmed by grep for
`httpAuth|credentials` across `plugins/`). So this policy module's
non-catalog fallback only affects permissions from Backstage's own core
plugins wired in `packages/backend/src/index.ts`: scaffolder, search,
catalog (non-entity), kubernetes, notifications, signals, techdocs, proxy,
app-backend.

## Proposed solution

Restructure `TeamBasedPermissionPolicy.handle()` around the same shape it
has today (early-return branches), replacing the two fail-open branches
with explicit, narrow allow paths and a deny-by-default posture. No changes
to the module's public surface (`teamPolicyModule` export, registration in
`packages/backend/src/index.ts`) are needed — this is contained entirely
inside `module.ts`.

1. **No-user branch.** Replace the unconditional ALLOW with a call to a new
   pure helper, `isAllowlistedServiceRequest(request, user)`, defined in the
   same file (or a new `serviceAllowlist.ts` in the same plugin, whichever
   keeps `module.ts` readable — prefer a separate file since it needs its
   own focused tests). This helper holds a small, explicitly named constant
   list of allowed service-subject/permission-name pairs (e.g. a
   `Set<string>` of permission names, or subject identifiers, depending on
   what the installed `@backstage/plugin-permission-node` version's
   `PolicyQuery`/`PolicyQueryUser` actually exposes for a credential-less
   caller — see Open Questions in requirements.md; this must be confirmed
   against the installed `.d.ts` before finalizing the check). If the
   request matches, ALLOW; otherwise DENY. Starting allowlist: empty (or
   populated only if the implementer's staging soak in tasks.md Task 5
   surfaces a genuine internal service call that needs it) — an empty
   allowlist that only denies is strictly safer than guessing at
   plugin-to-plugin subjects that may not exist in this deployment at all.
2. **Keep steps 2-4 (admins-owners ALLOW, viewer scaffolder DENY,
   catalog-entity conditional decision) unchanged.** These already
   implement the deny/allow split correctly and are exercised by real portal
   usage today; the issue's acceptance criteria explicitly require this
   behavior to remain unchanged.
3. **Non-catalog fallback.** Replace the trailing `return ALLOW` with an
   explicit allow-set check: a new constant, e.g.
   `ALLOWED_NON_CATALOG_PERMISSIONS: ReadonlySet<string>`, listing the exact
   permission names the portal's wired plugins require for normal operation
   (seeded per requirements.md's Open Questions with the scaffolder
   task/action/template permissions and `search.read`; the implementer
   confirms/extends this against installed `node_modules` type
   declarations and staging logs before merging). If
   `request.permission.name` is in the set, return the same ALLOW decision
   as today; otherwise return DENY. Also extend step 4's resource-permission
   handling (or add a sibling `isResourcePermission(request.permission,
   'catalog-location')` branch) so `catalog.location.*` gets an explicit,
   reasoned decision (proposed: DENY for non-admins, consistent with
   "Domain and Location are intentionally omitted -> DENY for non-admins"
   already stated in the existing catalog-entity comment at module.ts:117)
   instead of silently falling through the old blanket ALLOW.
4. **Logging for the catch-up path.** Because the allow set is seeded from
   static analysis rather than a live-traffic capture (no running instance
   available to this proposal), add a single `logger.warn` (the module
   already receives `logger` via `deps` in `register()`, module.ts:134-141;
   thread it into the policy instance's constructor) each time the
   non-catalog fallback denies a permission, including
   `request.permission.name`. This turns "we might have missed a
   permission" into an observable, actionable signal in the existing
   `mctl_get_service_logs`/Loki pipeline during the staging soak
   (tasks.md Task 5), rather than a silent, hard-to-diagnose UX break.
5. **Tests.** Add
   `plugins/permission-backend-module-team-policy/src/module.test.ts`
   following the existing house style seen in
   `plugins/custom-domains-backend/src/plugin.test.ts` (plain `describe`/`it`,
   no heavy mocking framework beyond `jest.fn()`), constructing
   `TeamBasedPermissionPolicy` directly and calling `.handle()` with hand-built
   `PolicyQuery`/`PolicyQueryUser`-shaped objects (using
   `createPermission`/existing permission objects, or minimal fakes typed
   against the real `Permission`/`ResourcePermission` interfaces from
   `@backstage/plugin-permission-common`, which is already a dependency).
   Cover: no-user → DENY; allowlisted service subject (if the allowlist ends
   up non-empty; otherwise a case proving DENY-when-empty is correct) →
   ALLOW; admin-owner → ALLOW-all; viewer + `scaffolder.task.create` →
   DENY; non-viewer member + `catalog-entity` permission → conditional
   decision returned (matching today's behavior, so this also acts as a
   regression guard on step 4); member + unrecognized non-catalog
   permission → DENY; member + an explicitly allow-set permission (e.g.
   `search.read`) → ALLOW.

## Alternatives

1. **Deny everything with no user, no allowlist at all.** Simpler, and
   arguably what the issue's evidence section alone would justify. Rejected
   because the issue explicitly asks for "a small explicit allowlist of
   plugin-to-plugin service subjects that legitimately have no user" —
   removing that entirely risks breaking a real internal call path this
   proposal cannot observe from a static read-only clone. Keeping the hook
   (even if it starts empty) lets the implementer add exactly one
   allowlist entry, with a comment and a test, if the staging soak proves
   one is needed — much safer than either guessing entries now or having no
   mechanism later.
2. **Allowlist entire plugins (by `pluginId`) instead of permission names
   for the non-catalog fallback.** E.g. "any permission from the scaffolder
   plugin is allowed." Rejected: `request.permission` does not carry a
   `pluginId` field in `@backstage/plugin-permission-common`'s `Permission`
   type as consumed here (the module only ever reads `.name` and resource
   type), and even if it did, this would reintroduce the same fail-open
   shape at plugin granularity instead of permission granularity — a new
   sensitive permission added to an already-allowed plugin (e.g. scaffolder
   gaining a "delete all tasks" permission) would be silently allowed
   again. Per-permission-name allow is more work to maintain but matches
   the issue's explicit ask ("explicit per-permission decisions").
3. **Move the allow set into `app-config.yaml`/`app-config.production.yaml`
   as configuration instead of a code constant.** Considered because the
   repo already has a config-driven pattern for environment-specific
   values. Rejected for this proposal: a security-relevant allow-list
   changing without a code review (a config-only change could bypass the
   scrutiny a PR touching `module.ts` gets) is a worse failure mode than
   the small inconvenience of a code change + redeploy to adjust it. Can be
   revisited later if the allow set needs to differ across environments,
   which nothing in the issue or the current single-environment deployment
   pattern (one `packages/backend/src/index.ts`) suggests today.

## Platform impact

- **Migrations:** none — no data model, storage, or API contract changes.
  Purely a change to in-process authorization decisions.
- **Backward compatibility:** intentionally behavior-changing for exactly
  the two fail-open paths described in the issue. Acceptance criteria in
  requirements.md pin down that admin, viewer, and catalog-entity behavior
  for logged-in members is unchanged. Any anonymous or credential-less
  caller that was previously silently allowed (there is no way to know from
  this static clone whether any currently exists) will start being denied;
  this is the intended fix, not a regression, but it is the one behavior
  change worth calling out loudly to a human reviewer before merge.
- **Resource impact:** negligible — one extra `Set.has()`/array check per
  permission decision, already an in-memory, per-request hot path with no
  new I/O.
- **Risks + mitigations:**
  - *Risk:* the non-catalog allow set is incomplete, silently breaking a
    portal feature relied upon by logged-in members (violates the "Portal
    UX for logged-in members unchanged" acceptance criterion).
    *Mitigation:* the `logger.warn` added in this design turns silent
    breakage into a visible, greppable log line
    (`mctl_get_service_logs(team, "permission-backend"...)` or the
    Backstage backend service, whichever hosts it) during a staging soak
    before this ships to the primary environment; tasks.md includes an
    explicit manual-soak task gated on this before merge sign-off.
  - *Risk:* the "service subject allowlist" is added speculatively without
    a real service call to test it against, encoding an untested,
    unverifiable security control. *Mitigation:* start the allowlist empty
    (deny-by-default with no exceptions) per Alternative 1 above; only add
    an entry, with a test, if the soak surfaces a genuine failure.
  - *Risk:* `catalog.location.*` moving from ALLOW to DENY-for-non-admins
    breaks a scaffolder template or onboarding flow that registers catalog
    locations on behalf of a non-admin member. *Mitigation:* covered by the
    same staging soak; if it surfaces, the fix is a one-line addition to
    the explicit allow set (or a conditional decision scoped to the user's
    own group, mirroring the catalog-entity Template branch pattern already
    in the file at module.ts:107-112), not a design change.
