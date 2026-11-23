# Design: backstage-security-advisories-bump

## Current state
Backstage monorepo (yarn workspaces, Node 22||24), see context/architecture.md. Current portal version 1.0.1 (context/current-version.md). Deployed versions of affected packages must be confirmed first.

## Proposed solution
Fixed minimums: plugin-scaffolder-backend >=4.1.0 (or 4.0.3 on that line), plugin-kubernetes-backend >=0.21.9, plugin-techdocs-backend >=2.4.2, plugin-auth-node with the 106460 fix. Run `yarn backstage-cli versions:bump` (target release 1.57.1), then verify with `yarn why`. Also rotate any credentials that scaffolder tasks may have exposed if older versions ran after Oct 6.

## Alternatives
- Pin individual packages via yarn resolutions — dropped: drifts from Backstage release set.
- Wait for next biweekly release — dropped: leaves known exposure/inconsistency open.

## Platform impact
- Migrations: none expected (patch/minor).
- Backward compatibility: patch-level; no API changes announced.
- Resource impact: neutral; no added memory in `labs` (portal runs in `admins`).
- Risks: transient plugin incompatibility; mitigated by staging smoke test and image rollback.
