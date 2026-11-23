# Bump Playwright to 1.65.1

## Context
Playwright 1.65.1 (13 Nov) fixes a 1.65 regression where decorated classes with static fields fail to load when useDefineForClassFields is false; bundled Chromium 159, Firefox 159, WebKit 27.2.

## User stories
- AS a platform admin I WANT e2e tests on the latest Playwright patch SO THAT the portal at app.mctl.ai stays secure and reproducible.

## Acceptance criteria (EARS)
- WHEN the change is merged THE SYSTEM SHALL build with `yarn install --immutable` and pass lint, tsc and unit tests.
- WHEN the lockfile is inspected THE SYSTEM SHALL resolve the targeted packages to the versions named in design.md.
- WHILE the portal runs in tenant `admins` THE SYSTEM SHALL keep catalog, scaffolder, kubernetes and observability plugins functional.
- IF any smoke check fails after deployment THEN THE SYSTEM SHALL be rolled back to the previous image.

## Out of scope
- Backstage major upgrades; changes in tenant `labs`; unrelated dependency bumps.
