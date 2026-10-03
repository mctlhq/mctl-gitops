# Design: x-crypto-ssh-transitive-audit-v2

## Current state
Per `context/architecture.md`, mctl-agent's direct dependencies are Go 1.24,
`go-chi/chi v5.2.1`, `google/go-github v68`, `modernc.org/sqlite 1.34`, `uuid 1.6`,
`slog` (stdlib), and `anthropic-sdk-go`. None declare `golang.org/x/crypto` directly.
The original `x-crypto-ssh-transitive-audit` proposal already scopes the mechanism to
answer "is `x/crypto/ssh` in our build graph, and is it reachable" against six CVEs
disclosed 2026-09-15. This cycle's research surfaced a seventh, CVE-2026-39830 (SSH
peer floods an internal buffer via unsolicited global-request responses, stalling the
connection's read loop), in the same `x/crypto/ssh` package family as the already-
tracked CVE-2026-39827/39829 resource-exhaustion issues.

## Proposed solution
1. Check whether the original audit (`x-crypto-ssh-transitive-audit`) has already run
   and produced a `go mod graph` / `go list -m all` snapshot, and whether `go.sum` has
   changed since. If unchanged, reuse that module-graph evidence directly instead of
   re-running the enumeration step.
2. Re-run `govulncheck ./...` (this is the step that must be repeated, since
   `govulncheck`'s vulnerability database needs to include CVE-2026-39830, which did
   not exist at the time of the original audit) and check its output for
   CVE-2026-39830 specifically, alongside re-confirming the original six.
3. Branch on the combined result exactly as the original audit does:
   - **Not present / present but unreachable (for all seven CVEs):** update the
     original audit's "not exposed" documentation with the expanded CVE list and the
     new `govulncheck` output as evidence; no code change.
   - **Present and reachable (for any of the seven):** identify the minimal fix (bump
     the upstream module that pulls in `x/crypto/ssh`, or add/raise a direct
     `require golang.org/x/crypto` line in mctl-agent's own `go.mod` to force
     resolution to a version that fixes all seven CVEs at once, not just
     CVE-2026-39830 in isolation).
4. Record the outcome as an update to the original audit's tracking PR/issue (cross-
   referenced from this proposal), so the CVE list a given `x/crypto` resolution has
   been checked against stays in one traceable place rather than fragmenting across
   `-v2`, `-v3`, etc. proposals with no linkage.
5. Re-affirm the original audit's standing checklist item: any future bump of
   `go-chi/chi`, `google/go-github`, or `anthropic-sdk-go` should re-trigger this
   question, now against whatever the current CVE list is at that time.

## Alternatives
- **Open a brand-new, independent audit proposal instead of an explicit `-v2` of the
  existing one.** Rejected: the audit mechanism (`go mod graph` + `govulncheck`) is
  identical; treating this as a from-scratch proposal would duplicate the module-graph
  enumeration step for no benefit and fragment the audit trail across unrelated
  documents.
- **Fold CVE-2026-39830 into the original proposal's files directly (edit in place)
  instead of creating a `-v2`.** Rejected: the original proposal may already be
  in-flight or closed as a PR; per the spec-writer workflow, an already-existing slug
  is extended via a `-v2` folder rather than mutated, preserving the original as a
  historical record of what was checked at the time.
- **Skip the re-audit and assume the original "not exposed" finding (if that's what it
  concluded) still holds for the new CVE too.** Rejected: CVE-2026-39830 could in
  principle be reachable via a different code path than the original six (e.g. if it
  affects client-side behavior the others don't); the audit is cheap enough (a
  `govulncheck` re-run) that assuming coverage without checking is not justified.

## Platform impact
- **Migrations:** none.
- **Backward compatibility:** none, unless remediation requires a module bump, in which
  case compatibility is scoped to that module's own release notes (chi's bump is
  tracked separately by `chi-v532-mount-route-fix` / `chi-redirect-cve-boundary-check`;
  go-github/anthropic-sdk-go bumps would be evaluated on their own if triggered here).
- **Resource impact:** negligible — audit-only unless remediation is triggered, in which
  case impact matches whatever module needs bumping. Not deployed to `labs`
  (mctl-agent runs only in `admins`), so no `labs` memory-pressure concern.
- **Risks and mitigations:**
  - *Risk:* reusing the original audit's module-graph snapshot could miss a dependency
    change that happened between the two audits. *Mitigation:* explicitly check
    `go.sum` diff / git history before deciding to reuse vs. re-run the enumeration
    step (task 1); when in doubt, re-run it — it's cheap.
  - *Risk:* if remediation is needed via forcing a direct `x/crypto` requirement, this
    could conflict with a version another module expects. *Mitigation:* run
    `go mod tidy` and the full test suite after any version pin change; treat any
    build/test failure as blocking.
