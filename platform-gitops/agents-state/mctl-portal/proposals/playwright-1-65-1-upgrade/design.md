# Design: playwright-1-65-1-upgrade

## Current state
Playwright e2e in the yarn workspace (context/architecture.md). Version is unconfirmed; a similar proposal `playwright-1-65-1-bump` may exist and should be reconciled.

## Proposed solution
Bump `@playwright/test` to 1.65.1 and refresh browsers in CI. Add one smoke spec: authenticate, open the catalog, check that known locations show as registered, open the scaffolder template list. Run it as a post-deploy gate for Backstage upgrades.

## Alternatives
- Stay on current Playwright: forgoes the regression fix if 1.65.0 is in use.
- Full e2e expansion: larger effort, deferred.

## Platform impact
- Migrations: none. Backward compatibility: dev/CI only.
- Resource impact: CI only; none in `labs` or `admins` runtime.
- Risks: browser download size, test flakiness; mitigated by retries and cached browsers.
