# Design: issue-1195-security-dependency-maintenance-and-exac

## Current state
- `go.mod`: `go 1.26.11`, no `toolchain` line. Direct dependencies relevant to auth and MCP are
  `github.com/mark3labs/mcp-go v1.0.0`, `github.com/coreos/go-oidc/v3 v3.20.0`,
  `github.com/go-jose/go-jose/v4 v4.1.4`, `golang.org/x/oauth2 v0.36.0`, `golang.org/x/crypto v0.57.0`,
  `github.com/go-chi/httprate v0.15.0` and `github.com/go-chi/chi/v5 v5.3.2`. `golang.org/x/net v0.60.0`
  is indirect. According to `go mod why`, it reaches `internal/k8s` through `k8s.io/client-go/rest` and
  then `golang.org/x/net/http2`. `go mod verify` reports "all modules verified".
- `Dockerfile`: the builder is `golang:1.27.4-alpine@sha256:0a5f7fe7...` with `CGO_ENABLED=0`; the runtime
  is `alpine:3.24` (tag, not digest) plus `ca-certificates git openssh-client`. The binary ships at
  `/usr/local/bin/mctl-api`.
- `.github/workflows/security.yml`: a fail-closed `govulncheck ./...` (scanner pinned to v1.7.0, DB
  floating, Go from `go-version-file: go.mod`), then a Trivy fs scan v0.69.3 (SARIF report-only for
  HIGH and CRITICAL, gate on CRITICAL, `ignore-unfixed`). There is **no image scan** and **no
  binary-mode govulncheck**.
- `.github/workflows/validate.yml`: golangci-lint, plus `go test -p 2 -exec pgtestexec ./...` against
  Postgres 16, plus fail-closed bridge PG tests.
- `.github/dependabot.yml`: weekly gomod, github-actions and docker updates. There may already be open
  Dependabot PRs that duplicate the x/net bump, and the implementer must check this.
- Regression coverage already exists:
  - `internal/api/clientmeta.go` (`ParseTrustedProxyCIDRs`, `keyByTrustedIP`, `forwardedClientIP`)
    replaces `httprate.KeyByRealIP` so that a spoofed X-Forwarded-For cannot escape its bucket.
  - The tests for it are `internal/api/clientmeta_test.go` (`TestRateLimit_SpoofedXFFCannotEscapeBucket`,
    `TestRateLimit_TrustedProxySeparatesClients`, `TestClientIP_*`) and `internal/api/ratelimit_test.go`.
  - OAuth and auth tests are in `internal/auth/oauth_*_test.go`, `auth_test.go` and
    `federation*_test.go`. MCP tool-count and server tests are in `internal/mcp/server_test.go`.
- The SecurityFinding lifecycle is in `internal/securityfindings/` (finding `sf_`, occurrence `soc_`,
  observation `sob_`, remediation `sra_`, verification `svr_`) and `docs/security-findings.md`.
  Observations come in through `POST /api/v1/security/observations` (`internal/api/handlers_security_findings.go`).
  An occurrence subject needs a repository and at least one of `package_purl`, `path`, `location` or
  `artifact_digest`. An artifact digest makes the deployed-artifact state a separate occurrence from
  the source state.
- Investigation scan at `main` 0352f3af9e67c10bbc75f0ba12b368dd9434d848:
  - Settings: govulncheck v1.7.0, `-format json`, scan level symbol, go1.26.11, DB `https://vuln.go.dev`
    last modified 2026-11-24T15:56:00Z.
  - Result: 0 symbol-level (reachable) findings, 0 package-level-only findings, 3 module-level-only.
  - The module-level findings: `golang.org/x/net` v0.60.0, 2 advisories, fixed in v0.62.0;
    `github.com/mark3labs/mcp-go` v1.0.0, 1 advisory, fixed only in pseudo-version
    `v1.5.1-0.20261109144041-2f5b9637ea84`.
  - Advisory IDs are withheld here on purpose.
  - A rerun with `GOTOOLCHAIN=go1.27.4` failed while loading packages (govulncheck v1.7.0 cannot parse
    the 1.27 stdlib). The shipped toolchain's stdlib reachability is therefore **unknown**.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` lists the tenants admins, karabu, labs, namax66 and redloop, and has no
  `*/mctl-api/values.yaml`. mctl-api is not deployed as a catalogue tenant service in this checkout.
- `mctl_get_service_config(team=admins, service=mctl-api)` returned an error: "service not found:
  admins/mctl-api".
