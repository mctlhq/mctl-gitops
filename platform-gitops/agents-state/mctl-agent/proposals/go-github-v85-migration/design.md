# Design: go-github-v85-migration

## Current state
As documented in `context/architecture.md`, mctl-agent depends on
`github.com/google/go-github/v68` for all GitHub operations, specifically PR creation in
`mctlhq/mctl-gitops`. The import path `github.com/google/go-github/v68` appears in
`go.mod`, `go.sum`, and in every `.go` source file that uses the GitHub client. The library
is used in the fix pipeline: after a skill produces a patch, the PR service client calls
`PullRequestsService.Create` (and potentially `ActivityService.MarkThreadDone` for
notification handling). The GitHub App installation token is rotated by an external
CronWorkflow and injected as an environment variable; the library itself does not manage the
token lifecycle.

The v68 → v85 delta introduces two documented breaking changes:
1. `ActivityService.MarkThreadDone` changed its parameter type.
2. Custom org role option handling was broken in intermediate versions and fixed in v85.

Both must be addressed at their call sites.

## Proposed solution
The migration is a mechanical source-level upgrade in three steps:

**Step 1 — Module update.**
Run `go get github.com/google/go-github/v85@v85.0.0` and `go mod tidy`. This updates
`go.mod` and `go.sum`. The old `v68` entries are removed by tidy.

**Step 2 — Import path rewrite.**
Use `sed` or `gofmt`-compatible tooling to replace every occurrence of
`"github.com/google/go-github/v68"` with `"github.com/google/go-github/v85"` across all
`.go` files. A single `grep -r` pass confirms no v68 references remain.

**Step 3 — Breaking-change call-site fixes.**
- Locate the `MarkThreadDone` call site. Update the argument to match the v85 signature
  (the changelog specifies the new parameter type; apply it verbatim).
- Locate any custom org role option usage. Apply the corrected v85 field or method as
  documented in the v85 release notes.
- Run `go build ./...` and `go vet ./...` to confirm zero errors.

**Why this approach?** The upgrade is intentionally minimal: fix only what the compiler and
the breaking-change documentation mandate, and add no new functionality. This keeps the diff
reviewable and the risk surface small. A larger refactor of the GitHub client layer (e.g.,
introducing an interface for testability) is explicitly deferred to a separate proposal.

## Alternatives

### Alternative A: Incremental version-by-version upgrade (v68 → v70 → ... → v85)
Step through each major version to understand intermediate changes. Dropped because Go module
major versions are independent; the source changes required are the same whether you migrate
in one hop or many, and the changelog for v85 documents all breaking changes relative to
v68 clearly enough to address them directly.

### Alternative B: Vendor a forked or pinned v68 and defer the upgrade indefinitely
Keep the vendored v68 copy and patch it locally if issues arise. Dropped because this creates
a private fork burden, loses upstream security patches, and makes the eventual forced
migration even more expensive. The "migrate under incident pressure" scenario is the risk
this proposal explicitly aims to avoid.

### Alternative C: Abstract the GitHub client behind an interface and upgrade behind the
interface boundary
Introduce a `GitHubClient` interface so the concrete library can be swapped without touching
callers. This is a desirable future state but it conflates two concerns (abstraction and
upgrade) and would widen the diff significantly. It is deferred to a follow-on proposal.

## Platform impact

### Migrations
`go.mod` and `go.sum` are updated. No database schema changes. No Kubernetes manifest
changes. The GitHub App token mechanism and the CronWorkflow are unaffected.

### Backward compatibility
The v85 `PullRequestsService.Create` API is backward-compatible with the v68 call for the
parameters mctl-agent uses (owner, repo, `NewPullRequest` struct). Only the two documented
breaking-change call sites require source edits. All other call sites compile unchanged after
the import path rewrite.

### Resource impact
The compiled binary size change is negligible (< 1 MB). No runtime memory or CPU impact.
No impact on the `labs` tenant — this change runs only in `admins`.

### Risks and mitigations
- **Risk:** An undocumented breaking change exists between v68 and v85 that the changelog
  does not surface. **Mitigation:** `go build ./...` and `go vet ./...` catch compile-time
  regressions; the existing table-driven integration tests for PR creation catch behavioural
  regressions before merge.
- **Risk:** The `go.sum` update introduces a supply-chain concern (new checksum entries for
  17 intermediate versions are not pulled in — only v85 is fetched). **Mitigation:** `go mod
  tidy` fetches only the direct v85 module; `go mod verify` confirms checksums against the
  sum database.
- **Risk:** The GitHub App installation token format or scopes required by v85 differ from
  v68. **Mitigation:** The token is provided externally via environment variable; the library
  uses it as a bearer token with no format assumptions. Review the v85 authentication section
  of the changelog to confirm no new token type is required.
