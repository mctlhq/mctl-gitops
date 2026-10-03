# Upgrade go-chi/chi to v5.3.2 for the Mount()/Route() handler-collision fix

## Context
chi routes every ingress path in mctl-agent: the AlertManager webhook
(`POST /api/v1/alerts`), the Telegram bot webhook (`POST /api/v1/telegram`), the REST
API (`GET /api/v1/tickets`, `GET /api/v1/skills`, `POST /api/v1/skills/register`), and
the MCP JSON-RPC endpoint (`POST /mcp`). The current pin is `go-chi/chi v5.2.1`.
`go-chi/chi v5.3.2` (released 2026-08-20) fixes a bug where `Mount()`/`Route()` handler
collisions could silently drop a registered handler, in addition to adding new default
compressible content types and deduping HTTP methods in `Allow:` headers on 405
responses. Because mctl-agent mounts several distinct routers (AlertManager, Telegram,
REST, MCP) onto one chi instance, a silent route drop from this bug is a real
availability risk specifically for the alert-ingestion path — the highest-value traffic
this service receives.

Two existing proposals (`go-chi-v5.3.2-router-upgrade` and
`chi-redirect-cve-boundary-check`) already track a bump to chi v5.3.2 bundled with a
CVE-2025-69725 (`RedirectSlashes` open-redirect) boundary check. This proposal is
narrower and does not duplicate the CVE-boundary work: this cycle's CVE research
clarified that CVE-2025-69725's fix landed in v5.2.4+ and that our shipped v5.2.1
predates (and is therefore not exposed to) the affected range (>=5.2.2), closing out
that CVE concern independently of this bump. This proposal exists to make sure the
Mount()/Route() fix itself is not lost or indefinitely deferred if the CVE-boundary
proposals stall for unrelated reasons — it should be treated as the same underlying
dependency bump as those two proposals, not a fourth independent chi upgrade.

## User stories
- AS the mctl-agent operator, I WANT chi upgraded to v5.3.2 SO THAT a Mount()/Route()
  handler-collision bug cannot silently drop a registered handler on the AlertManager,
  Telegram, REST, or MCP routers.
- AS the mctl-agent maintainer, I WANT this proposal explicitly reconciled with the
  existing `go-chi-v5.3.2-router-upgrade` and `chi-redirect-cve-boundary-check`
  proposals SO THAT we do not ship three separate PRs bumping the same dependency to
  the same version.

## Acceptance criteria (EARS)
- WHEN the mctl-agent module is built THE SYSTEM SHALL use `github.com/go-chi/chi/v5`
  at version 5.3.2 as declared in `go.mod`.
- WHEN the router-registration test suite is run THE SYSTEM SHALL pass, covering
  `Mount()`/`Route()` registration for the AlertManager webhook, Telegram webhook, REST
  API, and MCP endpoint routers without any handler being silently dropped.
- WHEN a request path yields a 405 Method Not Allowed response THE SYSTEM SHALL return
  an `Allow` header containing no duplicate HTTP methods.
- IF this proposal reaches implementation before `go-chi-v5.3.2-router-upgrade` or
  `chi-redirect-cve-boundary-check` THEN THE SYSTEM SHALL close those proposals as
  fulfilled by this one's PR, rather than executing the same `go.mod` bump three times.
- IF one of those other proposals reaches implementation first THEN THE SYSTEM SHALL
  close this proposal as fulfilled by that PR instead.
- WHILE the upgrade is in review THE SYSTEM SHALL keep all existing API routes,
  methods, and response contracts unchanged — this is a router library bump, not an
  API redesign.

## Out of scope
- CVE-2025-69725 (`RedirectSlashes` open redirect) verification — already closed out
  by this cycle's research (fix confirmed at v5.2.4+, our v5.2.1 pin predates the
  affected range >=5.2.2) and tracked historically by `chi-redirect-cve-boundary-check`.
  No new action needed on that CVE as part of this proposal.
- Adopting new chi 5.3.x features beyond the bugfixes already shipped (no new
  middleware, no new default compressible content types adopted deliberately — they
  come along with the bump but are not the motivation for it).
- The Go toolchain upgrade (tracked separately in `go-toolchain-security-upgrade`).
- Any change to route paths, handlers, or the API contract itself.
