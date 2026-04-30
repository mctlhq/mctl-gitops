# Design: go-upgrade-stdlib-cves-v2

## Current state

mctl-api v4.14.0 is compiled with Go 1.24 (last patch: go1.24.13, 2026-02-04).
Go 1.24 reached end-of-life on 2026-02-11 and receives no further security
patches. The Dockerfile uses a `golang:1.24-alpine` build stage.

The service handles TLS termination and performs OIDC/JWKS certificate
validation via `go-oidc/v3` on every inbound request, relying on `crypto/tls`
and `crypto/x509`. It also renders HTML content via `html/template` for error
pages and processes tar archives in certain upload paths via `archive/tar`.

The original `go-upgrade-stdlib-cves` proposal identified three CVEs in this
Go version. Since that proposal was written, seven additional CVEs have been
confirmed as affecting all Go 1.24.x releases:

| CVE | Package | Severity / Impact on mctl-api |
|---|---|---|
| CVE-2026-32280 | `crypto/x509` — cert chain DoS | High — JWKS/OIDC cert validation |
| CVE-2026-32282 | `os` — `Root.Chmod` symlink escape | Medium — build-time risk |
| CVE-2026-32283 | `crypto/tls` — TLS 1.3 key-update DoS | Critical — TLS termination |
| CVE-2026-32289 | `html/template` — XSS | Medium — error pages |
| CVE-2026-32288 | `archive/tar` — DoS via malformed archive | Medium — upload paths |
| CVE-2026-27140 | `cmd/go` — RCE via SWIG | High — CI/build pipeline risk |
| CVE-2026-27143 | `cmd/compile` — unsafe memory access | High — build pipeline risk |
| CVE-2026-27144 | `cmd/compile` — unsafe memory access | High — build pipeline risk |
| CVE-2026-33810 | `crypto/x509` — wildcard bypass | Critical — OIDC trust chain |

All ten CVEs are fixed by upgrading to go1.26.2 (released 2026-04-07, current
stable). None are backported to the EOL 1.24 branch.

Architecture reference: `context/architecture.md` — Go 1.24, modules,
Kubernetes + ArgoCD deployment on the `admins` tenant.

## Proposed solution

The upgrade is a pure toolchain and container-image bump. No application code
changes are required. The change set is identical in mechanism to the original
proposal but now carries the full ten-CVE scope in its CI validation:

1. **`go.mod` toolchain directive** — change the `go` directive to `go 1.26`
   and set `toolchain go1.26.2`. Run `go mod tidy` to reconcile any indirect
   dependency adjustments the new minimum Go version requires.

2. **Dockerfile build stage** — replace `FROM golang:1.24-alpine AS builder`
   with `FROM golang:1.26.2-alpine AS builder`. The distroless/Alpine runtime
   stage carries no Go toolchain and requires no change.

3. **CI workflow** — update all pinned `go-version: '1.24.x'` entries (in
   `actions/setup-go` or equivalent) to `go-version: '1.26.2'` so test, lint,
   vet, and build jobs use the exact same toolchain as the production image.

4. **CVE regression tests** — in addition to the TLS 1.3 key-update test
   required by the original proposal, add a test that presents a wildcard
   certificate to the OIDC verification path and asserts it is validated
   correctly (CVE-2026-33810 regression), and an `html/template` fuzz case
   confirming XSS payloads are escaped (CVE-2026-32289 regression).

The Go 1 compatibility guarantee covers all public stdlib APIs used by
chi/v5, pgx/v5, mcp-go, client-go, go-oidc, and prometheus/client_golang.
No breaking changes are expected; if `go mod tidy` surfaces a transitive
dependency requiring a minimum version bump, that bump is handled in the same
PR.

The ArgoCD `Application` for mctl-api on the `admins` tenant uses a rolling
update strategy with a `PodDisruptionBudget` of `minAvailable: 1`. Promotion
follows the normal GitOps path: image tag bump in Helm values → ArgoCD sync →
rolling pod replacement.

## Alternatives

**A. Apply the original proposal as-is and schedule a follow-up for the seven
new CVEs.**
This would close the original three CVEs now but leave seven (including the
critical CVE-2026-33810 wildcard bypass) open for another sprint. Given that
the fix action is identical (upgrade to go1.26.2) and the scope delta is only
additional CI regression tests, splitting into two PRs adds overhead with no
risk reduction benefit. Rejected.

**B. Stay on Go 1.24 and apply targeted runtime mitigations (WAF rules,
input sanitisation).**
CVE-2026-33810 and CVE-2026-32283 are in crypto primitives; WAF rules cannot
reliably block them. CVE-2026-27140/27143/27144 affect the build pipeline, not
the runtime, so runtime mitigations are inapplicable. No backports will be
issued for EOL Go 1.24. Rejected.

**C. Upgrade to Go 1.25 as an intermediate step.**
Go 1.25 fixes CVE-2026-32280, CVE-2026-32282, and CVE-2026-32289 but does not
include fixes for CVE-2026-32283, CVE-2026-33810, or the cmd/go and
cmd/compile CVEs (disclosed after 1.25's release). An intermediate hop would
require a second upgrade cycle within weeks and doubles the rollout risk.
Rejected in favour of jumping directly to go1.26.2.

## Platform impact

**Migrations**
None. The upgrade is toolchain and container-image only. No database schema
changes, Kubernetes CRD updates, or Vault policy changes are introduced.

**Backward compatibility**
The Go 1 compatibility guarantee covers all public stdlib APIs. All direct
dependencies (chi/v5, pgx/v5, mcp-go v0.31, client-go v0.32, go-oidc/v3,
prometheus/client_golang v1.23) support Go 1.26. Compatibility is verified by
`go mod tidy` and the full CI run required as part of this proposal.

**Resource impact**
Go 1.26 runtime memory and CPU profiles are comparable to 1.24 for this
workload. The `admins` tenant is not near its resource ceiling. The `labs`
tenant does not run mctl-api and is not affected at runtime. Shared CI
builders may experience a slightly larger Go toolchain image in their layer
cache, but this does not raise `labs` memory usage at runtime. No resource
risk flag required.

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|---|---|---|
| Transitive dependency requires `go 1.26` minimum, pulling in an incompatible API | Low | `go mod tidy` + full CI run on the feature branch catches this before merge |
| Behavioural change in `crypto/tls` or `crypto/x509` under 1.26 breaks OIDC or MCP auth | Low | Existing auth integration tests cover all three bearer-token paths; new CVE regression tests add targeted coverage |
| Rolling update leaves service degraded if new pods crash-loop | Low | PodDisruptionBudget (`minAvailable: 1`) keeps at least one old replica healthy; ArgoCD auto-rollback triggers on liveness failure |
| CVE-2026-33810 wildcard bypass already exploited before upgrade | Low-Medium | No external evidence of active exploitation; upgrade should be expedited to next available deploy window |
