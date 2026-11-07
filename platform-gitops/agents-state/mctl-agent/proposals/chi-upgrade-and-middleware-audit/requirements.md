# Upgrade chi 5.2.1 to 5.5.0 and audit RealIP / RedirectSlashes usage

## Context
chi/v5 routes the AlertManager webhook, Telegram webhook, REST API and `/mcp`, so router and middleware bugs are directly exposed. The Go vuln list reportedly shows an X-Forwarded-For IP spoofing issue in the `RealIP` middleware and an open redirect in `RedirectSlashes`. chi v5.5.0 (14 Oct) changes: Deprecation header, Maybe handler built once, Retry-After rounding, SupressNotFound no longer mutates the route context. Current pin is 5.2.1.

UNVERIFIED: advisory dates and fixed-in versions are unknown; both issues may already be fixed in 5.2.1 or earlier, or may have no fix. It is also unknown whether the code uses either middleware at all, and whether any rate limiting or allow-list depends on client IP.

## User stories
- AS a platform operator I WANT the router library current and its risky middleware audited SO THAT public webhooks cannot be abused via spoofed client IPs or redirects.
- AS the mctl-agent owner I WANT advisory facts confirmed SO THAT effort is spent only on real exposure.

## Acceptance criteria (EARS)
- WHEN the proposal is started THE SYSTEM SHALL confirm the chi advisories (IDs, dates, affected and fixed versions) from the Go vuln DB / `govulncheck` and record whether 5.2.1 is affected.
- WHEN the codebase is audited THE SYSTEM SHALL list every use of `middleware.RealIP` and `middleware.RedirectSlashes` and every place that reads client IP (rate limiting, logging, allow-lists, auth).
- IF `RealIP` is used and any security decision depends on the resulting address THEN THE SYSTEM SHALL either remove the middleware or restrict it to trusted proxy sources.
- IF `RedirectSlashes` is used and the advisory applies THEN THE SYSTEM SHALL remove it or upgrade to a fixed version, and verify no request can redirect to an external host.
- WHEN chi is upgraded to 5.5.0 (or the verified fixed version if different) THE SYSTEM SHALL pass the full test suite and route regression tests for every endpoint in `context/architecture.md`.
- WHEN `govulncheck` runs after the upgrade THE SYSTEM SHALL report no chi findings.
- WHILE the upgrade is deployed THE SYSTEM SHALL keep webhook responses (status codes, 404 and 405 behavior) unchanged except documented chi 5.5.0 changes.
- IF the audit shows neither middleware is used and 5.2.1 is unaffected THEN THE SYSTEM SHALL still upgrade as routine maintenance but treat the security priority as low.

## Out of scope
- Replacing chi with another router.
- Go toolchain bump (see go-toolchain-bump) and other dependency upgrades.
- Adding new rate limiting or auth features.
