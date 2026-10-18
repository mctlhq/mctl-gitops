# Spike report: MCTL governance and decision assurance beyond human-in-the-loop approval

## Context

Issue mctlhq/.github#182 is the only required work item of the provisional epic
`roadmap/epics/agent-governance-decision-assurance.yaml` (parent
mctlhq/.github#181, `lifecycle: proposed`). It asks for an architecture and
gap-analysis spike, not a new governance framework. The spike must show, for
each governed execution path in MCTL, whether the platform can prove the whole
decision chain: where intent came from, who initiated it, which policy was
evaluated and why, what the reviewer saw, whether the approver had authority,
whether the executed operation is exactly the approved one, what happened, and
whether the chain can be rebuilt later. The output is a durable report in this
repository (D1 sequence diagram, D2 capability matrix, D3 F1-F10 failure
analysis, D4 candidate Decision Envelope, D5 one architecture disposition), plus
a roadmap manifest change that matches the disposition.

This matters because human approval alone is not evidence of governance. A
reviewer can approve with too little context or authority, an approved proposal
can change, and execution can lose its binding to the decision.
mctlhq/mctl-agents#681 proves exact content binding for one path, DevLoop
proposal-content approval. Other paths are known to differ. In the deployed
`agent-platform/policy.yaml`, the scopes `incident-resolve`, `proposal-status`,
`agents-state-inbox-write` and `mentor-digest-write` are mutating scopes with
`requiresApproval: null`. The deployed approve CWFT treats
`expected_content_digest` as optional and takes `approver` as a caller-supplied
string. The spike has to state these differences per path, on evidence, and must
not generalize from #681.

## User stories

- AS a platform owner I WANT a per-path map of which governance guarantees MCTL enforces today SO THAT I can tell enforced invariants apart from approval UX and planned work.
- AS an auditor I WANT to know whether one governed action can be rebuilt end to end from durable records SO THAT the question "who decided what, under which policy and authority, and what exactly ran" has an answer that does not depend on sampled traces.
- AS a roadmap owner I WANT exactly one disposition (NO NEW EPIC / EXTEND EXISTING / CREATE NEW EPIC), with every gap routed to an owner SO THAT the provisional parent #181 is archived, repurposed or refined on purpose.
- AS an implementer of later follow-ups I WANT each gap to carry evidence, scope, acceptance criteria and an owner SO THAT remediation can be planned without repeating the audit.
- AS a reader of roadmap status I WANT the report and the manifest to say plainly that the spike delivers no runtime assurance SO THAT closing #182 is never reported as delivered governance.

## Acceptance criteria (EARS)

- WHEN the spike is delivered THE SYSTEM SHALL contain one report at `docs/spikes/agent-governance-decision-assurance.md` with sections D1, D2, D3, D4 and D5, and a list of pinned source revisions for each audited repository (mctlhq/.github, mctl-api, mctl-agents, mctl-gitops, plus any other repository the report cites), following the "Live audit and evidence" convention of `docs/plans/agent-commerce.md`.
- WHEN D1 describes a governed flow THE SYSTEM SHALL show the actual services, trust boundaries and evaluation order as a sequence diagram (Mermaid or ASCII) for at least these paths: (a) DevLoop proposal-content approval, (b) the direct `mctl-agents-approve` operation (`mctl_trigger_approve`), which bypasses the DevLoop, (c) capability gateway invoke through PolicyCheckpoint, (d) the incident-responder auto-accept path, (e) a commerce invocation (mctlhq/.github#173), and (f) an MCP platform operation that goes through mctl-api. Each step cites a code, contract or test path at a pinned revision, plus the deployed version where one is known.
- WHEN a D2 row is written THE SYSTEM SHALL fill the columns Capability, Status, Owner/component, Gap and Evidence. Status is one of implemented, partial, missing or owned-by-another-epic, and covers at least: intent provenance, unified identity, approval authority, policy evidence, decision context, immutable proposal, execution binding, approval expiry, replay protection, end-to-end trace, escalation, break-glass and governance metrics.
- IF the evidence for a capability could not be observed THEN THE SYSTEM SHALL mark the status as "unknown (not observed)" with the reason, and SHALL NOT record it as implemented or missing.
- WHILE a capability is implemented for one path only THE SYSTEM SHALL record it as partial and name the paths that are covered and the paths that are not. In particular, #681 content binding SHALL NOT be extended to tool calls, commerce actions or send_message-type actions without evidence for each of those paths.
- WHEN D3 analyses scenarios F1-F10 THE SYSTEM SHALL record, for each one, the current behaviour per affected path, the desired invariant, the evidence (an existing test or a safe, bounded, non-production reproduction), the gap and the owner. The analysis SHALL cover replay, payload mutation, target mutation, authority loss, expiry, delegation, partial failure, policy drift and break-glass.
- IF a scenario cannot be verified without a production side effect THEN THE SYSTEM SHALL record it as unverified, describe the reproduction it would take, and SHALL NOT perform it.
- WHEN the report evaluates approval integrity THE SYSTEM SHALL state, for each trust boundary, whether the hash binding and the existing audit are enough or whether stronger authenticated or tamper-evident evidence is needed, and SHALL note that a content hash does not establish approver identity.
- WHEN the report evaluates identity and authority THE SYSTEM SHALL name the requester or subject, the executing agent, the service or tool identity, the approving human, the tenant and any delegated authority. It SHALL state whether authority is re-evaluated at execution time, and SHALL flag every place where authority or approver identity comes from a caller-supplied string (for example the approve CWFT `approver` parameter).
- WHEN the report evaluates policy evidence THE SYSTEM SHALL state whether the policy identity and version, the allow/deny/require_approval result and structured reasons are persisted, and how they correlate with the execution. It SHALL NOT propose storing private model reasoning.
- WHEN D4 is written THE SYSTEM SHALL map every envelope field to an existing MCTL contract, or mark it as new with a reason. It SHALL state whether approvals, attempts, policy evaluations and workflow steps need append-only referenced records rather than singleton fields, and that stored authority claims are evidence, not an authorization substitute. It SHALL also define retention, access and redaction rules so that reconstruction does not depend on logging full private payloads.
- WHEN the report evaluates observability THE SYSTEM SHALL propose governance metrics (approval and rejection rates and latency, approvals without observable context inspection, mutation and reapproval counts, expired approvals, authority failures, overrides, break-glass events, mismatched execution attempts, escalation rates), together with their instrumentation limits. It SHALL reuse the OTLP primitives from mctlhq/.github#55 and SHALL NOT introduce a second telemetry system or treat sampled traces as a durable audit record.
- WHEN the report assesses reject, modify-and-resubmit, request-more-context, escalation, override, break-glass, expiry and no-authorized-approver THE SYSTEM SHALL define the allowed bypasses, the authority they require, attribution and audit requirements. It SHALL NOT enable any bypass.
- WHEN D5 is written THE SYSTEM SHALL state exactly one disposition, and every gap from D2 and D3 SHALL map to an existing owner or epic or to a justified proposed owner.
- IF D5 is EXTEND EXISTING or NO NEW EPIC THEN THE SYSTEM SHALL set `spec.lifecycle` in `roadmap/epics/agent-governance-decision-assurance.yaml` to `archived` (or record an explicit repurposing), with a header comment pointing at the report and the routed follow-ups.
- IF D5 is CREATE NEW EPIC THEN THE SYSTEM SHALL refine `roadmap/epics/agent-governance-decision-assurance.yaml` with the required and optional remediation and proof work items and a `dependsOn` DAG. Work items whose issues do not exist yet SHALL be listed in the report as proposed follow-ups, not invented as issue numbers.
- WHILE the roadmap manifest is changed THE SYSTEM SHALL keep `python3 roadmap/scripts/validate.py roadmap/epics` and the existing `roadmap/tests` passing.
- WHEN the report is merged THE SYSTEM SHALL state in the report and in the manifest successCriteria that completing the spike does not deliver runtime decision assurance.
- WHEN the report is added THE SYSTEM SHALL list it in `AGENTS.md` next to the existing Agent Commerce entry.

## Out of scope

- Implementing any runtime control, API, schema, CWFT or policy change in mctl-api, mctl-agents or mctl-gitops. The spike only names the follow-ups.
- A second authorization framework, a second telemetry system, or a replacement for Unified Identity or policy enforcement.
- Enabling any override, break-glass or bypass.
- Requiring human approval for every operation.
- Storing private model reasoning or chain of thought.
- A full approval UI.
- Implementing AssuranceScenario coverage. That belongs to mctlhq/.github#151 (mctl-agents#694-#700). The report may only name candidate scenarios.
- Creating GitHub issues for follow-ups as part of this change. The report drafts them; filing is a separate governed step.
- Production side effects of any kind during verification.

## Open questions

- The report's location: the issue allows either `docs/spikes/` or `docs/plans/`. This proposal picks a new `docs/spikes/` directory, because the report is an audit outcome and not a plan that is being carried out. A reviewer may prefer `docs/plans/`.
- The disposition is open by design. This proposal records EXTEND EXISTING as a working hypothesis (the gaps observed so far all fall to existing owners: mctl-api approvals and identity, mctl-agents policy and execution, mctl-gitops policy catalog, #55 observability, #151 assurance). The report must confirm or overturn it on evidence, and the tasks support either outcome.
- Which commerce and send_message-type paths are deployed today, and in which tenants. The investigator could only read mctl-gitops `platform-gitops/` and could not read the mctl-api or mctl-agents source trees. The implementer must pin and read those revisions.
- Whether the `incident-resolve` and `proposal-status` scopes without approval (`requiresApproval: null`, which `policy.yaml` itself calls "undecided") count as governed actions that need a gate, or as accepted autonomous scopes that only need attributable evidence. The report should make a recommendation and leave the decision to the owners.
- The deployed versions differ from the #681 baseline: mctl-api is `4.102.0` in gitops against `4.97.0` in the issue, and the mctl-agents workers are `1.84.0`. The report must pin the revisions it actually audits.
