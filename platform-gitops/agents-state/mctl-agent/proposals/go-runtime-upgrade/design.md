# Design: go-runtime-upgrade

## Current state
mctl-agent declares `go 1.24` in `go.mod` (see `context/current-version.md` — v1.5.0, last updated 2026-04-27). The Go 1.24 toolchain is used in CI and in the container build stage. Three CVEs in `crypto/tls` (CVE-2026-32283) and `crypto/x509` (CVE-2026-32280, CVE-2026-32281) remain unpatched in 1.24. These affect every Go binary that uses TLS.

## Proposed solution
Bump the Go toolchain declaration in `go.mod` from `go 1.24` to `go 1.26.2`, and update the corresponding toolchain pin in `go.mod` (`toolchain go1.26.2`). Update any `FROM golang:1.24` image references in `Dockerfile` / CI pipeline to `golang:1.26.2`. Run `go mod tidy` to regenerate `go.sum`.

No application code changes are expected. The Go 1.25 and 1.26 release notes list no breaking changes that affect chi, go-github, modernc.org/sqlite, or the standard patterns used in mctl-agent (HTTP handlers, slog, context cancellation). A full CI run (unit tests + integration tests) will confirm compatibility.

**Why Go 1.26.2 specifically (not 1.25.x)?**
Go maintains two supported release trains at any time. As of 2026-05-03, 1.26.x is the current train and 1.25.x is the prior supported train. Both receive security patches; however, 1.26.2 also ships the Green Tea GC and faster runtime, giving a free performance benefit alongside the security fix. Adopting the current train avoids a second upgrade in a few months.

## Alternatives

### A. Upgrade to Go 1.25.9 only
Fixes the three CVEs without introducing any 1.26-specific changes. Lower risk, but requires a second upgrade when 1.25.x reaches end-of-life. Rejected — the delta between 1.25.x and 1.26.x for mctl-agent is minimal, and a second upgrade has its own CI cost.

### B. Vendor the patched `crypto/tls` and `crypto/x509` packages without upgrading Go
Technically possible but fragile — vendoring standard-library packages is non-idiomatic Go and breaks with any subsequent toolchain bump. Rejected — adds complexity with no benefit over a simple toolchain upgrade.

### C. Stay on Go 1.24, accept risk
Acceptable only as a very short-term interim while the upgrade is scheduled. With TLS DoS CVEs active and mctl-agent exposed on public HTTPS endpoints, this is not an acceptable steady state. Rejected.

## Platform impact

### Migrations
None — Go toolchain upgrades are transparent to the Kubernetes deployment. The binary is rebuilt and the existing deployment rollout strategy applies.

### Backward compatibility
The compiled binary remains API-compatible. All existing REST endpoints, MCP tools, and webhook handlers behave identically.

### Resource impact
Green Tea GC is expected to reduce GC CPU overhead by 10–40 %. Memory footprint should remain flat or decrease slightly. **No impact on the `labs` tenant** — mctl-agent runs in `admins`.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| Compilation error due to deprecated stdlib symbol | Low | `go vet` + full CI run before merge |
| Test flakiness from timing changes in new GC | Very Low | Run test suite 3× in CI to detect flakes |
| Dockerfile build stage fails to pull `golang:1.26.2` | Low | Pin digest in Dockerfile; test in PR pipeline |
