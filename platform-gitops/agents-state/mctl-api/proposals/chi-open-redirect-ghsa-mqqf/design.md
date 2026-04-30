# Design: chi-open-redirect-ghsa-mqqf

## Current state
mctl-api (v4.14.0) declares `github.com/go-chi/chi/v5 v5.2.1` in `go.mod` (see `context/architecture.md`). chi is the sole HTTP router, handling all REST endpoints (UI/CLI/agents) and the MCP Streamable HTTP endpoint at `/mcp`. The `RedirectSlashes` middleware is used to canonicalise trailing-slash variants of routes. In v5.2.1 through v5.2.3, this middleware does not strip backslashes from the path before constructing the `Location` header, so a request such as `GET /some-path\@attacker.example.com` can cause a browser to follow a redirect to `attacker.example.com`.

## Proposed solution
Bump `github.com/go-chi/chi/v5` from v5.2.1 to v5.2.5 in `go.mod` and run `go mod tidy`. The fix is entirely internal to the chi library; no route registrations, middleware configuration, or handler code in mctl-api needs to change.

v5.2.5 delivers two fixes over v5.2.1:
1. **GHSA-mqqf-5wvp-8fh8** — backslash not stripped in `RedirectSlashes`, enabling open redirect (fixed in v5.2.4).
2. **`RouteHeaders` double invocation** — a handler registered under `RouteHeaders` could fire twice per request (fixed in v5.2.5).

Both fixes are strictly internal and backward-compatible. Deployment follows the standard gitops path: PR to mctl-gitops → ArgoCD sync to `admins`. No migration, no schema change, no new environment variable.

## Alternatives

**1. Remove the `RedirectSlashes` middleware**
Disable the middleware entirely to eliminate the attack surface. Rejected: the middleware is a legitimate and useful canonicalisation feature. Once patched in v5.2.4, it is safe to use. Removing it would change HTTP behaviour for existing clients that rely on trailing-slash redirects.

**2. Add a custom middleware to sanitise the `Location` header**
Insert a response-writer wrapper that strips external-domain redirect targets before they are sent. Rejected: this is defensive workaround code that duplicates what the upstream fix already does, adds maintenance burden, and does not remove the underlying bug.

**3. Defer until the next scheduled maintenance window**
Batch this with other upgrades. Rejected: an open redirect on an authenticated platform API is an active phishing vector. The effort is trivially low (Effort 1), and the fix has been available since v5.2.4 (published before the advisory date).

## Platform impact

**Migrations:** None. chi v5.2.5 has the same router API as v5.2.1; no route or middleware changes are required.

**Backward compatibility:** chi follows semver within v5; v5.2.5 is a drop-in patch-stream upgrade. No call-site changes needed.

**Resource impact:** No change to memory or CPU footprint. The `labs` tenant is not affected; mctl-api runs under `admins`.

**Risks and mitigations:**
- Risk: The `RouteHeaders` double-invocation fix (v5.2.5) alters execution semantics for routes using that feature. Mitigation: the existing integration test suite covers all registered routes; any handler firing twice would produce duplicate side-effects visible in tests. Review usage of `RouteHeaders` in the codebase before merging.
- Risk: A transitive dependency of chi introduces a version conflict. Mitigation: `go mod tidy` surfaces conflicts immediately; resolve before merging.
