# Design: rbac-location-update-permission

## Current state
Permission framework with RBAC through Dex group mapping (context/architecture.md). Policy rules for location permissions are in the backend permission policy module.

## Proposed solution
Audit the policy for `catalog.location.create` and `catalog.location.delete`; make update-capable groups explicit by granting both permissions to the same group set. Add unit tests for the policy covering create/delete/update scenarios. Ship ahead of or together with any upgrade to 1.57.x.

## Alternatives
- Leave default policy: may silently break catalog-import or over-grant.
- Allow delete to all authenticated users: over-permissive, rejected.

## Platform impact
- Migrations: none.
- Backward compatibility: no change for current behaviour before 1.57.x; compatible after.
- Resource impact: none; `labs` unaffected.
- Risks: over-granting delete; mitigated by tests and review.
