# Upgrade Playwright to 1.65.1 and add post-upgrade catalog smoke e2e

## Context
Playwright 1.65.1 (13 Nov) fixes a regression in 1.65 where decorated classes with static fields fail to load. We use Playwright for e2e. Backstage 1.57.4 also re-encodes catalog location URLs once on upgrade, which we want to cover with a smoke test.

## User stories
- AS a developer I WANT a working e2e toolchain SO THAT CI is reliable.
- AS a platform admin I WANT a smoke test of catalog and scaffolder SO THAT upgrades are verified automatically.

## Acceptance criteria (EARS)
- WHEN dependencies are installed THE SYSTEM SHALL resolve `@playwright/test` at 1.65.1 or later.
- WHEN the e2e suite runs THE SYSTEM SHALL load all spec files without class-initialisation errors.
- WHEN the smoke test runs THE SYSTEM SHALL verify that catalog locations load and the scaffolder template list renders.
- IF a catalog location fails to refresh after an upgrade THEN THE SYSTEM SHALL fail the smoke test.
- WHILE running in CI only THE SYSTEM SHALL add no runtime resource usage to the deployed portal.

## Out of scope
- Rewriting existing e2e tests; runtime changes.
