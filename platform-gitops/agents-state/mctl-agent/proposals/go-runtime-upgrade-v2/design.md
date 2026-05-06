# Design: go-runtime-upgrade-v2

## Current state
mctl-agent v1.5.0 (see `context/current-version.md`) declares `go 1.24` in
`go.mod` and uses a `FROM golang:1.24-alpine` (or equivalent) base image in
its Dockerfile. The service depends on chi/v5 v5.2.1, google/go-github v68,
modernc.org/sqlite 1.34, and makes outbound TLS connections to the Anthropic
API and GitHub App endpoints on every alert processing cycle (see
`context/architecture.md`).

Three stdlib CVEs are active and unpatched in Go 1.24:

| CVE | Package | Category |
|---|---|---|
| CVE-2026-32283 | crypto/tls | TLS 1.3 deadlock DoS |
| CVE-2026-32280 | crypto/x509 | Certificate chain-building DoS |
| CVE-2026-32289 | html/template | XSS injection |

Go 1.24 will not receive backports. The crypto/tls and crypto/x509 packages
are exercised on every outbound call to the Anthropic API and GitHub App,
making the DoS vectors directly reachable by any party able to influence
those responses.

## Proposed solution

### go.mod changes
1. Update the `go` directive from `go 1.24` to `go 1.26.2`.
2. Add or update the `toolchain` line to `toolchain go1.26.2`.
3. Bump `github.com/go-chi/chi/v5` from v5.2.1 to v5.2.5. chi v5.2.5
   requires Go >= 1.22, which Go 1.26.2 satisfies. There are no breaking
   API changes between v5.2.1 and v5.2.5; the bump is additive bug-fix
   and minor-feature work only.
4. Run `go mod tidy` to regenerate `go.sum`.

### Dockerfile change
Update the builder stage base image from `golang:1.24-alpine` to
`golang:1.26.2-alpine`. The final (runtime) stage is not affected if it
uses a distroless or scratch image. If CI uses a separate toolchain pin
(e.g., a `.go-version` file or GitHub Actions `go-version` input) that pin
must also be updated to `1.26.2`.

### Why Go 1.26.2 specifically
Go maintains two supported release trains at any time. As of 2026-05-06,
1.26.x is the current train and 1.25.x is the previous train. Both fix the
CVEs, but adopting 1.26.2 avoids a second upgrade when 1.25.x reaches
end-of-life (expected late 2026). Go 1.26 also ships the Green Tea GC, which
reduces GC CPU overhead by 10-40% — a free benefit for a long-running service
under variable alert load, requiring no code changes.

### Why include the chi bump
chi v5.2.5 is the latest stable release and requires Go >= 1.22. Because
the toolchain upgrade satisfies that constraint and the API is fully
backward-compatible, bundling the bump avoids an extra PR, an extra CI run,
and an extra ArgoCD rollout.

### What is NOT changed
- google/go-github stays at v68. The next major version introduces breaking
  API changes that require code-level changes and are out of scope here.
- modernc.org/sqlite, uuid, and all other indirect dependencies stay at
  their current versions unless `go mod tidy` forces a patch.
- No application source code changes are expected. The Go 1.25 and 1.26
  release notes list no breaking changes affecting the patterns used in
  mctl-agent (HTTP handlers, slog, context cancellation, CGO-free SQLite).

## Alternatives

### A. Upgrade to Go 1.25.9 only
Also patches all three CVEs. Lower risk of any 1.26-specific change. However,
1.25.x will reach end-of-life approximately six months after 1.26 is out,
requiring a second identical upgrade soon. Rejected: the incremental risk
between 1.25.9 and 1.26.2 for this codebase is negligible and a second
upgrade adds CI and deployment cost.

### B. Vendor or monkey-patch the affected stdlib packages
Technically possible by copying patched `crypto/tls` and `crypto/x509`
sources into the repository. Non-idiomatic Go, breaks with any subsequent
toolchain bump, and creates a maintenance burden. Rejected: complexity far
outweighs the marginal safety of avoiding a toolchain bump.

### C. Stay on Go 1.24 and accept the CVE risk temporarily
Acceptable only as a measured interim of days while the upgrade is scheduled,
not as a steady state. With two DoS CVEs on active TLS paths and one XSS CVE
in html/template, the exposure is material. Rejected as a longer-term
strategy.

## Platform impact

### Migrations
None. Go toolchain upgrades are transparent to the Kubernetes deployment. The
binary is rebuilt by the CI pipeline; the existing ArgoCD rollout strategy
(rolling update) applies without manifest changes.

### Backward compatibility
The compiled binary is API-compatible. All existing REST endpoints, MCP
tools, AlertManager webhook handlers, and Telegram webhook handlers behave
identically. chi v5.2.5 is backward-compatible with v5.2.1 at the handler
and middleware API level.

### Resource impact
Go 1.26 Green Tea GC is expected to reduce GC CPU usage. Memory footprint
should remain flat or marginally decrease. **No impact on the `labs` tenant**
— mctl-agent runs exclusively in the `admins` tenant. This proposal does not
flag any resource risk for `labs`.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Compilation error due to a deprecated stdlib symbol in Go 1.25/1.26 | Low | `go vet ./...` gate in CI before merge |
| Test flakiness from GC timing changes introduced by Green Tea GC | Very low | Run test suite three times in CI to surface flakes |
| Dockerfile build stage fails to pull `golang:1.26.2-alpine` image | Low | Pin image digest in Dockerfile; verify in PR pipeline before merge |
| chi v5.2.5 introduces an unexpected behaviour change | Very low | Full regression suite covers all router paths; chi changelog reviewed |
| go mod tidy pulls in an unvetted indirect dependency upgrade | Low | Review `go.sum` diff in the PR; restrict to patch-level indirect bumps |
