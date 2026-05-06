# Go 1.26.2 Upgrade for mctl-api

## Context
Go 1.26.2 was released on 2026-04-07, patching 10 CVEs across the standard library and toolchain. mctl-api currently runs Go 1.24, two minor versions behind the latest stable release. Several patched vulnerabilities directly affect the security posture of this service: CVE-2026-32283 introduces a TLS 1.3 deadlock/DoS in `crypto/tls`, which threatens both the OIDC JWT validation path (go-oidc/v3 against Dex/GitHub) and the Vault mTLS authentication channel. CVE-2026-32280 and CVE-2026-32281 introduce DoS conditions in `crypto/x509` chain-building and policy validation, affecting every TLS-terminating or certificate-verifying operation the service performs.

Beyond the immediate CVEs, remaining on an unpatched runtime exposes the service to compiler-level memory corruption (CVE-2026-27143, CVE-2026-27144) and a build-time RCE via `cmd/go` when processing external dependencies (CVE-2026-27140). Upgrading to 1.26.2 removes all ten known vulnerabilities, aligns with Go's supported-release policy (two latest minors), and keeps the service eligible for future security patches without requiring a larger catch-up effort later.

## User stories
- AS a platform operator I WANT mctl-api to be compiled and shipped with Go 1.26.2 SO THAT the service is no longer exposed to the ten CVEs patched in that release.
- AS a security engineer I WANT the OIDC JWT validation and Vault mTLS paths to use a runtime free of CVE-2026-32283 SO THAT a malicious TLS peer cannot deadlock or crash those connections.
- AS a developer I WANT the CI pipeline to enforce the Go 1.26.2 toolchain SO THAT no future build can accidentally regress to a vulnerable version.
- AS a platform operator I WANT the upgrade to be backward-compatible with existing Kubernetes and ArgoCD deployments SO THAT no tenant disruption occurs during rollout.

## Acceptance criteria (EARS)
- WHEN a new container image for mctl-api is built THE SYSTEM SHALL use Go 1.26.2 as the base toolchain image (`golang:1.26.2`).
- WHEN the CI pipeline runs a build THE SYSTEM SHALL fail if the `go` binary version reported by `go version` is not 1.26.2.
- WHEN mctl-api starts THE SYSTEM SHALL log the Go runtime version at INFO level so operators can verify the active toolchain.
- WHEN the service handles an OIDC JWT validation request WHILE running on Go 1.26.2 THE SYSTEM SHALL complete the TLS handshake without deadlock under concurrent load (verified by load test).
- WHEN the service authenticates to Vault via mTLS WHILE running on Go 1.26.2 THE SYSTEM SHALL successfully obtain a Vault token without TLS-layer errors.
- WHILE the Go 1.26.2 image is deployed THE SYSTEM SHALL pass all existing integration tests with no new failures attributable to the toolchain change.
- IF `go test ./...` reports a test failure introduced solely by the toolchain bump THEN THE SYSTEM SHALL block the release until the root cause is resolved and documented.
- WHEN a CVE scan (e.g., govulncheck) is executed against the compiled binary THE SYSTEM SHALL report zero findings for CVE-2026-32280, CVE-2026-32281, CVE-2026-32283, CVE-2026-32289, CVE-2026-27140, CVE-2026-27143, CVE-2026-27144, CVE-2026-32282, CVE-2026-32288, and CVE-2026-33810.

## Out of scope
- Upgrading any third-party Go module dependencies (chi, pgx, mcp-go, client-go, etc.) beyond what is required for Go 1.26 compatibility.
- Enabling or adopting new language features introduced in Go 1.25 or 1.26.
- Changes to the Kubernetes deployment resource requests/limits.
- Addressing CVEs in dependencies that are not part of the Go standard library or toolchain.
- Performance benchmarking or optimization work beyond confirming no regression.
- Any changes to the `labs` tenant configuration or workloads.
