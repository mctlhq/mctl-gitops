# Design: go-toolchain-security-upgrade

## Current state
mctl-agent (see `context/architecture.md`, `context/current-version.md`)
is a single-pod Go service in tenant `admins`, currently at version
1.5.0, built with Go 1.24. It makes outbound TLS connections to the
Anthropic API and GitHub API, and receives inbound webhooks from
AlertManager and Telegram over HTTPS terminated in front of the
service. The build pipeline uses `cmd/go` to resolve and fetch modules
from a proxy. None of this depends on Go-version-specific language
features beyond what 1.24 already provides.

## Proposed solution
Bump the toolchain declaration in `go.mod`:

```
go 1.27.0
toolchain go1.27.0
```

and update the container build image (Dockerfile `FROM golang:1.27...`
build stage) and any CI workflow file that pins a Go version to match.
No source-level API changes are required unless the build surfaces new
`go vet`/compiler diagnostics under 1.27, in which case those are fixed
as narrowly as possible (formatting/vet-only fixes, not refactors).

Rollout is a single dependency-bump PR: update `go.mod`/`go.sum` (via
`go mod tidy` under the new toolchain, which should be a no-op for
`go.sum` since no module dependency versions change), rebuild the
container image, run the full test suite and `go vet ./...`, then
deploy through the normal ArgoCD sync path for `admins-mctl-agent`.

## Alternatives
1. **Do nothing / wait for next Go LTS.** Rejected: the CVE set
   (crypto/tls, crypto/x509, cmd/go) is actively exploitable in a
   service that makes and receives many TLS connections; deferring
   leaves known, fixed vulnerabilities in production.
2. **Backport/patch only the specific CVE fixes via vendoring.**
   Rejected: Go stdlib is not designed to be selectively patched
   in-tree; this would require forking the standard library, which is
   far higher effort and higher risk than a toolchain bump, for no
   benefit over just adopting the upstream fix release.
3. **Jump straight to a Go version beyond 1.27.0 pre-emptively.**
   Rejected: 1.27.0 is the latest stable release as of this proposal;
   there is nothing newer to target, and chasing unreleased versions
   is out of scope for a maintenance bump.

## Platform impact
- **Migrations:** none. No data schema, ticket schema, or API contract
  changes.
- **Backward compatibility:** fully compatible — this is a toolchain
  bump, not a dependency API bump. The service's external behavior is
  unchanged.
- **Resource impact (tenant `labs`):** none. This proposal touches only
  the `admins`-tenant mctl-agent binary and build pipeline; it does not
  deploy to or affect tenant `labs` in any way, so it carries no risk
  to `labs`'s memory headroom.
- **Resource impact (tenant `admins`):** expected to be neutral to
  slightly positive (Go releases generally improve GC/runtime
  efficiency); no CPU/memory increase anticipated. Current `admins`
  tenant usage (6500m/10 CPU, 3200Mi/5Gi memory per latest metrics) has
  ample headroom regardless.
- **Risks and mitigations:**
  - *Risk:* a first-party file fails to compile or `go vet` flags new
    issues under 1.27.0. *Mitigation:* run the full build + test suite
    + `go vet ./...` locally and in CI before merge; fix any breaks as
    part of this same PR, scoped narrowly.
  - *Risk:* CI/build image pin and `go.mod` pin drift apart.
    *Mitigation:* explicit task to update both in the same PR; add a
    CI check (or note in review checklist) that the Dockerfile Go
    version and `go.mod` `go`/`toolchain` directives match.
  - *Risk:* GOTOOLCHAIN auto-download behavior pulls a different patch
    version than tested in CI. *Mitigation:* pin an exact
    `toolchain go1.27.0` (or the latest available patch at merge time)
    rather than a floating `go 1.27` directive alone.
