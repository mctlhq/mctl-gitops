# Adapt permission policy to the new catalog.location.delete requirement

## Context
Backstage v1.57.4 requires `catalog.location.delete` in addition to `catalog.location.create` to update a catalog location. Our RBAC uses group mapping via the permission framework; a policy that allows create but not delete would break catalog-import updates, and a policy that allows delete broadly could grant more than intended.

## User stories
- AS a platform admin I WANT the permission policy to reflect the new requirement SO THAT location updates are allowed only to intended groups.
- AS a developer I WANT catalog-import to keep working SO THAT I can register and update components.

## Acceptance criteria (EARS)
- WHEN a user in an authorized group updates a catalog location THE SYSTEM SHALL allow it after the upgrade.
- WHEN a user without `catalog.location.delete` attempts a location update THE SYSTEM SHALL deny it.
- WHEN the policy is evaluated for location create, update and delete THE SYSTEM SHALL use the same group allowlist.
- IF the policy lacks an explicit rule for `catalog.location.delete` THEN THE SYSTEM SHALL deny by default.
- WHILE the upgrade is in progress THE SYSTEM SHALL keep existing deletion restrictions unchanged.

## Out of scope
- Redesigning the RBAC model or group mapping.
