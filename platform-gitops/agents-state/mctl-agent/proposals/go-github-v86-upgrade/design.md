# Design: go-github-v86-upgrade

## Current state

`go.mod` declares `github.com/google/go-github/v68 v68.x.x`. The library is used
exclusively in the PR-creation leg of the fix pipeline (likely in
`internal/skill/builtin/` or a `github` package). Call sites follow the v68 pattern:

```go
pr, _, err := client.PullRequests.Create(ctx, owner, repo, opts)
```

where `ctx` is passed as the first argument to each method. See
`context/architecture.md` for the overall pipeline description.

## Proposed solution

### Step 1 — Jump directly to v86

Skip the intermediate v85 migration (covered by superseded proposals) and upgrade
`go.mod` to `github.com/google/go-github/v86`. This avoids a two-step migration and
ensures the service is on the current stable release.

### Step 2 — Migrate context-passing pattern

In v86 the context is embedded in the request via `github.WithAuthToken` / request
middleware rather than as a positional argument. The migration involves:

1. Changing import paths from `github.com/google/go-github/v68/github` →
   `github.com/google/go-github/v86/github`.
2. Updating every `client.XYZ.Method(ctx, ...)` call site to drop the explicit `ctx`
   argument and instead ensure the client is initialised with a context-aware transport
   (e.g. `github.NewClient(oauth2.NewClient(ctx, ts))`).
3. Re-running `go mod tidy` to remove the v68 transitive closure.

### Step 3 — Update tests

Existing table-driven tests for the PR path mock the GitHub client. Mocks must be
regenerated or manually updated to match v86 method signatures.

## Alternatives

| Option | Reason rejected |
|---|---|
| Migrate to v85 first, then v86 | Doubles migration cost; v85 proposals not yet landed |
| Stay on v68 indefinitely | Accumulates CVE and API debt; blocks future improvements |
| Replace go-github with direct REST calls | Increases maintenance; go-github provides correct auth rotation handling |

## Platform impact

### Migrations
`go.mod` and all call sites in the GitHub client package. No database changes.

### Backward compatibility
PR output (title, body, base/head branches) is unchanged. The GitHub API endpoint
(`POST /repos/{owner}/{repo}/pulls`) is unaffected; this is a client-library migration
only.

### Resource impact
- No increase in memory or CPU footprint.
- **`labs` tenant**: not impacted — this change lives entirely in the `admins` tenant
  service binary.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Undiscovered v68→v86 breaking changes beyond context pattern | Run `go build ./...` after import path swap; fix compile errors iteratively |
| Token rotation CronWorkflow (`cwft-rotate-github-token`) interacts with client init | Audit the token refresh path; ensure the new context-aware transport honours rotated tokens |
| Test mocks out of sync | Regenerate mocks with `mockery` or update manually; CI enforces compilation |
| Merge conflicts with in-flight v85 proposals | Close/supersede v85 proposals after this PR lands |
