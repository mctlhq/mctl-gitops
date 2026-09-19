# Audit dependency tree for transitive golang.org/x/crypto/ssh exposure

## Context
On 2026-09-15, six CVEs were disclosed against `golang.org/x/crypto`, several of them
high severity: CVE-2026-39829 (RSA/DSA parsers missing key-size limits, allowing
multi-minute CPU exhaustion from an unauthenticated client — now capped at 8192-bit RSA
moduli upstream) and CVE-2026-39827 (SSH server unbounded memory growth from repeated
rejected channel opens), plus four related SSH CertChecker, PartialSuccessError, and
agent key-constraint issues. mctl-agent does not list `golang.org/x/crypto` as a direct
dependency in `context/architecture.md`, but it could be pulled in transitively via
`go-chi/chi`, `google/go-github`, or `anthropic-sdk-go`.

This audit is cheap (a `go list -m all` / `go mod graph` pass) and either rules out
exposure entirely, or surfaces a real, high-severity issue worth patching immediately —
particularly relevant because mctl-agent exposes network-facing HTTP endpoints
(AlertManager webhook, Telegram webhook, MCP endpoint) that make CPU/memory-exhaustion
vectors directly actionable if any code path in our dependency graph actually
constructs or accepts SSH connections.

## User stories
- AS the mctl-agent operator, I WANT to know whether `golang.org/x/crypto/ssh` is
  present in our dependency graph and whether it is reachable from any code path we
  execute SO THAT I can decide whether the 2026-09-15 CVE cluster requires an
  immediate patch or is a non-issue.
- AS a security reviewer, I WANT the audit result and remediation (if any) documented
  SO THAT future dependency reviews don't have to re-derive this from scratch.

## Acceptance criteria (EARS)
- WHEN the audit is run THE SYSTEM SHALL produce a complete list of all modules in
  mctl-agent's build graph that depend on `golang.org/x/crypto`, including the
  specific subpackage (e.g., `x/crypto/ssh`) and the resolved version, via `go list -m
  all` and/or `go mod graph`.
- IF `golang.org/x/crypto/ssh` is present in the resolved build graph AND is reachable
  from code that mctl-agent actually calls (not just an unused transitive import)
  THEN THE SYSTEM SHALL bump the affected module(s) to a resolved `x/crypto` version
  that fixes CVE-2026-46597, CVE-2026-39835, CVE-2026-39827, CVE-2026-39828,
  CVE-2026-39829, and CVE-2026-39832.
- IF `golang.org/x/crypto/ssh` is absent from the build graph, or present only as an
  unreachable transitive dependency of an unused feature of an upstream module, THEN
  THE SYSTEM SHALL document this finding as "not exposed" with supporting evidence
  (module graph excerpt) and take no further code action.
- WHEN the audit completes THE SYSTEM SHALL record the finding (exposed / not exposed,
  with evidence) in the PR or proposal follow-up, independent of which branch above
  applies.
- WHILE no remediation is required THE SYSTEM SHALL still re-run this audit on any
  future bump of `go-chi/chi`, `google/go-github`, or `anthropic-sdk-go`, since any of
  them could newly introduce an `x/crypto/ssh` dependency.

## Out of scope
- Bumping `go-chi/chi`, `google/go-github`, or `anthropic-sdk-go` themselves for
  reasons unrelated to this CVE cluster (see sibling proposals
  `chi-redirect-cve-boundary-check` and `anthropic-sdk-compact-before-next-turn`).
- Adding new SSH functionality to mctl-agent.
- General dependency-supply-chain tooling (e.g., automated `govulncheck` in CI) beyond
  what is needed to resolve this specific finding — may be a follow-up proposal.
