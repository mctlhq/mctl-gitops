# Upgrade go-chi/chi from 5.2.1 to 5.3.2

## Context
chi routes every ingress path in mctl-agent: the AlertManager webhook
(`POST /api/v1/alerts`), the Telegram webhook (`POST
/api/v1/telegram`), the REST API (`/api/v1/tickets`, `/api/v1/skills`,
`/api/v1/skills/register`), and the MCP JSON-RPC endpoint (`POST
/mcp`). The current pin is chi v5.2.1. chi v5.3.2 was released
2026-08-20, a small 4-commit diff since v5.3.1, fixing a real
Mount()/Route() handler-collision bug, deduplicating the `Allow` header
on 405 responses, and closing a compress-middleware wildcard hole.

Separately, CVE-2025-69725 (GHSA-mqqf-5wvp-8fh8, CVSS 4.7) is an Open
Redirect in chi's `RedirectSlashes` middleware, reported to affect chi
>=5.2.2. Our current pin (5.2.1) is just below that range, so we are
not confirmed to be affected today — but the chi v5.3.2 release notes
do not explicitly state whether this CVE is fixed. This proposal
bundles the router bump with an explicit verification step for that
CVE so we do not silently assume it is resolved by version number
alone.

## User stories
- AS the mctl-agent maintainer I WANT chi upgraded to 5.3.2 SO THAT
  routing collision, 405-response, and compress-middleware wildcard
  bugs are fixed across all ingress paths.
- AS a security reviewer I WANT an explicit, documented answer on
  whether mctl-agent is exposed to CVE-2025-69725 SO THAT we don't rely
  on an assumption that upgrading past 5.2.1 silently fixes an
  unconfirmed vulnerability.

## Acceptance criteria (EARS)
- WHEN the mctl-agent module is built THE SYSTEM SHALL use
  `github.com/go-chi/chi/v5` at version 5.3.2 as declared in `go.mod`.
- WHEN the full router-level test suite is run THE SYSTEM SHALL pass,
  covering `Mount()`/`Route()` registration for all existing endpoint
  groups without handler collisions.
- WHEN a request path yields a 405 Method Not Allowed response THE
  SYSTEM SHALL return an `Allow` header containing no duplicate HTTP
  methods.
- IF the mctl-agent codebase uses chi's `RedirectSlashes` middleware
  THEN THE SYSTEM SHALL have that usage reviewed against
  CVE-2025-69725 and either confirmed fixed in 5.3.2, confirmed
  not-applicable (middleware unused or usage pattern not exploitable),
  or mitigated by an explicit workaround — the outcome SHALL be
  recorded in this proposal's task log, not left implicit.
- IF the mctl-agent codebase does not use `RedirectSlashes` at all THEN
  THE SYSTEM SHALL record that finding explicitly as the closure for
  the CVE-2025-69725 verification task.
- WHILE the upgrade is in review THE SYSTEM SHALL keep all existing API
  routes, methods, and response contracts unchanged — this is a router
  library bump, not an API redesign.

## Out of scope
- Any change to route paths, handlers, or the API contract itself.
- Adopting new chi 5.3.x features beyond the bugfixes already shipped
  (e.g. no new middleware adopted as part of this bump).
- The Go toolchain upgrade (tracked separately in
  `go-toolchain-security-upgrade`).
- Fixing CVE-2025-69725 upstream in chi itself — if verification shows
  mctl-agent is exposed and chi 5.3.2 does not fix it, the mitigation
  (e.g. dropping `RedirectSlashes` usage or replacing it) becomes a
  follow-up proposal, not part of this one.
