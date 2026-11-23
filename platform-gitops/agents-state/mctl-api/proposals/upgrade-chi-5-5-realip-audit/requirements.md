# Upgrade chi to 5.5.0 and audit RealIP trust

## Context
chi 5.2.1 has advisories for RealIP X-Forwarded-For spoofing (GO-2026-5777/5775/5774) and RedirectSlashes open redirect (GO-2026-4316); httprate keyed by IP and audit-log IPs could be spoofed. Related earlier proposals exist (pgx-chi-bumps-realip-audit, chi-upgrade-v525); this one restates the current 2026-11-14 signal and should be merged with them at triage.

## User stories
- AS a platform operator I WANT the dependency upgraded SO THAT known advisories no longer apply to api.mctl.ai.

## Acceptance criteria (EARS)
- WHEN the service is built THE SYSTEM SHALL use github.com/go-chi/chi/v5 v5.5.0.
- WHEN CI runs THE SYSTEM SHALL pass all existing tests and govulncheck without the listed advisories.
- IF a regression is found in staging THEN THE SYSTEM SHALL be rolled back to the previous image via ArgoCD.
- WHILE the upgrade is deployed THE SYSTEM SHALL keep all 24 MCP tools and existing REST routes behaving as before.

## Out of scope
- Other dependency upgrades; router, driver or transport replacement (see ADR 0001).
