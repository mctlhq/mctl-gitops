# Upgrade pgx/v5 to 5.11.x

## Context
pgx 5.8 is affected by memory-safety advisories GO-2026-4772 and GO-2026-4771; v5.11.0 includes decoder hardening. Related earlier proposals exist (pgx-critical-memory-safety-cve, pgx-upgrade-v592); this one restates the current 2026-11-14 signal and should be merged with them at triage.

## User stories
- AS a platform operator I WANT the dependency upgraded SO THAT known advisories no longer apply to api.mctl.ai.

## Acceptance criteria (EARS)
- WHEN the service is built THE SYSTEM SHALL use github.com/jackc/pgx/v5 v5.11.x.
- WHEN CI runs THE SYSTEM SHALL pass all existing tests and govulncheck without the listed advisories.
- IF a regression is found in staging THEN THE SYSTEM SHALL be rolled back to the previous image via ArgoCD.
- WHILE the upgrade is deployed THE SYSTEM SHALL keep all 24 MCP tools and existing REST routes behaving as before.

## Out of scope
- Other dependency upgrades; router, driver or transport replacement (see ADR 0001).
