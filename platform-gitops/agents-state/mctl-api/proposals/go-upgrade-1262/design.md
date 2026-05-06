# Design: go-upgrade-1262

## Current state
mctl-api is built with Go 1.24 (see `context/architecture.md`). The service is deployed to the `admins` tenant on Kubernetes via ArgoCD. Container images are built in CI using a `golang:1.24` base image. The `go.mod` file declares `go 1.24`. Key security-sensitive paths that run on the current toolchain include:

- OIDC JWT validation via `go-oidc/v3` (TLS to Dex / GitHub JWKS endpoints) — vulnerable to CVE-2026-32283 (crypto/tls TLS 1.3 deadlock).
- Vault mTLS authentication via `auth/kubernetes` — also uses `crypto/tls`, same exposure.
- X.509 certificate verification on all outbound TLS connections (ArgoCD, Backstage, Argo Workflows, Kubernetes API) — vulnerable to CVE-2026-32280 and CVE-2026-32281.
- Build pipeline fetching external modules at compile time — vulnerable to CVE-2026-27140 (cmd/go RCE via malicious SWIG file names).

Ten CVEs patched in Go 1.26.2 are unaddressed on Go 1.24. Previous proposals (go-upgrade, go-upgrade-stdlib-cves-v2, go-toolchain-ace-cve-27140) targeted earlier release trains and do not cover the 1.26.2 release.

## Proposed solution
Update the toolchain reference from Go 1.24 to Go 1.26.2 at every layer where a version is pinned, then rebuild and redeploy the service.

**What changes:**

1. `go.mod` — update the `go` directive from `go 1.24` to `go 1.26.2`. Run `go mod tidy` to pick up any minor adjustments to the module graph required by the new toolchain.
2. `Dockerfile` (or equivalent CI build spec) — change `FROM golang:1.24` to `FROM golang:1.26.2` (or `golang:1.26.2-alpine` if the current image is Alpine-based).
3. CI pipeline configuration (GitHub Actions / ArgoCD build step) — pin the `go-version` input to `1.26.2` and add a `govulncheck` step that fails the build if any of the ten patched CVEs are detected.
4. Runtime startup log — emit `runtime.Version()` at INFO level on service start (one-line change in `main.go`) so the deployed version is observable in logs.

**Why this approach:**

A pure toolchain-version bump is the minimal-risk path. It touches no application logic, no dependency versions beyond what the module graph requires for Go 1.26 compatibility, and no Kubernetes manifests. The Go 1.x compatibility guarantee means existing code should compile and behave identically; the test suite serves as the regression gate. This minimizes review surface and rollback complexity while closing all ten CVEs.

## Alternatives

**Alternative 1: Stay on Go 1.24 and apply targeted mitigations (rejected)**
One could attempt to mitigate CVE-2026-32283 at the application layer (e.g., adding TLS connection timeouts) and accept the remaining CVEs as low-exploitability. This is rejected because: (a) application-layer timeouts do not fully address a deadlock in the TLS state machine; (b) accepting compiler-level memory corruption CVEs (CVE-2026-27143, CVE-2026-27144) and a build-time RCE (CVE-2026-27140) is incompatible with the platform's security posture; (c) Go 1.24 will eventually leave the supported window, forcing the upgrade anyway.

**Alternative 2: Upgrade to Go 1.25.x instead of 1.26.2 (rejected)**
Go 1.25.x does not include the patches for the ten CVEs listed above — those were introduced in 1.26.2. Stopping at 1.25 would close only a subset of the vulnerabilities and still leave the service one minor version behind latest stable. Going directly to 1.26.2 closes all ten CVEs in a single change.

**Alternative 3: Rebuild only the final binary layer without updating go.mod (rejected)**
Using a 1.26.2 builder image while leaving `go 1.24` in `go.mod` would produce a binary compiled with the new toolchain but without the module graph reflecting 1.26.2 semantics. This is fragile: `go mod tidy` on 1.26.2 may produce a different graph than on 1.24, leading to silent inconsistencies. The correct approach is to update both `go.mod` and the build image atomically.

## Platform impact

**Migrations**
No database migrations. No changes to Kubernetes manifests, ConfigMaps, Secrets, or ArgoCD Application specs. The upgrade is entirely within the build and runtime layer.

**Backward compatibility**
Go guarantees source-level compatibility within the 1.x series. All existing API endpoints, MCP tools, auth flows, and Vault/ArgoCD integrations are expected to compile and function identically. Any incompatibility surfaced by `go mod tidy` or the test suite must be resolved before release.

**Resource impact (labs)**
The Go runtime memory footprint does not change meaningfully between minor versions. No change to container resource requests or limits is planned. The `labs` tenant is near its memory limit; however, this proposal affects only the `admins` tenant deployment of mctl-api. Labs workloads are not modified and carry no additional memory risk from this change.

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|---|---|---|
| A third-party module fails to compile under Go 1.26 | Low — Go 1.x compat guarantee | Run `go mod tidy` + `go build ./...` in CI before merging; fix any incompatibility |
| A subtle behavioral change in `crypto/tls` or `crypto/x509` breaks OIDC or Vault auth | Low | Integration tests covering OIDC login and Vault token acquisition must pass before deployment |
| ArgoCD image sync triggers an unexpected rollout during a high-traffic window | Low | Schedule the ArgoCD sync during a maintenance window; use a canary or blue/green rollout if available |
| govulncheck flags a new CVE in a dependency not previously scanned | Informational | Treat as a separate follow-up proposal; do not block this upgrade on unrelated findings |
