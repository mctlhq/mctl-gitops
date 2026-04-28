# Design: go-upgrade

## Current state
According to `context/architecture.md`, mctl-api is built on **Go 1.24**. The 1.24 branch received its last security patch in February 2026 (v1.24.13) and has since left active support. Critical security patches in `crypto/tls`, `crypto/x509`, `archive/tar`, `html/template`, `os` (releases 1.25.9 / 1.26.2 dated 2026-04-07) are not backported to the 1.24 branch.

mctl-api opens TLS connections to Vault (`secrets.mctl.ai`), ArgoCD, Argo Workflows, Backstage, and the Kubernetes API — all via the standard `crypto/tls`. The auth flow (Dex JWT via JWKS, OAuth JWT) uses `crypto/x509` for certificate-chain verification. A vulnerability in these packages directly threatens the confidentiality of tokens and the integrity of auth checks.

## Proposed solution
Update the `go` directive in `go.mod` from `1.24` to `1.26` and update the toolchain in the CI/CD pipeline and Dockerfile to Go 1.26.2 (the latest stable patch as of 2026-04-27).

Architectural rationale for choosing 1.26 (not 1.25):
- Go supports the two latest branches; 1.26 is the current branch, 1.25 is the previous one. Moving directly to 1.26 maximises the runway until the next mandatory upgrade.
- All security patches from 1.25.9 are included in 1.26.2 — there is no reason to stop on 1.25.

Steps:
1. Update `go.mod`: `go 1.26`.
2. Update `Dockerfile` / `.tool-versions` / CI workflow — `golang:1.26.2-alpine` (or equivalent).
3. `go mod tidy` — confirm direct dependencies are compatible with Go 1.26 (check the `go N.N` directive in each dependency's `go.mod`).
4. Build and run tests: `go test ./...`.
5. `govulncheck ./...` — confirm there are no stdlib findings.
6. Deploy via ArgoCD to `admins`.

## Alternatives

**A. Upgrade to Go 1.25 instead of 1.26.**
Closes the same CVEs, but the 1.25 branch will become unsupported when Go 1.27 is released (expected ~August 2026). Will require another upgrade in a few months. Dropped in favour of 1.26.

**B. Stay on Go 1.24 and backport patches manually.**
Not feasible within the standard Go module workflow — Go does not support vendored backports of stdlib patches. Dropped.

**C. Use the auto-updating Go toolchain directive (`toolchain go1.26`) in go.mod.**
Allows automatic patch pickup. Dropped at this stage: unpredictable toolchain drift complicates reproducible builds; this decision requires a separate ADR and an agreed update policy.

## Platform impact

**Migration:** No DB schema changes. The toolchain in the Dockerfile and CI changes — coordinate with the ops team (base image refresh).

**Backward compatibility:** Go guarantees source compatibility between minor versions within the same major. mctl-api code written for Go 1.24 compiles unchanged on Go 1.26. We must verify that all direct dependencies (chi, pgx, mcp-go, client-go, go-oidc) declare a `go` directive no higher than 1.26 — if higher, those will need updating.

**Resource impact:** A toolchain switch does not affect runtime memory or CPU usage. The `labs` tenant is not affected directly, but if `labs` uses the same CI runner, updating the Go version in CI could affect its builds — clarify with ops.

**Risks and mitigations:**
- Risk: a breaking change in `crypto/tls` behaviour (cipher-suite default changes in 1.25+) may affect TLS handshakes with Vault/ArgoCD. Mitigation: integration tests cover all outbound TLS connections; staging run before prod deploy.
- Risk: a dependency with a minimum Go version above 1.26 will require an additional bump. Mitigation: explicit check via `go mod graph` at step 3.
- Risk: `GODEBUG` default behaviour change in newer Go versions. Mitigation: review the Go 1.25 and 1.26 release notes for `GODEBUG` default changes; add explicit `//go:build` flags if needed.
