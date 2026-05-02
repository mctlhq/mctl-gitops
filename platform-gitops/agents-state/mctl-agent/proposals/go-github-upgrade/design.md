# Design: go-github-upgrade

## Current state
`go.mod` declares `github.com/google/go-github/v68 v68.x.x`. The service uses the client in (presumed) `internal/github/` or equivalent to:
1. Create a feature branch from `main` in `mctlhq/mctl-gitops`.
2. Commit the remediation patch.
3. Open a pull request with structured metadata (title, body, labels).

v68 does not reject cross-host redirects, meaning any 3xx response from GitHub's API that points to a different host will forward the `Authorization` header. The GitHub App token has write access to `mctlhq/mctl-gitops`, so this is a high-impact credential-exposure vector.

## Proposed solution

**Step 1 — Replace the import path and bump the version**

In `go.mod`:
```
require github.com/google/go-github/v85 v85.0.0
```

All import paths in Go source change from:
```go
import "github.com/google/go-github/v68/github"
```
to:
```go
import "github.com/google/go-github/v85/github"
```

This can be done with a single `sed` pass or `gofmt`-based tool.

**Step 2 — Adapt breaking API changes**

The v68→v85 changelog introduces the following relevant breaking changes:
- `MarkThreadDone(ctx, threadID int64)` → `MarkThreadDone(ctx, threadID string)` — mctl-agent likely does not call this; verify and update if needed.
- `GetOrgRole`, `CreateCustomOrgRole`, `UpdateCustomOrgRole` parameter signatures changed — verify usage; update if needed.
- Google App Engine standard environment support removed — not relevant (mctl-agent runs on Kubernetes).

For PR creation specifically (`PullRequestsService.Create`, `GitService.CreateRef`, `RepositoriesService.CreateFile`), no breaking changes have been identified in the v68–v85 range.

**Step 3 — Adopt structured error types (optional but recommended)**

v85 introduces a `Type()` method on API errors. Wrap GitHub API calls to log `err.(*github.ErrorResponse).Type()` at ERROR level for faster incident diagnosis.

**Architecture diagram — unchanged**
The go-github client remains a thin wrapper called by the existing fix-PR component. No new services, no new storage, no new API endpoints.

## Alternatives

**A — Vendor-patch v68 to backport the redirect fix**
Would fix the immediate CVE without the migration cost. Rejected: vendored patches create a maintenance burden, are invisible to `go mod tidy`, and do not fix the accumulated correctness improvements in v69–v85.

**B — Migrate to the GitHub REST API via raw HTTP**
Removes the dependency entirely. Rejected: reimplementing OAuth token handling, pagination, and retry logic is far more effort and error-prone than upgrading the library.

**C — Upgrade to v85 in two hops (v68→v75, v75→v85)**
Splits the migration into smaller diffs. Rejected: the breaking changes are concentrated in org-role APIs that mctl-agent does not use; a single hop is feasible.

## Platform impact

**Migrations:** Import path change only (`/v68` → `/v85`). No database schema, config, or API contract changes.

**Backward compatibility:** Full at the service API level. The PRs created in `mctlhq/mctl-gitops` are unchanged in content and format.

**Resource impact:** Negligible binary size change. No runtime memory or CPU impact. No impact on `labs` tenant.

**Risks and mitigations:**
- *Risk:* Undetected usage of broken API methods (MarkThreadDone, org-role APIs) causes compilation failure.  
  *Mitigation:* `go build ./...` will fail fast; all call sites are easy to locate and fix.
- *Risk:* v85 introduces a new default timeout or retry policy that changes PR creation latency.  
  *Mitigation:* Run the staging smoke test (Task 5) and compare PR creation timing against baseline.
- *Risk:* The `golang:1.24.8` base image (from `go-runtime-patch`) is not yet deployed, causing a module graph conflict.  
  *Mitigation:* This proposal depends on `go-runtime-patch` being merged first (or run concurrently); document the dependency in tasks.
