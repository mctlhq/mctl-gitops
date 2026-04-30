# Patch chi to v5.2.5 to fix open redirect (GHSA-mqqf-5wvp-8fh8)

## Context
mctl-api (v4.14.0) uses `go-chi/chi/v5` v5.2.1 as its HTTP router for every REST and MCP endpoint. GHSA-mqqf-5wvp-8fh8 (GO-2026-4316, CVSS 4.7 Moderate, published 2026-01-14) discloses an open redirect in chi's `RedirectSlashes` middleware: a backslash in the request path is not trimmed before the redirect is issued. Browsers follow such redirects, allowing an attacker to craft a URL on `api.mctl.ai` that silently redirects an authenticated platform operator or agent to an attacker-controlled domain. This enables phishing and OAuth credential harvesting against accounts that already hold valid sessions.

The fix is available in chi v5.2.4; v5.2.5 additionally resolves a double handler invocation in `RouteHeaders`. Bumping from v5.2.1 to v5.2.5 closes the vulnerability and picks up both fixes with no breaking API changes.

## User stories
- AS a platform operator I WANT mctl-api's HTTP router to be free of GHSA-mqqf-5wvp-8fh8 SO THAT I cannot be redirected to attacker-controlled domains via crafted URLs on api.mctl.ai.
- AS a security engineer I WANT the dependency bumped to v5.2.5 SO THAT compliance scans no longer flag an open redirect on the production API.
- AS a developer I WANT the fix to require no changes to route definitions or middleware configuration SO THAT the patch ships quickly and with low review risk.

## Acceptance criteria (EARS)
- WHEN the CI pipeline builds mctl-api THEN THE SYSTEM SHALL resolve `go-chi/chi/v5` at v5.2.5 or higher as shown in `go.sum`.
- WHEN a security scanner runs against the merged branch THEN THE SYSTEM SHALL report zero open findings for GHSA-mqqf-5wvp-8fh8 / GO-2026-4316.
- WHEN a request path containing a backslash is received and `RedirectSlashes` is active THEN THE SYSTEM SHALL redirect only to a path on the same origin, never to an external domain.
- WHILE mctl-api is handling HTTP requests after the upgrade THE SYSTEM SHALL route all existing REST and MCP endpoints correctly with no change in status codes or response bodies for well-formed requests.
- IF the chi upgrade introduces a transitive dependency conflict THEN THE SYSTEM SHALL resolve it without removing or downgrading any other direct dependency.

## Out of scope
- Disabling or replacing the `RedirectSlashes` middleware (the middleware is correct after the patch; removal is unnecessary).
- Changing any route definitions, handler logic, or middleware ordering.
- Upgrading any other dependency as part of this change.
- Applying the fix to any service other than mctl-api.
