# Design: go-runtime-patch

## Current state
`go.mod` declares `go 1.24` with no explicit `toolchain` directive, meaning the build uses whatever Go version the CI runner or Dockerfile provides. The Dockerfile (presumed to be `FROM golang:1.24` or equivalent) pins a major.minor but not a patch version. Go vulnerability scanners (`govulncheck`, Trivy, Grype) flag the binary for the 10 CVEs published on 2026-04-07.

See `context/architecture.md` — Tech stack section — for the authoritative version declaration.

## Proposed solution

**Change 1 — `go.mod` toolchain pin**

Add or update the `toolchain` directive in `go.mod`:

```
go 1.24

toolchain go1.24.8
```

The `toolchain` directive (introduced in Go 1.21) instructs `go` to refuse to build if the active toolchain is older than the declared version. This is an enforcement mechanism, not just documentation.

**Change 2 — Dockerfile base image**

Update the builder stage from `golang:1.24` (or whichever minor-pinned tag is currently used) to `golang:1.24.8`:

```dockerfile
FROM golang:1.24.8-alpine AS builder
```

**Change 3 — CI pipeline**

If the CI workflow file (`.github/workflows/*.yml` or equivalent) pins a Go version via `actions/setup-go`, update the `go-version` input to `'1.24.8'`.

**No source-code changes are required.** The Go 1.24.8 compiler is fully backward-compatible with Go 1.24.x source code.

## Alternatives

**A — Upgrade to Go 1.25 or 1.26 instead**
Would also fix all 1.24.x CVEs, but introduces a new minor version with its own potential regressions, new vet checks that may require source changes, and a larger testing surface. Rejected for this proposal; tracked separately.

**B — Use `govulncheck` suppression annotations and defer the patch**
Would silence scanner alerts without fixing the underlying vulnerabilities. Rejected — suppression is not a mitigation.

**C — Ship a custom Go toolchain built from source**
Unnecessary operational complexity when the official `golang:1.24.8` image is available. Rejected.

## Platform impact

**Migrations:** None. The binary ABI is unchanged; no database schema, config format, or API contract is modified.

**Backward compatibility:** Full — Go 1.24.8 is a patch release; all source code compiled with 1.24.x compiles cleanly.

**Resource impact:** Negligible. The compiled binary size may change by a few KB; runtime memory and CPU are unaffected. No impact on `labs` tenant.

**Risks and mitigations:**
- *Risk:* A new vet check added in 1.24.8 flags existing code.  
  *Mitigation:* Run `go vet ./...` in CI before merging; fix any new findings before release.
- *Risk:* The `golang:1.24.8` Docker image is not yet available in the registry mirror.  
  *Mitigation:* Verify image availability before raising the PR; fall back to pulling from Docker Hub if the mirror lags.
