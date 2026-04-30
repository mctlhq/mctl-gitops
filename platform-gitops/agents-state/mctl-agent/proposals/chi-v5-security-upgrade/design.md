# Design: chi-v5-security-upgrade

## Current state
As documented in `context/architecture.md`, mctl-agent uses `go-chi/chi v5.2.1` as its HTTP
router. chi handles routing for all API endpoints: `POST /api/v1/alerts`,
`POST /api/v1/telegram`, `GET /api/v1/tickets`, `GET /api/v1/skills`,
`POST /api/v1/skills/register`, `POST /mcp`, `GET /healthz`, and `GET /readyz`. The Go
module is declared as `github.com/go-chi/chi/v5 v5.2.1` in `go.mod`.

CVE-2025-69725 affects chi v5.2.2 through v5.2.4: the `RedirectSlashes` middleware
introduced an open-redirect flaw in those versions. v5.2.5 was released with the hardened
middleware. mctl-agent on v5.2.1 does not contain the vulnerable code, but version
v5.2.1 is one patch increment away from the range. The patch release cadence of chi means
it is realistic that a `go get -u ./...` or `go mod tidy` run by a future engineer could
inadvertently move the pinned version into the vulnerable range.

## Proposed solution
The upgrade is a single-line change to `go.mod` plus a `go mod tidy` to refresh `go.sum`.
No source file changes are required because the v5.x series maintains full API compatibility.

**Steps:**
1. `go get github.com/go-chi/chi/v5@v5.2.5`
2. `go mod tidy`
3. `go build ./...` to confirm no compilation errors.
4. Run the full test suite to confirm no behavioural regressions.
5. Merge, build a new container image, and deploy via ArgoCD.

The v5.2.5 release notes confirm: no API removals or signature changes relative to v5.2.1;
minimum Go version is 1.22 (satisfied by the service's Go 1.24 runtime); binary size change
is negligible.

**Why this approach?** A one-line `go.mod` change with zero source edits is the lowest-risk
change possible. It addresses the forward-exposure concern with a single commit that is easy
to review, easy to revert, and carries no functional change to the service.

## Alternatives

### Alternative A: Stay on v5.2.1 and document the exclusion
Explicitly pin to v5.2.1 and add a `go.mod` `exclude` directive for v5.2.2–v5.2.4. Dropped
because an `exclude` directive only blocks direct `go get` upgrades; it does not prevent
indirect dependency resolution from selecting a vulnerable version, and it does not deliver
the hardened middleware of v5.2.5.

### Alternative B: Replace chi with a different router (e.g., gorilla/mux, net/http ServeMux)
Swap chi entirely to eliminate the dependency. Dropped because it is architecturally
disproportionate to a CVSS 4.7 patch upgrade, would require rewriting all route and
middleware registrations, and introduces regression risk orders of magnitude greater than the
one-line fix.

### Alternative C: Upgrade to the next minor version (chi v6, if available)
If chi v6 exists, adopt it for a more substantial upgrade. Dropped because as of 2026-04-30
no stable chi v6 has been released; v5.2.5 is the current latest stable and the correct
target.

## Platform impact

### Migrations
`go.mod` and `go.sum` are updated. No other files change.

### Backward compatibility
chi v5 is fully backward-compatible within the minor series. All existing route definitions,
middleware registrations, and handler signatures remain valid without modification.

### Resource impact
Binary size delta is negligible (confirmed in the v5.2.5 release notes). No change in
runtime memory or CPU consumption. No impact on the `labs` tenant — this change is deployed
in `admins` only, and the `labs` tenant does not run mctl-agent.

### Risks and mitigations
- **Risk:** An undocumented behavioural change in chi v5.2.5 affects request routing for
  one of the registered endpoints. **Mitigation:** The full test suite covers all endpoints;
  any routing regression will be caught before merge. The change can be reverted in under
  5 minutes by rolling back the ArgoCD image tag.
- **Risk:** `RedirectSlashes` is not registered in mctl-agent today, meaning the hardened
  middleware delivers no direct runtime benefit. **Mitigation:** The benefit is forward
  protection: the hardened implementation is present in the binary, so if `RedirectSlashes`
  is ever registered in the future it will be the safe version. This is explicitly noted in
  the out-of-scope section.
