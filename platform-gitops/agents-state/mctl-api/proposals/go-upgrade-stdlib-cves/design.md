# Design: go-upgrade-stdlib-cves

## Current state

mctl-api v4.14.0 is compiled with Go 1.24 (last patch go1.24.13, 2026-02-04).
The Dockerfile uses a `golang:1.24-alpine` build stage and a distroless or
Alpine runtime image. The service handles TLS termination for all inbound
connections and performs OIDC/JWKS certificate validation via `go-oidc/v3`,
both of which rely on `crypto/tls` and `crypto/x509` from the standard library.

Three CVEs are present in all Go 1.24.x releases and are not backported:

| CVE | Package | Impact on mctl-api |
|---|---|---|
| CVE-2026-32280 | `crypto/x509` — cert chain DoS | JWKS/OIDC cert validation path |
| CVE-2026-32282 | `os` — `Root.Chmod` symlink escape | Lower severity; no direct exploit surface |
| CVE-2026-32283 | `crypto/tls` — TLS 1.3 key-update DoS | Direct: TLS termination on every request |

Go upstream has designated Go 1.26.2 (2026-04-07) as the fix release.
Go 1.24 has reached the end of its two-minor-version support window and will
receive no further security patches.

Architecture reference: `context/architecture.md` — Go 1.24, modules,
Kubernetes + ArgoCD deployment on the `admins` tenant.

## Proposed solution

Bump the Go toolchain from 1.24 to 1.26.2 by updating two artefacts:

1. **`go.mod` toolchain directive** — change `go 1.24` / `toolchain go1.24.x`
   to `go 1.26` / `toolchain go1.26.2`. Run `go mod tidy` to pick up any
   indirect dependency adjustments the new toolchain requires.

2. **Dockerfile build stage** — replace `FROM golang:1.24-alpine AS builder`
   with `FROM golang:1.26.2-alpine AS builder`. The runtime stage (distroless
   or Alpine) does not carry the Go toolchain and requires no change unless a
   glibc/musl version constraint is introduced, which is unlikely between 1.24
   and 1.26.

3. **CI workflow** — update any pinned `go-version` matrix entries
   (`actions/setup-go` or equivalent) from `1.24.x` to `1.26.2` so the test
   and lint jobs run against the same toolchain used in production.

No application code changes are anticipated. Go 1.25 and 1.26 maintain strong
backward compatibility per the Go 1 compatibility guarantee. If `go mod tidy`
reveals a transitive module that requires a newer minimum Go version,
individual module bumps will be handled as a follow-up within the same PR.

The ArgoCD `Application` for mctl-api in the `admins` tenant is configured with
a rolling update strategy and a `PodDisruptionBudget` of `minAvailable: 1`.
The upgraded image will be promoted through the normal GitOps pipeline:
image tag bump in the Helm values file → ArgoCD sync → rolling replacement of
pods one at a time.

## Alternatives

**A. Stay on Go 1.24 and apply targeted patches**
Go's security team has stated that CVE-2026-32280 and CVE-2026-32283 will not
be backported to 1.24. A private patch would need to be maintained against the
full stdlib source, creating an ongoing maintenance burden and making future
upgrades harder. Rejected.

**B. Offload TLS termination to an ingress / envoy sidecar**
Moving TLS to a network-layer component would eliminate CVE-2026-32283's
direct exposure in mctl-api. However, this is a significant architectural
change (changes to the auth flow, mTLS header trust, MCP Streamable HTTP
requirements) that far exceeds the effort justified by a single CVE.
Rejected for this proposal; may be revisited independently.

**C. Upgrade to Go 1.25 (rather than 1.26.2)**
Go 1.25 contains fixes for CVE-2026-32280 and CVE-2026-32282 but not for
CVE-2026-32283, which was disclosed after 1.25's release. Upgrading to 1.25
would require a second upgrade cycle shortly after. Rejected in favour of
going directly to the current stable release.

## Platform impact

**Migrations**
None. The upgrade is purely at the toolchain and container-image level. No
database schema changes, no Kubernetes CRD changes, no Vault policy changes.

**Backward compatibility**
The Go 1 compatibility guarantee covers all public stdlib APIs. chi/v5,
pgx/v5, mcp-go, client-go, go-oidc, and prometheus/client_golang all support
Go 1.26 (verify via `go mod tidy` and CI). No breaking changes are expected.

**Resource impact**
Go 1.26 runtime memory and CPU profiles are comparable to 1.24 for this
workload. The `admins` tenant is not near its resource ceiling.

The `labs` tenant does not run mctl-api and is not directly affected by this
change. However, if shared CI runners are used, the larger Go 1.26.2 toolchain
image may increase build cache pressure. This is a low risk and does not push
`labs` closer to its memory limit at runtime. No resource flag required.

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|---|---|---|
| A transitive dependency sets `go 1.26` minimum and pulls in an incompatible API | Low | `go mod tidy` + full CI run before merge catches this |
| Subtle behavioural change in `crypto/tls` under 1.26 breaks the OIDC or MCP auth flow | Low | Existing integration tests cover auth paths; add a TLS 1.3 key-update test (see tasks) |
| Rolling update leaves service degraded if new pods crash-loop | Low | PodDisruptionBudget ensures at least one old replica stays until new ones are healthy; ArgoCD auto-rollback on liveness failure |
