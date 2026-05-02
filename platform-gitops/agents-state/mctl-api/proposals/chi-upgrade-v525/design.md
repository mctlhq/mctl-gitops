# Design: chi-upgrade-v525

## Current state
mctl-api v4.14.0 uses `github.com/go-chi/chi/v5` at v5.2.1 as its sole HTTP router, handling all REST and MCP endpoints. The middleware stack includes `RedirectSlashes`, rate limiting via `httprate`, and OIDC/JWT authentication middleware. Per `context/architecture.md`, switching the router to gin, echo, or any other framework is not permitted.

## Proposed solution
Bump the single dependency line in `go.mod` from `github.com/go-chi/chi/v5 v5.2.1` to `github.com/go-chi/chi/v5 v5.2.5`, then run `go mod tidy` to update `go.sum`. This is a minor-version patch bump within the chi/v5 line; the chi project maintains API compatibility across 5.x patch releases, so no handler or middleware call-site changes are expected. After the bump, the `RedirectSlashes` middleware will include the CVE-2025-69725 fix and will refuse to issue redirects to external domains. The atomic-type refactor also included in v5.2.5 may marginally reduce memory contention under load but requires no code changes on our side. The minimum Go version required by chi v5.2.5 is 1.22; mctl-api targets Go 1.24, so there is no toolchain conflict.

## Alternatives
1. Remain on v5.2.1 — the service is not currently in the vulnerable range, so immediate risk is low. However, this leaves a latent trap: any accidental or transitive bump into v5.2.2–v5.2.4 would silently introduce the open-redirect CVE. Deferred technical debt with no upside; rejected.
2. Pin to v5.2.3 or v5.2.4 — both versions fall squarely inside the CVE-2025-69725 vulnerable range and offer no benefit over v5.2.1. Rejected.
3. Switch to gin or echo — explicitly rejected by `context/architecture.md` ("Do not propose switching the Go router to gin/echo without a strong benchmark"). Out of scope for this proposal.

## Platform impact
- Migrations: none required. The change is confined to `go.mod` and `go.sum`.
- Backward compatibility: chi/v5 minor bumps are API-compatible. No handler, middleware, or routing changes are expected.
- Resource impact: the atomic-type refactor in v5.2.5 may marginally reduce memory contention; no increase in CPU or memory usage is anticipated. No impact on the `labs` tenant memory ceiling.
- Risks and mitigations: minimal. The chi v5.2.x patch series is well-tested upstream. Risk is further mitigated by the existing routing test suite (unit tests, integration tests) and the staging smoke-test described in tasks.md. Rollback to v5.2.1 is immediate and carries no security regression since v5.2.1 is outside the vulnerable range.
