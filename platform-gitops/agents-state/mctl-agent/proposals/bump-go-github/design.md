# Design: bump-go-github

## Current state
`context/architecture.md` records `google/go-github v68` as the library used for all GitHub API
interactions. The agent's PR-creation path (pipeline stage: fix → PR → notify) calls
`github.PullRequestsService.Create` with a short-lived installation token sourced from Vault at
`secret/platform/github-app`. The token is rotated every 30 minutes by the
`cwft-rotate-github-token` CronWorkflow and injected at runtime via environment variable.

v68 does not validate cross-host redirects, does not strip `..` segments from constructed URLs, and
does not enforce payload size limits in `ValidatePayloadFromBody`. All three gaps are present in
every agent release since the dependency was first introduced.

## Proposed solution
Bump `google/go-github` from v68 to v85 in `go.mod`/`go.sum` and update the import paths from
`github.com/google/go-github/v68/github` to `github.com/google/go-github/v85/github` throughout
the codebase.

The v85 client transparently enforces the three security properties (redirect rejection,
path validation, payload size limits) without requiring caller-side code changes in the common case.
Any call sites that relied on cross-host redirect following or non-canonical URL construction must be
updated to remove that reliance — but given that the agent only calls `api.github.com`, no such sites
are expected.

Dependency resolution: run `go get github.com/google/go-github/v85@v85.0.0 && go mod tidy`.

## Alternatives

### A. Pin at an intermediate version (e.g., v75)
Ruled out: there is no security-relevant intermediate checkpoint that closes all three issues. v85 is
the earliest version that bundles all three fixes. Taking an intermediate version would require
another upgrade cycle within weeks.

### B. Wrap the existing v68 client with a custom HTTP transport that rejects cross-host redirects
Ruled out: this duplicates security logic that already exists in v85, introduces a maintenance
surface, and does not address the path-traversal or payload-size issues. It is strictly worse than
upgrading.

### C. Replace go-github with direct `net/http` calls to the GitHub REST API
Ruled out: the library provides typed request/response objects, pagination helpers, and rate-limit
handling that would all need to be re-implemented. The effort is disproportionate to the problem.

## Platform impact

### Migrations
Import paths must be updated from `v68` to `v85` across all Go source files that reference the
library. The public API surface of go-github is stable across these versions for the methods the
agent uses (`PullRequestsService.Create`, `RepositoriesService.GetContents`, etc.); no functional
changes to call sites are anticipated.

### Backward compatibility
The v85 client is backward-compatible with existing API usage patterns. The one observable behavior
change — rejection of cross-host redirects — is desirable and not relied upon by current code.

### Resource impact (`labs` tenant)
This is a pure dependency upgrade with no change to binary size, memory footprint, or goroutine
count. The `labs` tenant is not impacted; no risk to its memory limit.

### Risks and mitigations
- **API surface change:** The 17-version gap means some method signatures may have changed. Mitigation:
  compile the project after the upgrade and resolve any type errors before merging.
- **Transitive dependency churn:** `go mod tidy` may pull in updated transitive dependencies. Mitigation:
  review the diff of `go.sum` in the PR and flag any unexpected new modules for manual audit.
- **Test coverage gap:** Existing unit tests mock the GitHub client at the interface level and will not
  exercise the new redirect-rejection logic. Mitigation: add an integration test (see tasks.md T2)
  that confirms the redirect is rejected when a test HTTP server redirects to a different host.
