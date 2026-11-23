# Move to Backstage 1.57.1 and fix caret-range resolution

## Context
Backstage 1.57.1 republishes six packages (catalog-backend 4.0.5, kubernetes-backend 0.21.15, scaffolder-backend-module-github 0.10.4, api-docs 0.14.9, scaffolder-backend-module-gitlab 0.12.4, techdocs-backend-module-zensical 0.1.2) because 1.56 patches outranked 1.57.0 builds.

## User stories
- AS a platform admin I WANT caret ranges to resolve to the intended 1.57 builds SO THAT the portal at app.mctl.ai stays secure and reproducible.

## Acceptance criteria (EARS)
- WHEN the change is merged THE SYSTEM SHALL build with `yarn install --immutable` and pass lint, tsc and unit tests.
- WHEN the lockfile is inspected THE SYSTEM SHALL resolve the targeted packages to the versions named in design.md.
- WHILE the portal runs in tenant `admins` THE SYSTEM SHALL keep catalog, scaffolder, kubernetes and observability plugins functional.
- IF any smoke check fails after deployment THEN THE SYSTEM SHALL be rolled back to the previous image.

## Out of scope
- Backstage major upgrades; changes in tenant `labs`; unrelated dependency bumps.
