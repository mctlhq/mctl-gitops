# Verify and bump Backstage packages for Oct 2026 advisories

## Context
October 2026 advisories include CVE-2026-106501 (9.6, scaffolder credential disclosure), 106502/106504 (scaffolder events/logs), 106561 (kubernetes masked values), 106460 (auth-node email verification) and 106489/106490 (techdocs). We must confirm our resolved versions include the fixes.

## User stories
- AS a platform admin I WANT all affected packages verified at or above fixed versions SO THAT the portal at app.mctl.ai stays secure and reproducible.

## Acceptance criteria (EARS)
- WHEN the change is merged THE SYSTEM SHALL build with `yarn install --immutable` and pass lint, tsc and unit tests.
- WHEN the lockfile is inspected THE SYSTEM SHALL resolve the targeted packages to the versions named in design.md.
- WHILE the portal runs in tenant `admins` THE SYSTEM SHALL keep catalog, scaffolder, kubernetes and observability plugins functional.
- IF any smoke check fails after deployment THEN THE SYSTEM SHALL be rolled back to the previous image.

## Out of scope
- Backstage major upgrades; changes in tenant `labs`; unrelated dependency bumps.
