# Design: go-1.24-eol-unpatched-cve

## Current state
Per `context/architecture.md`, mctl-api is built with Go 1.24. The Go project patches only the two
most recently released major versions; since Go 1.26.0 shipped (2026-02-10), 1.24 no longer
receives stdlib/crypto/runtime security fixes. Go 1.27.0 shipped 2026-08-19. CVE-2026-42507
(`net/textproto` error-injection) is fixed in 1.25.11 and 1.26.4 only — there is no 1.24.x patch
and there will never be one. mctl-api's own error-handling and logging paths, and any dependency
using `net/textproto` (e.g. HTTP client code paths reached via ArgoCD/Backstage integrations),
inherit this exposure. Nine prior proposals targeting a Go upgrade exist under `proposals/`
(`go-runtime-upgrade`, `go-runtime-upgrade-v2`, `go-runtime-cve-dos`, `go-runtime-cve-upgrade`,
`go-upgrade`, `go-upgrade-1262`, `go-upgrade-stdlib-cves`, `go-upgrade-stdlib-cves-v2`,
`go-toolchain-ace-cve-27140`), none merged. `go-runtime-upgrade-v2` is the most complete and
already targets 1.26.3 to close a batch of other CVEs (CVE-2026-27140, CVE-2026-32283,
CVE-2026-33814, partial CVE-2026-39825 coverage).

## Proposed solution
Rather than draft a tenth parallel toolchain-bump proposal, this proposal frames the ask as an
**escalation**: the Go 1.24 EOL condition is now structural (permanent, not a single-CVE gap), and
the fix mechanism is identical to what `go-runtime-upgrade-v2` already specifies — bump
`go.mod`'s `go` directive and `toolchain` pin, update the Dockerfile base image, resolve
dependency minimum-version conflicts, and re-run the full test/load-test/soak sequence.

The target version is at minimum **1.26.4** (the first 1.26.x patch that includes the
CVE-2026-42507 fix; 1.26.3 alone, as targeted by `go-runtime-upgrade-v2`, does not close this
specific CVE). Since Go 1.27.0 has now shipped, upgrading straight to the latest 1.27.x patch is
preferable to minimize how soon the next EOL cliff is hit, but 1.26.4+ is the acceptable floor if
1.27 introduces unreviewed risk. This proposal recommends: merge `go-runtime-upgrade-v2`'s
mechanism with the target bumped to at least 1.26.4 (or 1.27.x if the team prefers to also absorb
that jump now), and close the remaining eight superseded drafts.

## Alternatives
1. **Selectively backport just the `net/textproto` fix into a vendored patch on Go 1.24.** Rejected
   — the Go toolchain is not designed for local patching of stdlib; this creates an unsupportable
   fork and does nothing for the *next* EOL-driven CVE, which is guaranteed to recur every few
   months as long as mctl-api stays on 1.24.
2. **Wait and bundle this with a larger, less-frequent "major Go upgrade" initiative.** Rejected —
   this is exactly the reasoning that has stalled nine prior proposals; the gap is now permanent
   and worsening (three majors behind, zero patches for 6+ months).
3. **Target Go 1.27.0 directly instead of 1.26.4.** Viable and arguably better long-term (buys the
   most runway before the next EOL), but carries more unreviewed surface area on a brand-new major
   than a 1.26.4 patch bump. Recommendation: 1.26.4 as the safe floor, 1.27.x acceptable if the
   team accepts the slightly larger diff; not rejected outright, called out as an open decision for
   whoever executes this proposal.

## Platform impact
- **Migrations:** None — toolchain/runtime change only, no data or schema impact.
- **Backward compatibility:** No API surface changes. Dependency minimum-version conflicts, if
  any, must be resolved before merge (see `tasks.md`).
- **Resource impact:** Expected neutral-to-positive (Go 1.26's "Green Tea" GC reduces pause
  overhead per prior research). mctl-api runs only in the `admins` tenant — **no `labs` resource
  impact**.
- **Risks and mitigations:**
  - Risk: a transitive dependency requires a Go version incompatible with the chosen target.
    Mitigation: dependency audit task before the toolchain bump is finalized.
  - Risk: performance regression from the runtime change. Mitigation: staging load test comparing
    Prometheus p50/p99 latency and GC metrics against the 1.24 baseline before promotion.
  - Risk: continuing to accumulate parallel proposals instead of merging one. Mitigation: this
    proposal explicitly calls for closing the eight other unmerged Go-upgrade proposals once this
    one is accepted.
