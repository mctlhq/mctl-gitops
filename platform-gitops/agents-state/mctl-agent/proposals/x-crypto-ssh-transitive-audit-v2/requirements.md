# Re-verify x/crypto/ssh transitive exposure against CVE-2026-39830 (audit v2)

## Context
The existing proposal `x-crypto-ssh-transitive-audit` scopes a `go list -m all` /
`go mod graph` / `govulncheck` audit to determine whether mctl-agent's dependency graph
(via `go-chi/chi`, `google/go-github`, or `anthropic-sdk-go`) transitively pulls in
`golang.org/x/crypto/ssh`, and if so, whether it is reachable and needs patching for the
six CVEs disclosed 2026-09-15 (CVE-2026-46597, CVE-2026-39835, CVE-2026-39827,
CVE-2026-39828, CVE-2026-39829, CVE-2026-39832). This cycle surfaces an additional,
newly disclosed CVE in the same `x/crypto/ssh` package: CVE-2026-39830, where a
malicious SSH peer sends unsolicited global-request responses to fill an internal
buffer, blocking the connection's read loop — a per-connection resource-exhaustion
issue in the same family as the already-tracked CVE-2026-39827/39829.

`golang.org/x/crypto` is still not a direct dependency per `context/architecture.md`.
This proposal supersedes (extends the CVE list of) the original audit rather than
duplicating its mechanism: same audit steps, one more CVE added to the check list, so
the two proposals do not run redundant work.

## User stories
- AS the mctl-agent operator, I WANT to know whether `golang.org/x/crypto/ssh` is
  present and reachable in our dependency graph, checked against the full current CVE
  list including CVE-2026-39830, SO THAT I can decide whether a patch is needed with an
  up-to-date signal rather than last cycle's partial list.
- AS a security reviewer, I WANT the updated audit result documented in the same place
  as the original audit's findings SO THAT the CVE list this service has been checked
  against is traceable over time rather than scattered across separate, disconnected
  proposals.

## Acceptance criteria (EARS)
- WHEN this audit is run THE SYSTEM SHALL produce a complete list of all modules in
  mctl-agent's build graph that depend on `golang.org/x/crypto`, including the specific
  subpackage (e.g. `x/crypto/ssh`) and the resolved version, via `go list -m all`
  and/or `go mod graph` — reusing the original audit's output if it is still current
  (i.e., no `go.sum` changes since it ran), rather than re-deriving it from scratch.
- WHEN `govulncheck ./...` is run THE SYSTEM SHALL report reachability for
  CVE-2026-39830 in addition to the six CVEs already checked by the original audit
  (CVE-2026-46597, CVE-2026-39835, CVE-2026-39827, CVE-2026-39828, CVE-2026-39829,
  CVE-2026-39832).
- IF `golang.org/x/crypto/ssh` is present in the resolved build graph AND is reachable
  from code that mctl-agent actually calls THEN THE SYSTEM SHALL bump the affected
  module(s) to a resolved `x/crypto` version that fixes all seven tracked CVEs
  (the original six plus CVE-2026-39830), not just the newly added one.
- IF `golang.org/x/crypto/ssh` is absent from the build graph, or present only as an
  unreachable transitive dependency, THEN THE SYSTEM SHALL update the original audit's
  "not exposed" documentation to record that the finding still holds against the
  expanded seven-CVE list, with supporting evidence.
- WHEN this audit completes THE SYSTEM SHALL record the finding as an update to the
  original audit's tracking PR/issue (or a clearly cross-referenced follow-up) rather
  than as an unrelated, standalone record.

## Out of scope
- Re-running the full audit mechanism from zero if the original audit's `go mod graph`
  output is still valid (no dependency changes since) — reuse that evidence and only
  re-run `govulncheck` for the new CVE.
- Bumping `go-chi/chi`, `google/go-github`, or `anthropic-sdk-go` for reasons unrelated
  to this CVE cluster (see the separate `chi-v532-mount-route-fix` and
  `anthropic-sdk-v175-compaction-fix` proposals).
- CVE-2026-39831 (FIDO/U2F `Verify()` touch-bypass) — not applicable, mctl-agent does
  not handle hardware security-key attestation (already dropped by the analyst).
- General dependency-supply-chain tooling (e.g. automated `govulncheck` in CI) beyond
  what is needed to resolve this specific finding.
