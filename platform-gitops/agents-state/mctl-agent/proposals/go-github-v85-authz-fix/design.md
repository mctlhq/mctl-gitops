# Design: go-github-v85-authz-fix

## Current state

`go.mod` contains `github.com/google/go-github/v68 v68.x.x`. All files dealing with the
GitHub API import `github.com/google/go-github/v68/github`. The client is used in
`internal/skill/builtin/` (at minimum the PR-creation skill) and in the token-init HTTP
handler. According to `context/architecture.md`, **Google/go-github v68** is used to open
PRs with fixes in `mctlhq/mctl-gitops`.

## Proposed solution

A three-phase upgrade:

### Phase 1 — Update go.mod
```diff
-require github.com/google/go-github/v68 v68.x.x
+require github.com/google/go-github/v85 v85.0.0
```
Run `go mod tidy`.

### Phase 2 — Rewrite imports
All lines of the form:
```go
import "github.com/google/go-github/v68/github"
```
are replaced with:
```go
import "github.com/google/go-github/v85/github"
```
Done automatically with the command:
```bash
find . -name '*.go' | xargs sed -i 's|go-github/v68|go-github/v85|g'
```

### Phase 3 — Address breaking changes
Documented breaking changes between v68 and v85:
- `MarkThreadDone` — return type changed; if used, adapt.
- Custom Organization Role API — types changed; check `Audit` for usage.
- Other breaking changes — surfaced via `go build ./...` at the compile step.

Cross-host redirect rejection is enabled automatically in v85 — no extra code required.
A test for redirect behaviour can be added (see tasks.md T2).

## Alternatives

| Option | Why dropped |
|---|---|
| Stay on v68 and configure `http.Client` with a custom `CheckRedirect` manually | High maintenance overhead; conflict of configurations on the next upgrade; misses future go-github security patches. |
| Stepwise upgrade through intermediate versions (v68 → v75 → v85) | Go modules support a direct jump; intermediate versions only add risk. |
| Switch to direct GitHub REST API calls without a library | Total loss of typing and future security patches; high effort; conflicts with the existing architecture. |

## Platform impact

- **Migration**: changes are confined to go.mod and imports — purely in mctl-agent code,
  nothing in GitOps manifests or CRDs.
- **Backward compatibility**: runtime PR-creation behaviour does not change; only the
  behaviour on an anomalous cross-host redirect changes (now returns an error instead of following).
- **Resource impact**: client-side library, no memory growth. Neutral for `labs`.
- **Risks and mitigations**:
  - *Risk*: unknown breaking changes between v68 and v85 (17 major versions).
  - *Mitigation*: `go build ./...` in CI surfaces all compile-time errors; a full
    `go test ./...` surfaces runtime regressions. Use a feature branch and pass all tests before merge.
  - *Rollback*: revert the commit in git → rebuild the image → update the tag in GitOps.
