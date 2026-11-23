# Upgrade mark3labs/mcp-go to 1.5.x

## Context
mcp-go 0.31.0 predates the Host-header validation fix for DNS rebinding (CVE-2026-81092, fixed in 0.56.0) and SSE request-body bounds in v1.5.0. Related earlier proposals exist (mcp-go-v1-upgrade, mcp-go-upgrade-v3); this one restates the current 2026-11-14 signal and should be merged with them at triage.

## User stories
- AS a platform operator I WANT the dependency upgraded SO THAT known advisories no longer apply to api.mctl.ai.

## Acceptance criteria (EARS)
- WHEN the service is built THE SYSTEM SHALL use github.com/mark3labs/mcp-go v1.5.x.
- WHEN CI runs THE SYSTEM SHALL pass all existing tests and govulncheck without the listed advisories.
- IF a regression is found in staging THEN THE SYSTEM SHALL be rolled back to the previous image via ArgoCD.
- WHILE the upgrade is deployed THE SYSTEM SHALL keep all 24 MCP tools and existing REST routes behaving as before.

## Out of scope
- Other dependency upgrades; router, driver or transport replacement (see ADR 0001).
