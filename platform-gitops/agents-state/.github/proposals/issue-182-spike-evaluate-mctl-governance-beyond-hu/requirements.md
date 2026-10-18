# Spike: Agent Governance & Decision Assurance report (D1-D5) for mctlhq/.github#182

## Context

Issue mctlhq/.github#182 asks for an architecture and gap-analysis spike on
whether MCTL governance holds end to end, beyond simply putting a human in
front of execution. Human approval is not enough evidence of governance on its
own. The spike must work out, for each governed action: where the intent came
from, who initiated it, which policy was evaluated and why, what context the
reviewer saw, whether the approver had authority, whether the operation that
ran was exactly the one approved, what the outcome was, and whether the whole
chain can be rebuilt afterwards. The deliverable is one durable report,
`docs/spikes/agent-governance-decision-assurance.md`, in `mctlhq/.github`. It
contains D1 (current-state sequence diagram), D2 (capability matrix, per
path), D3 (F1-F10 failure analysis), D4 (minimal candidate Decision Envelope
built from existing contracts) and D5 (exactly one disposition: NO NEW EPIC /
EXTEND EXISTING / CREATE NEW EPIC).

This proposal replaces the first proposal, which was not approved. It applies
the owner corrections of 2026-10-18:
- D5 starts with no prior disposition.
- The roadmap lifecycle decision goes in a separate PR.
- Cross-repository source evidence pinned at SHAs is a hard prerequisite.
- P1 (Temporal DevLoop grant approval) and P2 (standalone/direct GitOps
  approval) are kept apart.
- The incident-responder auto-accept is treated neutrally as an
  autonomous/no-human-gate path until its evidence is read.
- mctl-agents#681 proves exact-content binding only for P1.

## User stories

