# Design: x-crypto-ssh-transitive-audit

## Current state
Per `context/architecture.md`, mctl-agent's direct dependency list is: Go 1.24,
`go-chi/chi v5.2.1`, `google/go-github v68`, `modernc.org/sqlite 1.34`, `uuid 1.6`,
`slog` (stdlib), and the Anthropic SDK (`anthropic-sdk-go`). None of these are SSH
clients/servers by design, but Go module graphs commonly pull in `golang.org/x/crypto`
transitively (e.g., via `golang.org/x/crypto/ssh/terminal`-adjacent tooling, or as a
shared dependency of unrelated packages). We currently have no documented, up-to-date
answer to "do we ship `x/crypto/ssh` in our binary, and is it reachable." This is a gap
given the 2026-09-15 CVE cluster, and given that mctl-agent exposes several
network-facing endpoints where a resource-exhaustion vulnerability (CVE-2026-39829,
CVE-2026-39827) would be directly relevant if reachable.

## Proposed solution
1. Run `go list -m all` and `go mod graph` against mctl-agent's `go.mod`/`go.sum` to
   enumerate every module in the build graph, then `grep` for `golang.org/x/crypto`.
2. For each hit, resolve the requiring module (which of `chi`, `go-github`,
   `anthropic-sdk-go`, or something else pulls it in) and the specific subpackage
   (`x/crypto/ssh`, `x/crypto/bcrypt`, `x/crypto/nacl`, etc.) — only `x/crypto/ssh` is
   relevant to this CVE cluster; other subpackages under `x/crypto` are out of scope
   for these particular CVEs.
2b. Optionally corroborate with `govulncheck ./...` (part of the standard Go
    toolchain), which performs reachability analysis (not just "is it in go.sum" but
    "is the vulnerable function actually called"), giving a stronger signal than
    `go list`/`go mod graph` alone.
3. Branch on result:
   - **Not present / present but unreachable:** document the `go mod graph` /
     `govulncheck` output as evidence in the tracking PR or an ADR-style note; no code
     change.
   - **Present and reachable:** identify the minimal fix — either the upstream module
     (`chi`, `go-github`, `anthropic-sdk-go`) has already bumped its own `x/crypto`
     requirement in a newer release (in which case bumping that module resolves it,
     coordinate with the `chi-redirect-cve-boundary-check` proposal if `chi` is the
     source), or we add/raise an explicit `require golang.org/x/crypto` line in our own
     `go.mod` via `go get golang.org/x/crypto@latest` to force module resolution to a
     patched version (Go's minimal version selection allows a direct requirement to
     override a transitive one).
4. Record the outcome so future dependency bumps of the three flagged modules
   automatically re-trigger this question (documented as a standing checklist item,
   not automated tooling, in this proposal's scope).

## Alternatives
- **Assume "not on our explicit dependency list" means "not exposed" and skip the
  audit.** Rejected: this is exactly the reasoning gap the CVE disclosure exposes —
  transitive dependencies are invisible without actually inspecting the module graph,
  and the cost of checking is near zero (~minutes) against a real CPU/memory-exhaustion
  risk on network-facing endpoints.
- **Preemptively add a direct `golang.org/x/crypto` pin to `go.mod` regardless of
  audit outcome, "just to be safe."** Rejected: adds an unnecessary direct dependency
  and maintenance surface if the module isn't actually in our graph at all; prefer to
  gate the pin on the audit's actual finding.
- **Wait for `govulncheck` to be added to CI as a general practice before checking this
  specific CVE cluster.** Rejected: this CVE cluster is time-sensitive (disclosed 4 days
  ago as of this proposal) and the manual audit is fast; CI integration of
  `govulncheck` is worth a separate, non-urgent follow-up proposal rather than blocking
  this one.

## Platform impact
- **Migrations:** none.
- **Backward compatibility:** none, unless remediation requires a module bump, in
  which case compatibility is scoped to that module's own release notes (chi's bump is
  already covered by the sibling `chi-redirect-cve-boundary-check` proposal;
  go-github/anthropic-sdk-go bumps would be evaluated on their own if needed).
- **Resource impact:** negligible — this is an audit task, not a runtime change, unless
  remediation is triggered, in which case impact matches whatever module needs
  bumping. Not deployed to `labs` (mctl-agent runs only in `admins`), so no `labs`
  memory-pressure concern.
- **Risks and mitigations:**
  - *Risk:* audit concludes "not exposed" based on `go list`/`go mod graph` alone but
    misses a reachability nuance. *Mitigation:* corroborate with `govulncheck`, which
    does call-graph reachability analysis rather than pure module-graph presence.
  - *Risk:* if remediation is needed via forcing a direct `x/crypto` requirement, this
    could conflict with the resolved version another module expects. *Mitigation:*
    run `go mod tidy` and the full test suite after any version pin change; treat any
    build/test failure as blocking.
