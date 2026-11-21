# Design: backstage-1-57-1-version-fix

## Current state
Backstage monorepo (yarn workspaces, Node 22||24), see context/architecture.md. Current portal version 1.0.1 (context/current-version.md). Deployed versions of affected packages must be confirmed first.

## Proposed solution
Set backstage.json to 1.57.1 via `yarn backstage-cli versions:bump`, dedupe the lockfile, and confirm the six packages resolve at or above the listed versions. Skip packages we do not use.

## Alternatives
- Pin individual packages via yarn resolutions — dropped: drifts from Backstage release set.
- Wait for next biweekly release — dropped: leaves known exposure/inconsistency open.

## Platform impact
- Migrations: none expected (patch/minor).
- Backward compatibility: patch-level; no API changes announced.
- Resource impact: neutral; no added memory in `labs` (portal runs in `admins`).
- Risks: transient plugin incompatibility; mitigated by staging smoke test and image rollback.