- AS the mctl-api owner I WANT one evidence-backed report that shows how each governed path really behaves SO THAT I can decide where governance gaps belong without starting a parallel framework.
- AS a reviewer of D5 I WANT the disposition to follow from D1-D4 evidence pinned at named SHAs SO THAT the recommendation is not a restatement of the issue text or of an earlier hypothesis.
- AS an auditor I WANT every claim in the report to cite a file, test, contract or read-only live observation SO THAT I can reproduce it.
- AS a roadmap owner I WANT the report to state the exact manifest delta it recommends, without applying it SO THAT the lifecycle change of #181 stays a separate owner-reviewed PR.
- AS the Runtime Assurance owner (#151) I WANT the report to name candidate AssuranceScenarios without implementing them SO THAT the harness stays in one place.

## Acceptance criteria (EARS)

Evidence and pinning
- WHEN the report is written THE SYSTEM SHALL include an "Evidence pins" table with the commit SHA read for each of `mctlhq/.github`, `mctlhq/mctl-api`, `mctlhq/mctl-agents`, `mctlhq/mctl-gitops`, and any other repository used for a substantive claim.
- IF a mandatory source repository cannot be read THEN THE SYSTEM SHALL stop, record the blocker in the report, and not complete D1-D4 from issue text or gitops comments alone.
- WHEN a fact cannot be observed even though the mandatory sources were read THE SYSTEM SHALL mark it `unknown (not observed)` and say why. It SHALL NOT mark that fact implemented or missing.
- WHEN a deployed version or live status is claimed THE SYSTEM SHALL cite a read-only MCTL observation or a gitops path (for example `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` image tag) and its date.

Path separation
- THE SYSTEM SHALL analyse at least these paths separately:
  - P1: canonical Temporal DevLoop approval (`aar_` grant with `artifact_hash`, then human decision, then grant-authorized `/operations/mctl-agents-approve/execute`, then CWFT `expected_content_digest`, then the implementer gate).
  - P2: standalone/direct GitOps approval (`mctl_trigger_approve` or direct `mctl-agents-approve` with no DevLoop grant).
  - P3: the incident-responder autonomous/no-human-gate path.
  - P4: orchestrator policy-checkpoint governed actions (tool calls and GitHub mutations).
  - P5: Agent Commerce invocations.
- WHILE analysing P1 THE SYSTEM SHALL treat mctl-agents#681 as proof of exact-content binding for P1 only. It SHALL NOT extend that proof to P2-P5 without each path's own evidence.
- WHILE analysing P3 THE SYSTEM SHALL describe it neutrally and SHALL classify it (for F10) only from the policy and authority contract that was read.

Deliverables
- WHEN D1 is complete THE SYSTEM SHALL provide a sequence diagram per path. Each diagram SHALL show services, trust boundaries and the real evaluation order, and SHALL separate implemented behavior from planned work.
- WHEN D2 is complete THE SYSTEM SHALL provide, for each path, a matrix with columns Capability | Status | Owner/component | Gap | Evidence.
  - It SHALL have at least these rows: intent provenance, unified identity, approval authority, policy evidence, decision context, immutable proposal, execution binding, approval expiry, replay protection, end-to-end trace, escalation, break-glass, governance metrics.
  - Status SHALL be one of implemented / partial / missing / owned by another epic / unknown (not observed).
- WHEN D3 is complete THE SYSTEM SHALL record, for each of F1-F10:
  - current behavior per applicable path;
  - the desired invariant;
  - evidence, being an existing test or a safe bounded reproduction with no production side effects;
  - the gap;
  - the owner.
- WHEN F1/F2/F5 are analysed THE SYSTEM SHALL state whether `approved(action A) + attempt(action B) -> hard fail` holds, and name the enforcing code.
- WHEN D4 is complete THE SYSTEM SHALL map every candidate envelope field to an existing MCTL contract field or mark it as a gap. It SHALL also state where append-only references are needed instead of singleton fields: multiple approvals, attempts, policy evaluations and steps.
- WHEN D5 is written THE SYSTEM SHALL derive exactly one disposition from D1-D4.
  - It SHALL give every gap an existing owner/epic or a justified proposed owner.
  - It SHALL state the exact recommended roadmap manifest delta or follow-up action as text only.
- IF D5 is CREATE NEW EPIC THEN THE SYSTEM SHALL include a refined EpicDefinition draft (required/optional work and dependency DAG) in the report body, not in `roadmap/epics/`.
- THE SYSTEM SHALL state in the report that completing the spike does not deliver runtime assurance.

Scope fences
- WHILE the spike PR is open THE SYSTEM SHALL NOT change `roadmap/epics/agent-governance-decision-assurance.yaml` or the lifecycle of #181, beyond non-semantic documentation links.
- THE SYSTEM SHALL NOT create follow-up issues, ship runtime fixes, enable bypasses, or call any mutating MCTL operation as part of the spike.
- THE SYSTEM SHALL NOT state or prefer any D5 disposition before D1-D4 are written.

## Out of scope

- Runtime fixes in mctl-api, mctl-agents or mctl-gitops; creating follow-up issues.
- Archiving, activating or refining the roadmap manifest or #181 lifecycle (a separate PR after D5 review).
- A second authorization framework, a second telemetry system, or an approval UI.
- Implementing AssuranceScenarios or replay/regression harness work (owned by #151 / mctl-agents#694-#700).
- Storing or evaluating private model reasoning.

## Open questions

- Is P4 (policy-checkpoint actions) a "send_message-type" path in the F1 sense? A `send_message` action kind was not confirmed in `orchestrator/policy_checkpoint.py` at the pinned SHA. The report should analyse F1 on the closest real action kinds (GitHub issue comment, work-item write, commerce invoke) and mark Telegram send as `unknown (not observed)` unless its source is read.
- Is the P2 standalone approve a supported production path or legacy only? The CWFT accepts an empty `expected_content_digest`. The report should treat P2 as in scope and state its binding gap, without assuming it is deprecated.
- Mandatory repo list: are `mctl-telegram`, `mctl-portal` and `mctl-agent` needed? The report adds them only if a substantive claim depends on them, and pins their SHAs if so.
- Deployed versions differ from the #681 E2E: api 4.97.0 then, `4.102.0` now in gitops bootstrap. The report should state whether the P1 controls are unchanged between the two, or mark it unverified.
