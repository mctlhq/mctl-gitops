# Spike: sandbox isolation gaps beyond the Kubernetes primitives spike (#852)

## Context

Issue #852 asks whether the sandbox isolation gaps described in The New Stack article "When 'isolated'
doesn't mean isolated: How to sandbox AI agents" (https://thenewstack.io/how-to-sandbox-agents/) reveal
weaknesses in mctl's agent isolation that the existing spikes do not cover. Two spikes already cover the
topic. #807 audits the Kubernetes layer: RBAC, egress NetworkPolicy, PSA, RuntimeClass and quota. Its
report, auditor and tests are in PR #810, which is open and not merged. #830 covers runtime observability
and egress detection of an agent that escapes its sandbox through package installation. The issue asks
for one outcome: an isolation gap list.

This proposal keeps the spike narrow on purpose. It produces a delta report. The report lists only the
isolation gaps that #807 and #830 do not already own, and every listed gap is grounded in
mctl-agents code or mctl-gitops configuration. Gaps that #807 or #830 already own are mapped to them, not
restated. Code reading for this proposal already shows several candidate gaps that sit above the pod
boundary, where no Kubernetes primitive applies:

- provider-side tools such as `WebSearch` run outside the pod's network path;
- the model-driven `Bash` tool is audit-logged but not policy-mediated;
- agent configuration can be loaded from untrusted target repositories through `setting_sources=["project"]`;
- untrusted repository code runs in the same pod as long-lived credentials.

## User stories

- AS the mctl platform owner I WANT a gap list that names only isolation weaknesses not already tracked
  by #807 or #830 SO THAT I can decide whether new hardening work is needed without duplicate spikes.
- AS a reviewer of agent security I WANT every gap tied to a concrete file, symbol or gitops path SO THAT
  I can verify it and it does not rest on the article's general claims.
- AS the scout pipeline maintainer I WANT the spike to record when an article adds nothing new SO THAT
  overlapping scout issues can be closed with evidence.

## Acceptance criteria (EARS)

- WHEN the spike is delivered THE SYSTEM SHALL contain a report at
  `docs/spikes/852-sandbox-isolation-delta.md` with a gap table. Each row has the columns `id`, `layer`,
  `gap`, `evidence` (repo path:symbol or gitops path), `status`, `owner_spike` and `follow_up`.
- WHEN a gap is already covered by #807 (G1-G6) or #830 THE SYSTEM SHALL mark the row `covered-by-807` or
  `covered-by-830` and SHALL NOT propose separate work for it.
- WHEN a gap is not covered by either spike THE SYSTEM SHALL mark it `new`, give it a severity
  (high/medium/low), and name one recommended control and the repo that owns it (mctl-agents or
  mctl-gitops).
- IF a claimed gap cannot be confirmed from code or gitops THEN THE SYSTEM SHALL mark it `not-observed`
  and SHALL NOT mark it `absent` or `new`.
- WHEN the report is merged THE SYSTEM SHALL carry exactly one decision token on its `STATUS:` line, from
  `NO_NEW_GAPS`, `NEW_GAPS_FOLLOW_UP`, `FOLD_INTO_807`, or SHALL carry `STATUS: DRAFT`.
- WHILE the spike PR is open THE SYSTEM SHALL NOT change any file under `orchestrator/`, `config/` or
  `agents/_manifests/`, nor `Dockerfile` or `entrypoint.sh`. A guard test enforces this.
- IF the source article body cannot be retrieved THEN THE SYSTEM SHALL say so in the report and derive
  the article taxonomy only from its title and publicly known sandboxing categories. Those categories are
  kernel sharing, network egress, credentials, filesystem persistence, tool mediation, untrusted code
  execution and resource exhaustion.
- THE SYSTEM SHALL NOT include secret values, exploit payloads or step-by-step escape procedures in the
  report.

## Out of scope

- Any change to the runtime, CWFTs, NetworkPolicies, RBAC or ExecutionProfiles. Hardening goes to
  follow-up issues.
- Restating #807's Kubernetes matrix or #830's egress observability plan.
- Live probing of the production cluster.
- Choosing a sandbox runtime such as gVisor, Kata or Firecracker. This stays #807 G5's decision.

## Open questions

- The article body could not be fetched in this run: the page returned only navigation and the title.
  The implementer should retry the fetch. If the fetch still fails, the report proceeds on the
  title-derived taxonomy and records the limitation.
- #807's PR #810 is still open. If it changes the G1-G6 numbering before merge, the delta report must map
  to the merged numbering.
- Whether `setting_sources=["project"]` in target-repo clones loads `.claude/settings.json` hooks and
  permissions, or only agents and skills, depends on the Claude Agent SDK version that is pinned. The spike
  verifies this against the pinned SDK and does not assume it.
- Whether #852 should be closed as a duplicate of #807 or #830 once the report says `NO_NEW_GAPS` or
  `FOLD_INTO_807` is the owner's call.
