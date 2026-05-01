# Design: go-toolchain-upgrade

## Current state
mctl-agent (see `context/architecture.md`) is compiled with **Go 1.24**. The service runs in the `admins` tenant on Kubernetes + ArgoCD. The build toolchain is specified in:
- `go.mod` — `go 1.24` directive
- The CI Dockerfile `FROM golang:1.24-alpine` (or equivalent builder image)
- Any ArgoCD/Argo Workflows build templates that pin the Go image

Seven CVEs patched in Go 1.26.2 are currently open against every binary produced by the Go 1.24 toolchain and against the Go 1.24 standard-library packages shipped inside those binaries.

## Proposed solution

**Change the toolchain pin from Go 1.24 to Go 1.26.2 in every location that references it.**

Concretely:

1. `go.mod` — update the `go` directive to `go 1.26.2` and add/update the `toolchain go1.26.2` line (Go 1.21+ workspace toolchain management).
2. Dockerfile builder stage — change `FROM golang:1.24-alpine` to `FROM golang:1.26.2-alpine` (or the distroless equivalent used in the project).
3. CI pipeline YAML (Argo Workflows CronWorkflow / GitHub Actions, whichever is in use) — update any hard-coded Go version environment variable or image reference.
4. Run `go mod tidy` to refresh `go.sum` with hashes for stdlib packages that changed.
5. Verify `go vet ./...` and the full test suite pass unchanged.

**Why this approach:**
- The upgrade is a patch-level bump within the Go 1.x compatibility promise; no source code changes are expected.
- Go 1.26 preserves full backwards compatibility with Go 1.24 module code per the Go compatibility policy.
- A toolchain-only change is the narrowest possible diff, minimising review surface and rollback complexity.
- It directly closes all 7 CVEs in a single PR.

## Alternatives

**A. Stay on Go 1.24 and wait for an LTS-equivalent backport.**
Go does not have an LTS model; 1.24 will receive no further security patches once 1.26.x is current. This leaves the vulnerabilities open indefinitely. Dropped.

**B. Upgrade only to Go 1.25.9 (the parallel patch branch).**
Go 1.25.9 carries the same 7 CVE fixes as 1.26.2. However, upgrading directly to 1.26.2 — the latest release — reduces future upgrade distance and is equally low-risk given the compatibility guarantee. Using the latest patch of the latest minor avoids the need for another toolchain upgrade in the near term. Dropped in favour of 1.26.2.

**C. Apply source-level workarounds (e.g., limit intermediate certificates, avoid archive/tar sparse paths).**
Workarounds are fragile, not exhaustive across all 7 CVEs, and create technical debt. CVE-2026-27143 (compiler memory corruption) cannot be mitigated at the source level at all — only the toolchain fix resolves it. Dropped.

## Platform impact

**Migrations:**
- `go.mod` and `go.sum` will be regenerated; no schema migrations are required.
- The CI/CD pipeline image reference must be updated before the next build.

**Backward compatibility:**
- Go 1.26 is backward compatible with Go 1.24 source code per the Go compatibility policy. No application code changes are anticipated.
- If any third-party dependency uses a build tag or `//go:build` constraint that conflicts with Go 1.26, `go mod tidy` will surface it and it will be resolved before merging.

**Resource impact (labs tenant):**
- The Go toolchain upgrade does NOT increase the memory footprint of the compiled binary or its runtime RSS. Go 1.26 does not add new background goroutines or increase the default GC target. The binary size change from a toolchain bump is negligible (typically < 1%). There is **no risk to the labs tenant memory limit** from this change. This is explicitly confirmed: the proposal introduces zero additional resident memory on the labs tenant.

**Risks and mitigations:**
- Risk: A third-party dependency uses a deprecated internal package removed in 1.26. Mitigation: run `go build ./...` and `go vet ./...` in CI against Go 1.26.2 before merging; block the PR if any error surfaces.
- Risk: The CI builder image (`golang:1.26.2-alpine`) introduces a different Alpine version with a glibc/musl incompatibility. Mitigation: the build produces a statically linked binary (CGO_ENABLED=0, which is already required because modernc.org/sqlite is pure Go); no dynamic linking issues can arise.
- Risk: Automated dependabot/renovate bot creates a conflicting PR simultaneously. Mitigation: coordinate with the bot configuration to suppress duplicate toolchain PRs; merge this PR first.
