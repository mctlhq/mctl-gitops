# Design: chi-open-redirect

## Current state
mctl-agent uses `github.com/go-chi/chi/v5 v5.2.1` (declared in `go.mod`, see `context/architecture.md`). chi provides the HTTP router for all endpoints: `POST /api/v1/alerts`, `POST /api/v1/telegram`, `GET /api/v1/tickets`, `GET /api/v1/skills`, `POST /api/v1/skills/register`, `POST /mcp`, `GET /healthz`, `GET /readyz`. If `middleware.RedirectSlashes` is used (common chi setup pattern), GHSA-mqqf-5wvp-8fh8 applies: a crafted request URL can cause chi to issue a redirect to an attacker-controlled host.

## Proposed solution
Update `go.mod` to declare `github.com/go-chi/chi/v5 v5.2.5`. Run `go mod tidy` to regenerate `go.sum`. No router configuration or handler code changes are required — v5.2.5 is fully backward-compatible with v5.2.1 at the API level.

**Verification step:** audit `internal/` and `cmd/` for any use of `middleware.RedirectSlashes`. If present, confirm the updated middleware only redirects to same-host paths. If absent, the CVE has no attack surface in this codebase, but the upgrade is still applied to close the structural gap and pick up the `RouteHeaders` double-invocation fix.

## Alternatives

### A. Disable RedirectSlashes middleware without upgrading
Removes the attack surface without a version bump. However, it does not fix the underlying flaw, leaves the RouteHeaders bug in place, and does not advance the version to receive future security patches. Rejected — upgrading is strictly better and equally low effort.

### B. Replace chi with standard `net/http` ServeMux (Go 1.22+)
Go 1.22 introduced pattern-matching ServeMux that covers most of chi's use cases. This would eliminate the chi dependency entirely. However, it is a large refactor touching every handler registration, violates the low-effort criterion, and provides no immediate security benefit beyond upgrading. Rejected — out of scope for a CVE-fix proposal.

### C. Pin chi at v5.2.4 (minimum fix version)
v5.2.5 is the latest stable; v5.2.4 is the minimum fix. Pinning to v5.2.4 leaves a known minor bug (double handler invocation in RouteHeaders) unaddressed. Rejected — use the latest stable.

## Platform impact

### Migrations
None — pure module version bump with no API changes.

### Backward compatibility
chi v5.2.5 is backward-compatible with v5.2.1. All existing route registrations, middleware chains, and handler signatures remain valid.

### Resource impact
Negligible. chi is a lightweight router; the new version adds no new goroutines or memory allocations at startup. **No impact on the `labs` tenant.**

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| RedirectSlashes behaviour change breaks a test | Very Low | Full test suite run in CI |
| RouteHeaders fix changes response for edge-case requests | Very Low | Inspect any tests relying on RouteHeaders behaviour |
| `go mod tidy` pulls in an incompatible transitive dep | Very Low | Review `go.sum` diff in PR |