- So the deployed image tag or digest **could not be observed**. This does not mean nothing is
  deployed. The gap is listed under Open questions in requirements.md.

## Proposed solution
1. **Baseline reconciliation (evidence only).** Pin the work to one `main` SHA. Map each item of the
   privately supplied owner baseline to one of four states:
   - already fixed (the version in `go.mod` is at or above the fixed version);
   - duplicate (an open Dependabot PR, .github#222 or mctl-agents#809/#813);
   - fixable now;
   - exception candidate.

   Re-run govulncheck v1.7.0 with JSON output. Keep the raw JSON as a private artifact and publish
   only a summary table: level, module, current version and fixed version.
2. **Smallest dependency-only change.** Run `go get golang.org/x/net@v0.62.0` (or the lowest tagged
   fix, if the baseline shows a lower one), then `go mod tidy`. Only `go.mod` and `go.sum` should
   change. Accept any transitive bumps that minimum version selection forces (for example
   `golang.org/x/text`, `x/sys` or `x/crypto`), but list each one in the PR. If a forced bump touches
   an auth-relevant module (`x/crypto`, `x/oauth2`, `go-jose`, `go-oidc`, `mcp-go`), flag it for review.
3. **mcp-go stays at v1.0.0.** The finding is at module level only (the vulnerable symbols are not
   called). The only fix is an untagged pseudo-version several minor versions ahead, and adopting it
   would risk the MCP contract (`internal/mcp/server.go` and `server_test.go`). Record a SecurityFinding
   occurrence for it with:
   - `package_purl` pkg:golang/github.com/mark3labs/mcp-go@v1.0.0
   - repository mctlhq/mctl-api
   - an observation carrying the scan provenance
   - a proposed disposition of exception, with the justification "not reachable at symbol level",
     a review date, and the trigger "tagged upstream fix released".

   The exception takes effect only after owner approval.
4. **Verification at the exact candidate.**
   - Run CI as usual (validate and security workflows).
   - Run the targeted regression tests: `go test -count=1 ./internal/auth/... ./internal/mcp/...
     ./internal/api/ -run 'ClientIP|RateLimit|TrustedProxy|Loopback|OAuth'`.
   - Build the image locally or in CI from the candidate SHA and record its digest.
   - Scan the image by digest: govulncheck `-mode=binary` on the extracted `/usr/local/bin/mctl-api`.
     This covers the stdlib that go1.27.4 links, which closes the unknown above, assuming binary mode
     works with a go1.27 build; if it does not, the stdlib result stays explicitly unknown.
   - Run a Trivy image scan with a recorded Trivy version and DB timestamp.
   - Diff the before and after summaries. Any new finding blocks the candidate.
5. **Lifecycle recording.** Report each remaining or verified finding to the SecurityFinding store as
   an observation, with one occurrence for the source revision and one for the artifact digest. For the
   x/net fix, attach the remediation attempt (`sra_`) and a verification record (`svr_`) referencing
   the candidate SHA and digest.
6. **Follow-ups, recorded but not implemented here.** These need separate approval:
   - Align the `go.mod` `go` directive, the CI govulncheck toolchain and the Dockerfile builder.
   - Bump govulncheck once a release supports go1.27.
   - Add a binary or image scan job to `security.yml`.
   - Pin `alpine:3.24` by digest.

## Alternatives
- **Bump all dependencies to latest.** Rejected. This is not the smallest change, it widens the review
  surface across the auth and OAuth libraries, and the issue explicitly asks for minimal.
- **Adopt the mcp-go pseudo-version now.** Rejected. It is untagged and a large version jump on the MCP
  server core, the finding is not reachable, and it would risk the MCP tool contracts that
  `server_test.go` guards.
- **Fix the toolchain mismatch in the same PR (set `go 1.27.x` or change the builder).** Rejected for
  this slice. It is a build and release policy change and no longer dependency-only. It is recorded as
  a follow-up instead.

## Platform impact
- No migrations, API or contract changes, or config changes. Only `go.mod` and `go.sum` change.
- Risk: transitive bumps forced by x/net v0.62.0 could change HTTP/2 behaviour in the Kubernetes client
  (`internal/k8s`). The mitigation is the full test suite plus a check of the k8s client paths.
- Risk: the scans could expose stdlib findings in go1.27.4 that were never checked before. These are
  pre-existing and not new, so they should be recorded as baseline, not blocking, but they still need
  an owner disposition.
- Deployment is out of scope. Rollout follows the normal release-please process once the owner gives GO.
