# Design: bump-go-toolchain

## Current state
`context/architecture.md` records the agent's tech stack as **Go 1.24**. The Go version is
declared in three places:

1. `go.mod` — `go 1.24` directive at the top of the module file.
2. `Dockerfile` — base image (e.g., `golang:1.24-alpine` for the build stage).
3. CI workflow (GitHub Actions or equivalent) — `go-version` input to `actions/setup-go`.

Go 1.24 does not include the fixes for CVE-2026-32280 and CVE-2026-32281 in `crypto/x509`. Both
CVEs were fixed in Go 1.26.2 (and 1.25.9). The agent makes continuous outbound TLS calls to
`api.github.com` and the Anthropic API, meaning the vulnerable code path is exercised on every
remediation cycle.

## Proposed solution
Bump the Go toolchain from 1.24 to 1.26.2 by updating all three declaration points:

1. `go.mod`: change the `go` directive to `go 1.26.2`.
2. `Dockerfile`: update the build-stage base image to `golang:1.26.2-alpine` (or the distroless
   equivalent in use). The runtime/final stage image is not a Go image and is unaffected.
3. CI workflow: update `go-version: "1.26.2"` in the setup step.

After the toolchain change, run `go mod tidy` to ensure module graph consistency with the new
minimum version. No application-level code changes are expected; Go 1.26 maintains backward
compatibility with all code valid under Go 1.24.

**Ordering note:** This proposal should be applied before `bump-chi` (Upgrade chi v5.2.1 to
v5.2.5), because chi v5.2.5 declares a minimum Go version of 1.22 and is most cleanly adopted once
the toolchain is already at 1.26. There is no strict technical blockage — chi v5.2.5 will compile
with Go 1.24 — but aligning the toolchain first reduces the risk of subtle toolchain-version
interactions.

## Alternatives

### A. Upgrade to Go 1.25.9 (the other patched branch)
Ruled out: 1.26.2 is the current stable release and will receive security patches for longer.
Adopting 1.25.9 would require a second upgrade in the near term. The incremental effort is the
same; taking 1.26.2 directly is the correct choice.

### B. Apply a custom `crypto/x509` patch to the existing 1.24 toolchain
Ruled out: Go does not support patching individual standard-library packages without rebuilding the
toolchain from source. This approach is operationally complex, not reproducible in CI, and creates
a non-standard build that will confuse future maintainers.

### C. Mitigate at the network layer (e.g., restrict outbound TLS to known CAs only)
Partially valid but insufficient: even with CA pinning, the agent must perform chain validation, and
the CVE is triggered during that validation. Network-layer controls do not prevent a compromised
intermediate CA in the trusted chain from triggering the vulnerability. This can be a complementary
defence-in-depth measure but is not a substitute for patching the toolchain.

## Platform impact

### Migrations
No database schema changes. No Kubernetes manifest changes beyond the Dockerfile base image.
No environment variable or secret changes.

### Backward compatibility
Go guarantees backward compatibility for all code targeting Go 1.x. Code valid under Go 1.24
compiles unchanged under Go 1.26. No application-level changes are anticipated.

### Resource impact (`labs` tenant)
This is a pure build-toolchain upgrade. The compiled binary size and runtime memory footprint are
not materially changed by a toolchain version bump. The `labs` tenant memory limit is not at risk;
this proposal is not flagged as risky for `labs`.

### Risks and mitigations
- **Subtle standard-library behavior changes:** Go 1.25 and 1.26 include changes to `net/http`,
  `net/url`, and `html/template`. Mitigation: run the full test suite after the toolchain change
  and review the Go 1.25 and 1.26 release notes for any behavior changes relevant to the agent's
  HTTP handling.
- **Dockerfile base image availability:** The `golang:1.26.2-alpine` image must be available in
  the container registry used by CI. Mitigation: verify image availability before merging.
- **CI cache invalidation:** The Go module cache in CI will be invalidated by the toolchain change,
  causing a slower first build. This is cosmetic and not a risk.
