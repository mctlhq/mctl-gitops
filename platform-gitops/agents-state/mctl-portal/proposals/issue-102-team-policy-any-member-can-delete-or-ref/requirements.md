# team-policy: branch catalog-entity conditions on permission action to close a privilege-escalation

## Context

`plugins/permission-backend-module-team-policy/src/module.ts` handles every
`catalog-entity` resource permission (`catalog.entity.read`,
`catalog.entity.delete`, `catalog.entity.refresh`) through a single
`isResourcePermission(request.permission, 'catalog-entity')` branch that
returns the *same* `anyOf` conditional decision regardless of the
permission's action. One arm of that `anyOf` exists to let members see and
run global admin templates (`Template` entities owned by
`group:default/admins` without the `mctl.me/admin-only` annotation). Because
the arm does not check the action, it also grants `delete` and `update`
(refresh) on those same templates. Any authenticated non-admin member can
therefore call `DELETE /api/catalog/entities/by-uid/<uid>` (or the refresh
endpoint) against a shared platform template such as `deploy-component` and
unregister or force-refresh it for every tenant — a P1 privilege escalation,
since only admins are supposed to be able to mutate shared platform
templates. A related but lower-severity issue (P2): the viewer-role carve-out
at module.ts:125 only denies permission names starting with `scaffolder.`,
so a viewer (who is documented as read-only) can still reach
`catalog.entity.delete` / `catalog.entity.refresh` on entities their own team
owns, contradicting the read-only contract of that role.

This is pre-existing behavior untouched by #100 and distinct from #101; it
is filed separately because it is an escalation, not merely an
over-broad grant. The frontend hint at `EntityPage.tsx:74`
(`disableUnregister: isAdmin ? false : 'hidden'`) only hides a menu item and
provides no enforcement — the API is the actual trust boundary and it is
currently open.

## User stories

- AS a platform admin I WANT non-admin members to be unable to delete or
  refresh shared/global admin templates SO THAT the platform's catalog of
  shared scaffolder templates cannot be tampered with by any tenant member.
- AS a platform admin I WANT viewer-role users to be denied any mutating
  catalog-entity action (delete, update/refresh) SO THAT the "read-only"
  viewer role is enforced consistently, not just for scaffolder actions.
- AS a security reviewer I WANT the permission policy to branch on the
  permission's action before assembling catalog-entity conditions SO THAT
  future additions to the `anyOf` list cannot silently leak into
  destructive actions the way the admin-template arm did here.

## Acceptance criteria (EARS)

- WHEN a non-viewer, non-admin member requests `catalog.entity.delete` or
  `catalog.entity.refresh` (action `delete` or `update`) on an entity that
  matches only the global-admin-template arm (kind `Template`, owned by
  `group:default/admins`, without `mctl.me/admin-only`) THE SYSTEM SHALL NOT
  return a conditional decision that allows it via that arm.
- WHEN a non-viewer, non-admin member requests `catalog.entity.read` on the
  same global-admin-template entity THE SYSTEM SHALL continue to return a
  conditional decision permitting read access via the existing
  global-admin-template arm (no regression to template browse/run).
- IF a user carries the viewer marker group (`group:default/viewer-*`) AND
  the requested permission is a `catalog-entity` resource permission whose
  action is not `read` THEN THE SYSTEM SHALL return DENY, regardless of
  which catalog-entity conditional arm would otherwise have matched.
- WHILE evaluating any `catalog-entity` resource permission THE SYSTEM SHALL
  determine the permission's action (`request.permission.attributes?.action`)
  before selecting which `anyOf` arms to include, so that action-specific
  behavior cannot be bypassed by the arm-matching logic.
- WHEN a non-viewer, non-admin member requests `catalog.entity.delete` or
  `catalog.entity.refresh` on Group/User/System/Component/API/Resource/
  group-owned-Template entities owned by their own team group THE SYSTEM
  SHALL preserve today's existing behavior (conditional ALLOW), since the
  issue only asks that the *global-admin-template* arm be read-gated and
  that viewers be fully read-only — it does not ask to revoke a team's
  ability to manage entities their own team owns.
- WHEN an admin-owner user (`group:default/admins-owners`) requests any
  catalog-entity permission THE SYSTEM SHALL continue to ALLOW
  unconditionally (unchanged short-circuit at module.ts:120).

## Out of scope

- Deciding whether non-admin members should be able to delete/refresh
  catalog entities their *own* team owns at all (the issue explicitly
  raises this as a question for later, noting deletes are transient because
  `TenantCatalogEntityProvider` and the GitHub discovery provider
  re-populate entities on the next provider run). This proposal only closes
  the global-admin-template escalation and the viewer read-only gap.
- Changing frontend behavior (`EntityPage.tsx`'s `disableUnregister`) —
  it is cosmetic UI-only and not a security boundary; no functional change
  needed there for this fix, though it is now provably consistent with the
  backend once this fix lands (non-admins already see the option hidden,
  and now the API backs that up for admin templates).
- Adding new permissions, new roles, or new marker groups.
- Auditing/logging enhancements for delete/refresh attempts (could be a
  follow-up, not required to close this issue).

## Open questions

- Should non-admin members retain delete/refresh on entities their own team
  owns (Component/API/Resource/System/Group/User/group-owned-Template)? The
  issue raises this explicitly as worth deciding but does not gate the fix
  on it. Interpretation taken here: preserve existing behavior for
  team-owned entities (no new restriction beyond the two the issue asks
  for), since changing that is described as a separate, undecided question
  and doing so unprompted risks breaking legitimate team workflows (e.g. a
  team removing its own stale component).
- The issue's fix direction snippet checks
  `request.permission.attributes?.action === 'read'`. Backstage's
  `catalog.entity.refresh` permission carries action `update`, not a
  dedicated `refresh` action — confirmed by the issue body itself
  ("`catalog.entity.refresh` (action `update`)"). Treated as authoritative:
  the design gates on `action !== 'read'` (deny/exclude) rather than
  enumerating `'delete'`/`'update'`, so any future non-read catalog-entity
  action is safe-by-default rather than silently falling through the old
  behavior. **Confirmed at approval**, with one addition: the same
  comparison also makes a *missing* `attributes.action` fall to the
  restrictive side, which is the right default but would break template
  visibility for every member if a Backstage upgrade ever renamed or
  dropped that field. Task 3a makes that case explicit and observable
  rather than accidental and silent.
