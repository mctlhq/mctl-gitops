# Upgrade Go from 1.24 to a current supported branch (1.26)

## Context
Go follows a policy of supporting the two latest major branches. The Go 1.24 branch received its last security patch (1.24.13) in February 2026 and no longer receives fixes. Security patches for `crypto/tls`, `crypto/x509`, `archive/tar`, `html/template`, `os` and the compiler ship only in branches 1.25 and 1.26 (releases 1.25.9 and 1.26.2 dated 2026-04-07).

mctl-api implements three types of bearer authentication (GitHub PAT, Dex JWT, OAuth JWT) and opens TLS connections to Vault, ArgoCD, Argo Workflows, and Backstage. Vulnerabilities in `crypto/tls` and `crypto/x509` directly threaten the confidentiality and integrity of these connections. The current stable branch is 1.26 (latest patch 1.26.2).

## User stories
- AS a platform security engineer I WANT mctl-api built with Go 1.26 SO THAT all TLS/PKI security patches are applied and the runtime is on a supported release branch.
- AS a developer I WANT to use Go 1.26 language features and standard library improvements SO THAT code quality and toolchain support are maintained.

## Acceptance criteria (EARS)
- WHEN the CI pipeline builds mctl-api THE SYSTEM SHALL use Go 1.26.x toolchain (verified via `go version` in build output and `go.mod` `go` directive).
- WHEN mctl-api establishes outbound TLS connections (Vault, ArgoCD, Argo Workflows, Backstage) THE SYSTEM SHALL use the TLS stack from Go 1.26 with all published security fixes applied.
- WHILE running under Go 1.26 THE SYSTEM SHALL pass all existing unit and integration tests without modification to business logic.
- IF `govulncheck` is run against the built binary THE SYSTEM SHALL report no findings related to the Go standard library CVEs fixed in 1.25/1.26.
- WHEN the service starts under Go 1.26 THE SYSTEM SHALL expose correct `/metrics` and `/healthz` responses, confirming no runtime regressions.
- IF any direct dependency requires a minimum Go version higher than 1.26 THE SYSTEM SHALL surface a build error and the dependency shall be pinned to a compatible version before merging.

## Out of scope
- Migration to Go 1.27+ or switching to the auto-updating Go toolchain directive.
- Updating dependencies that do not require changes for Go 1.26 compatibility.
- Refactoring code to use new language features from Go 1.25/1.26 (range-over func, improved type inference, etc.) — a separate task after the upgrade.
- Updating base Docker images and CI runners (a related infra task, outside the mctl-api repo scope).
