# Design: go-runtime-upgrade-v2

## Current state
`go.mod` declares `go 1.24` and `toolchain go1.24.x`. The CI pipeline (GitHub Actions / ArgoCD)
pulls the Go toolchain specified in `go.mod`. The container image uses an official `golang:1.24`
base image for the build stage.

mctl-api's HTTP surface — REST + MCP Streamable HTTP — uses `net/http`, `net/http/httputil`
(reverse proxy to upstream services), and `crypto/tls`. All three are directly affected by CVEs
patched in the 1.26.2–1.26.3 cycle. The service also uses `html/template` for any server-side
rendered error pages or documentation (XSS CVEs in that package apply).

## Proposed solution
**Pin the toolchain to Go 1.26.3** via a two-line change to `go.mod`:

```
go 1.26.3
toolchain go1.26.3
```

Update the Dockerfile build stage from `golang:1.24-alpine` to `golang:1.26.3-alpine` (or
equivalent slim image).

**Why not a floating `go 1.26`?**
The `toolchain` directive in Go 1.21+ selects an exact toolchain, not a range. Floating leaves
open the possibility of picking up a pre-release toolchain automatically. Pinning to `go1.26.3`
ensures reproducibility and guarantees the CVE patches are present.

**Dependency compatibility:** Go's compatibility guarantee covers 1.24 → 1.26 with no expected
API breaks. `go mod tidy` after the bump will surface any dependency that requires a newer
minimum; these must be resolved (typically a `go get` bump) before merging.

**GC:** Go 1.26's "Green Tea" GC is enabled by default. No GOGC or GOMEMLIMIT changes are
required to benefit from the reduced pause times. Existing Prometheus GC metrics will
automatically reflect the improvement.

## Alternatives

### Stay on Go 1.24 and apply individual stdlib CVE workarounds
Not viable: crypto/tls and net/http patches require a toolchain rebuild; there is no
user-space mitigation for compiler/linker CVEs (CVE-2026-27140, CVE-2026-27143).

### Upgrade to Go 1.25.10 (LTS-equivalent patch)
Go 1.25.10 closes the same CVE set but is already out of the two-release support window (1.26 and
1.25). Building on an older version accumulates future drift immediately. Rejected in favour of
the current latest stable (1.26.3).

### Upgrade to Go 1.27 RC
Pre-release toolchains are not production-safe. Rejected.

## Platform impact
- **Migrations:** `go.mod` + `go.sum` update; Dockerfile base image tag update.
- **Backward compatibility:** Go 1 compatibility guarantee; no breaking changes expected.
  `go vet` and `staticcheck` may surface new warnings with the newer toolchain — these must be
  addressed before merge.
- **Resource impact:** Go 1.26 Green Tea GC is expected to reduce heap fragmentation, which may
  lower steady-state memory usage. No increase expected. `labs` tenant not affected (mctl-api
  runs in `admins`).
- **Risks and mitigations:**
  - Risk: A transitive dependency may set `go 1.25+` minimum and fail `go mod tidy`. Mitigation:
    run `go mod tidy` locally in step 1 and resolve before CI.
  - Risk: New default behavior in `net/http` (e.g., GODEBUG defaults) may change connection
    handling subtly. Mitigation: full integration test run plus 24-hour staging observation.
  - Risk: Green Tea GC may behave differently under bursty MCP streaming loads. Mitigation:
    load test in staging before production promotion.
