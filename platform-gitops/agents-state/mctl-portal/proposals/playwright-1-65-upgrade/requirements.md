# Upgrade Playwright to 1.65 for e2e

## Context
Playwright 1.65.0 (05 Nov) drops Node 20 testing, changes cookie matching (RFC 6265), ARIA snapshot text, inert-element handling and TS class field semantics, and adds a `failures` reporter. We run e2e with Playwright; breaking changes may alter test outcomes.

## User stories
- AS a developer I WANT a current Playwright SO THAT e2e stays supported and CI output focuses on failures.

## Acceptance criteria (EARS)
- WHEN the bump is merged THE SYSTEM SHALL pin `@playwright/test` to 1.65.x and update browsers in CI.
- WHEN the e2e suite runs on Node 22 and 24 THE SYSTEM SHALL pass with no snapshot drift left unreviewed.
- WHEN a test fails in CI THE SYSTEM SHALL print failures via the `failures` reporter.
- IF an ARIA snapshot differs only due to unrendered-text exclusion THEN THE SYSTEM SHALL update the snapshot with reviewer approval.

## Out of scope
- Bun runner, test lock adoption, new test coverage.
