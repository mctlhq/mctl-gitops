# Design: go-runtime-upgrade

## Current state

mctl-api v4.14.0 declares `go 1.24` in its `go.mod` and is compiled by the Go 1.24 toolchain in CI. The resulting container image is deployed to the `admins` tenant via mctl-gitops and ArgoCD. Go 1.24 is now outside the active-support window and carries five unpatched stdlib CVEs:

| CVE | Package | Risk to mctl-api |
|---|---|---|
| CVE-2026-32280 | crypto/x509 | DoS via unbounded intermediate chain — hits every OIDC JWT verification (go-oidc/v3 path) |
| CVE-2026-32281 | crypto/x509 | DoS via policy mapping loop — same OIDC verification path |
| CVE-2026-32283 | crypto/tls | TLS 1.3 deadlock under concurrent load — affects all inbound HTTPS and outbound TLS calls |
| CVE-2026-27143 | cmd/compile | Memory corruption in compiled binary — affects the entire service binary |
| CVE-2026-32289 | html/template | XSS — minimal exposure (mctl-api is JSON-only) |

The crypto/tls deadlock (CVE-2026-32283) is the highest operational risk: it can halt the entire API server including MCP tools and REST endpoints because all connections pass through the affected code path.

See `context/architecture.md` for the full stack and `context/current-version.md` for the deployed version.

## Proposed solution

### What changes

1. `go.mod` toolchain directive is updated from `go 1.24` to `go 1.26.2`.
2. The CI Dockerfile base image (builder stage) is updated from `golang:1.24-alpine` (or equivalent) to `golang:1.26.2-alpine`.
3. The CI pipeline gains an explicit `govulncheck` step that fails the build if any of the five target CVEs remain present.
4. `go mod tidy` is run to regenerate `go.sum` and ensure the module graph is consistent under the new toolchain.

### Why this approach

Go's compatibility guarantee (https://go.dev/doc/go1compat) ensures that code that compiled under Go 1.24 compiles and runs correctly under Go 1.26 with no source changes required. The upgrade is a pure toolchain swap: no application logic, API contracts, or dependency versions need to change. This is the lowest-risk path to eliminating all five CVEs.

### Dependency compatibility check

- `chi/v5 5.2.1` requires minimum Go 1.22 — satisfied by 1.26.2.
- `go-oidc/v3` — no minimum Go version above 1.21 documented; satisfied.
- `pgx/v5 5.8`, `client-go 0.32`, `mcp-go 0.31`, `httprate 0.15`, `prometheus/client_golang 1.23` — all require Go 1.21 or lower minimums; satisfied.
- A `go build ./...` dry-run and `go test ./...` in CI will surface any compile-time incompatibility before merge.

### Deployment path

The change flows through the standard mctl-gitops pipeline:

```
PR opened → CI (build + govulncheck + unit tests) → merge to main
  → image pushed with new tag → mctl-gitops PR auto-created
  → ArgoCD syncs admins tenant → canary / rolling-update observed
```

No manifest changes beyond the container image tag are required.

## Alternatives

### Option A: Apply targeted source-level patches for CVE-2026-32283 only

Vendor the affected `crypto/tls` package and cherry-pick the upstream fix without moving the toolchain. This would close the most operationally dangerous CVE but leave CVE-2026-32280, CVE-2026-32281, and CVE-2026-27143 open, and it requires maintaining a vendored stdlib fork — an ongoing maintenance burden that is antithetical to Go's upgrade model. Dropped.

### Option B: Upgrade only to Go 1.25.x

Go 1.25.x is not the current stable release as of 2026-05-04; Go 1.26.x is. Stopping at 1.25.x would close the current CVEs but put the service one minor version behind the active-support line immediately, requiring another upgrade cycle sooner than necessary. Upgrading directly to 1.26.2 is the same effort and provides a longer runway. Dropped.

### Option C: Introduce a WAF rule to block malformed certificates at the ingress layer

A WAF cannot intercept the OIDC JWT verification path because the certificate validation happens inside the Go process during JWKS key resolution, not at the HTTP layer. Similarly, a WAF has no visibility into the crypto/tls TLS 1.3 state machine. This option mitigates none of the five CVEs. Dropped.

## Platform impact

### Migrations

None. Go's compatibility guarantee applies; no source-code migration is needed. `go mod tidy` regenerates `go.sum` deterministically.

### Backward compatibility

The REST API contract and MCP Streamable HTTP interface are unchanged. All three authentication flows (GitHub PAT, Dex JWT, OAuth JWT) remain behaviorally identical. The upgrade is internal to the build toolchain.

### Resource impact (`labs` tenant)

This proposal does not change any resource requests or limits for the `admins` tenant and makes no changes to the `labs` tenant whatsoever. Go 1.26 binary sizes and runtime memory footprints are comparable to Go 1.24; no memory pressure increase is anticipated. This proposal is not flagged as risky for `labs`.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| A dependency fails to compile under Go 1.26 | Low — all major deps declare Go 1.21 or lower minimums | `go build ./...` in CI gates the PR; fix by pinning or patching the affected dep |
| A behavioral change in stdlib affects auth or TLS dial behavior | Very low — Go compat guarantee | Full integration test suite run in CI; crypto/tls behavioral regression would surface in TLS dial tests against Vault / ArgoCD stubs |
| govulncheck reports a new unrelated vulnerability during the scan | Possible | Treat as a separate finding; do not block this PR unless severity is critical |
| Rolling update briefly mixes old and new pods | Inherent to rolling deploys | mctl-api is stateless at the HTTP layer; the Postgres connection pool reconnects transparently; ArgoCD sync strategy already uses rolling updates |
