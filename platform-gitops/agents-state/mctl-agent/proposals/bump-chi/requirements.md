# Upgrade go-chi/chi v5.2.1 to v5.2.5

## Context
mctl-agent uses `go-chi/chi v5.2.1` as its HTTP router for all publicly accessible endpoints
(AlertManager webhook at `POST /api/v1/alerts`, Telegram webhook at `POST /api/v1/telegram`,
REST API, MCP JSON-RPC at `POST /mcp`, and health probes). The service is exposed at
`https://agent.mctl.ai`.

CVE-2025-69725 (GHSA-mqqf-5wvp-8fh8, CVSS 4.7 Medium) describes an open-redirect vulnerability
in chi's `RedirectSlashes` middleware: a crafted URL can cause the `Location` response header to
resolve to an attacker-controlled host. The vulnerability was introduced in v5.2.2 and patched in
v5.2.4. The current pin of v5.2.1 pre-dates the regression, but upgrading to v5.2.5 is the
correct remediation because it also fixes a double handler invocation bug in `RouteHeaders` and
aligns with the Go 1.22 minimum now required by the updated toolchain (see proposal
`bump-go-toolchain`).

Upgrading is a single `go.mod` line change with no application-level code modifications required.

## User stories
- AS a security reviewer I WANT chi to be pinned at a version that is not vulnerable to
  CVE-2025-69725 SO THAT the agent's publicly accessible endpoints cannot be used as an open
  redirect to an attacker-controlled host.
- AS a platform engineer I WANT chi upgraded to v5.2.5 SO THAT the `RouteHeaders` double-handler
  invocation bug does not silently process requests twice.
- AS a developer I WANT `go.mod` to reflect the current stable chi release SO THAT routine
  dependency audits do not flag the router as outdated.

## Acceptance criteria (EARS)
- WHEN a request arrives at any chi-routed endpoint with a URL crafted to trigger an open redirect
  THEN THE SYSTEM SHALL NOT return a `Location` header pointing to a host other than `agent.mctl.ai`.
- WHEN `RedirectSlashes` middleware is active and a trailing-slash redirect is issued THEN THE
  SYSTEM SHALL redirect only to the same host and path with the slash appended or removed.
- WHEN a request matches a `RouteHeaders` pattern THEN THE SYSTEM SHALL invoke the matched handler
  exactly once.
- IF the `go-chi/chi/v5` version in `go.mod` is less than v5.2.5 THEN THE SYSTEM SHALL fail CI
  with a dependency audit error.
- WHILE the agent is serving HTTP traffic THEN THE SYSTEM SHALL route all requests using chi v5.2.5
  or later.

## Out of scope
- Changing any routing logic, middleware stack, or endpoint behavior.
- Upgrading to chi v6 or any future major version.
- Adding new middleware (e.g., rate-limiting, authentication) as part of this change.
- Remediating CVE-2025-69725 via WAF rules or reverse-proxy configuration (that would be a
  complementary control, not a substitute for patching the library).
