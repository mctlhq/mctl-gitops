# Upgrade Go toolchain and x/net to fix HTTP/2 DoS advisories

## Context
mctl-api is internet-facing (api.mctl.ai). Several 2026 HTTP/2 DoS advisories affect net/http and golang.org/x/net (CVE-2026-56853, CVE-2026-33814, CVE-2026-27141, CVE-2026-78669, GO-2026-6603/6610/6612/6617). We are on Go 1.24, which is out of support, so no fixes will land there.
Fixes require Go >= 1.25.13 / 1.26.6 (1.26.9 recommended) and x/net >= v0.62.0. Related earlier proposals exist (go-runtime-*, go-upgrade-*); this one consolidates the current advisory set.

## User stories
- AS a platform operator I WANT a supported, patched Go toolchain SO THAT unauthenticated clients cannot crash or exhaust the API via HTTP/2.
- AS a developer I WANT go.mod and the Dockerfile aligned SO THAT builds are reproducible.

## Acceptance criteria (EARS)
- WHEN the service is built THE SYSTEM SHALL use Go 1.26.9 or later and golang.org/x/net v0.62.0 or later.
- WHEN govulncheck runs in CI THE SYSTEM SHALL report no reachable net/http or x/net HTTP/2 vulnerabilities.
- WHILE serving HTTP/2 traffic THE SYSTEM SHALL keep p99 latency and error rate within 10% of the pre-upgrade baseline.
- IF the upgrade fails the MCP Inspector smoke test THEN THE SYSTEM SHALL NOT be promoted beyond the canary rollout.

## Out of scope
- Dependency bumps other than those required by the toolchain (see mcp-go-v1-upgrade, pgx-chi-bumps-realip-audit).
