# Spike: provider-neutral security finding lifecycle (verified fix and regression reopen)

## Context

Issue mctlhq/.github#209 asks whether MCTL should add a small, provider-neutral contract for
the lifecycle of a security finding. The contract would take findings from several sources
(Claude Security, GitHub code scanning/CodeQL, Dependabot/Trivy, MCTL Runtime Assurance), turn
each one into a single governed remediation, bind the exact vulnerable and fixed revisions,
mark the finding resolved only when verification evidence exists, and reopen it on regression.
The output is a spike report with one portfolio recommendation (`NO_NEW_CONTRACT`,
`EXTEND_ASSURANCE_FINDING`, `ADD_SECURITY_FINDING_CONTRACT` or `CREATE_SECURITY_EPIC`). It is
backed by a bounded, deterministic lifecycle experiment run on fixtures. Nothing is rolled out.

This matters because the current path has measurable gaps. In the
`mctl-gitops/platform-gitops/agents-state/` tree, 156 proposal `requirements.md` files cite a
CVE identifier. Six separate `mctl-api` proposals target CVE-2025-54236 (pgx). Only one of
them, `pgx-sqli-cve-2025-54236`, has a `.status.yaml`. That file records
`status: merged` and `merge_commit: 92f579a8...`, but no verification result. Its own
acceptance criterion ("a Dependabot or Trivy scan ... SHALL report zero open findings") is not
recorded anywhere as having been checked. CVE-2026-32283 appears in 13 proposals across
`mctl-agent` and `mctl-api`. So deduplication, verification and reopen semantics are missing
today. The spike tests whether a separate contract is the smallest fix, or whether the existing
Runtime Assurance model (mctlhq/.github#151) or plain documentation is enough.

## User stories

- AS the owner of mctlhq/.github#209 I WANT a current-state map, a provider matrix and one
  evidence-backed recommendation SO THAT I can decide on a contract without pre-selecting an
  epic.
- AS a platform operator I WANT one canonical finding per vulnerability across providers and
  delivery retries SO THAT one CVE does not spawn six proposals.
- AS a security reviewer I WANT "resolved" to mean "verified absent on the exact landed
  revision" SO THAT a merged PR is never mistaken for a fix.
- AS the owner of mctlhq/.github#151 I WANT Runtime Assurance to remain the only owner of probe
  generation, replay and assurance regression promotion SO THAT it does not grow into a
  general scanner.
- AS an auditor I WANT dismissals (false positive, accepted risk, duplicate, not applicable,
  provider withdrawn) to carry actor, authority and reason SO THAT they are never confused with
  technical remediation.

## Acceptance criteria (EARS)

Report (`docs/spikes/security-finding-lifecycle.md`):

- WHEN the report is merged THE SYSTEM SHALL contain sections D1 to D7 as named in #209, an
  evidence-pin table (repository, 40-hex commit, read date) for every repository cited, and
  exactly one recommendation token from the four allowed values.
- WHEN D1 lists a current source (GitHub code scanning/CodeQL, Dependabot/Trivy, Claude/agy PR
  review, Runtime Assurance `AssuranceFinding`, manual GitHub issues, agents-state service-agent
  CVE proposals) THE SYSTEM SHALL record, for each source, the ten Q1 attributes. Any attribute
  that was not observed is marked `unknown (not observed)` with a reason.
- WHEN D2 is written THE SYSTEM SHALL fill all 12 rows of the provider matrix for Claude
  Security, GitHub/CodeQL and Runtime Assurance. Each cell cites a public doc URL, a source path
  or `unknown`.
- IF Claude Security live access is unavailable THEN THE SYSTEM SHALL map it from the public
  article and docs plus a fixture payload, and SHALL state the live-access limitation explicitly.
- WHEN D3 is written THE SYSTEM SHALL choose exactly one of reuse, extend, reference or
  separate for the Runtime Assurance boundary, and SHALL list the #151 success criteria it
  preserves.
- IF a contract is recommended THEN D4 SHALL define the following. The fields are
  references-first; no field duplicates WorkItem, repository identity, approval or evidence.
  The states are open, triaged, fixing, awaiting_verification, resolved, reopened,
  unverifiable and dismissed(reason). D4 SHALL also give the owner of each transition and the
  required evidence for each one.
- WHILE any provider's severity, title, description or suggested fix is stored THE SYSTEM SHALL
  treat it as untrusted evidence. It does not become an MCTL policy input or an authorization
  input.

Experiment (`docs/spikes/security-finding-lifecycle/`):

- WHEN the experiment test suite runs THE SYSTEM SHALL drive one fixture finding through
  provider event, normalized candidate, one remediation WorkItem reference, recorded vulnerable
  revision, fix revision, verification on the fixed revision, resolved, regression fixture, and
  reopened, and SHALL assert the state after each step.
- WHEN the same provider event is delivered twice, or two providers report the same canonical
  vulnerability identity, THE SYSTEM SHALL keep exactly one canonical finding and exactly one
  remediation reference.
- WHEN a PR-merged event arrives with no verification result THE SYSTEM SHALL leave the
  finding in `awaiting_verification`, not `resolved`.
- IF verification fails, times out, or reports the scanner unavailable THEN THE SYSTEM SHALL
  move the finding to `unverifiable` (or keep it in `awaiting_verification`) and SHALL NOT
  move it to `resolved`.
- WHEN a provider reports "fixed" with no MCTL verification on the exact landed revision THE
  SYSTEM SHALL record that as provider evidence with strength `provider_claim`. It SHALL NOT
  set `resolved` unless the contract's declared policy accepts that strength. The default
  does not.
- WHEN a finding is dismissed THE SYSTEM SHALL require actor, authority reference and reason.
  A later regression observation SHALL NOT silently reopen a dismissed finding. It SHALL be
  recorded as linked evidence.
- WHILE a resolved finding receives regression evidence THE SYSTEM SHALL require the
  configured confirmation (default: two consecutive observations, or one deterministic
  regression test) before it moves to `reopened`. This prevents flapping.
- WHEN at least one real provider payload schema (GitHub `code_scanning_alert` webhook / REST
  alert) is mapped THE SYSTEM SHALL keep it as a read-only fixture with no secrets and no
  vulnerable code bodies.

## Out of scope

- Building or running a source-code vulnerability scanner, or any scan of a public or
  production target.
- Changing the Runtime Assurance harness, its replay engine or the `agent-runtime-assurance`
  manifest.
- Any production rollout, mctl-api schema migration, MCP tool, webhook receiver or gitops
  credential.
- Adding, editing or binding any `roadmap/epics/*.yaml` manifest. Follow-up issues in D6 are
  text only.
- Auto-merge of security fixes, or any change to approval policy.
- A second WorkItem, identity, approval, policy or evidence model.

## Open questions

- The `AssuranceFinding` field shape (mctl-agents#694) is not visible from this repository.
  Every work item in `roadmap/epics/agent-runtime-assurance.yaml` reports `unbound` /
  `unknown` in the live roadmap publication. The spike must read mctl-agents at a pinned SHA.
  If the contract is not merged there, D3 records the boundary against the #151 manifest text
  only.
- Claude Security is public beta, Claude Enterprise only. The public article names no API
  fields or webhook event names. Live access is assumed unavailable, and the mapping is
  fixture-based.
- Whether `unverifiable` is a distinct state or a flag on `awaiting_verification` is chosen
  in D4. The experiment models it as a distinct state.
- Whether the default resolve policy should ever accept a provider's own "fixed" claim
  (for example GitHub `fixed` on the default branch at a known commit) as sufficient. Default
  in this proposal: no. It is recorded as weaker evidence.
- How the five orphaned duplicate pgx proposals should be closed is an operator decision.
  The spike only reports them.
