# Execute the #182 governance audit: Agent Governance & Decision Assurance report (D1-D5)

## Context

Issue mctlhq/.github#199 carries the execution of the #182 spike and nothing else. The original Temporal DevLoop `dev-loop-mctlhq-.github-182` is now `Completed` and cannot be restarted. Here is how it closed:
- the human approval grant `aar_d3572c56815543f59289fa3bf0a30f6d` was bound to proposal v1 (mctl-gitops `fb63a4b03`, `sha256:09718ba2...`);
- `@MCTL reinvestigate` then rewrote the proposal to v2 (mctl-gitops `178f7bf9a`, `sha256:2ca80ff5...`);
- the approve CWFT `mctl-agents-approve-6f23268b` correctly refused the v1-bound decision for the v2 bytes before it edited anything.

The scope is identical to the owner-reviewed v2 proposal, which follows the current body of mctlhq/.github#182: "Current baseline - 2026-10-18", "Execution status and production incident - 2026-10-18", "Owner corrections", Scope 1-8, F1-F10, D1-D5 and the acceptance criteria.

The deliverable is one report, `docs/spikes/agent-governance-decision-assurance.md`, in `mctlhq/.github`. The report must establish whether governance holds end to end on each governed path. Human approval alone is not evidence of that. The report also gives the 2026-10-18 stale-grant refusal its own D3 analysis on P1, because it is a real production case for F1/F5. It shows that decision-time binding held while the proposal lifecycle and the approval lifecycle were not atomic (mctlhq/mctl-agents#701). It also shows that a refused approval was projected as success (mctlhq/mctl-agents#702).

This carrier changes nothing in the v2 scope or design. The only additions are the ones the #199 issue body requires:
- the production D3 evidence;
- the free-text-reason invariant;
- a refresh of the evidence pins, because mctl-api `main` has moved since v2 was written.

## User stories

- AS the mctl-api owner I WANT one evidence-backed report showing how each governed path P1-P5 really behaves SO THAT I can decide where governance gaps belong without starting a parallel framework.
- AS the #182 owner reviewing D5 I WANT the disposition derived only from D1-D4 evidence pinned at named SHAs SO THAT it is not a restatement of issue text or of an earlier hypothesis.
- AS an auditor I WANT every claim to cite a file, test, contract or read-only live observation SO THAT I can reproduce it.
- AS a DevLoop maintainer I WANT the 2026-10-18 stale-grant refusal analysed precisely, covering what held, what was not atomic and what was misprojected, SO THAT mctl-agents#701 and #702 are grounded in the governance model.
- AS a roadmap owner I WANT the recommended manifest delta stated as text and not applied SO THAT the #181 lifecycle change stays a separate owner-reviewed PR.
- AS the Runtime Assurance owner (#151) I WANT candidate AssuranceScenarios named but not implemented SO THAT the harness stays in one place.

## Acceptance criteria (EARS)

Evidence and pinning
- WHEN the report is written THE SYSTEM SHALL include an "Evidence pins" table with the 40-hex commit SHA and read date for `mctlhq/.github`, `mctlhq/mctl-api`, `mctlhq/mctl-agents`, `mctlhq/mctl-gitops`, and any other repository used for a substantive claim.
- IF a mandatory repository cannot be read THEN THE SYSTEM SHALL stop, record the blocker in the report, and not complete D1-D4 from issue text or gitops comments alone.
- WHEN a fact is genuinely unobservable although the mandatory sources were read THE SYSTEM SHALL mark it `unknown (not observed)` with a reason, and SHALL NOT mark it implemented or missing.
- WHEN a deployed version, live status or audit record is claimed THE SYSTEM SHALL cite a read-only MCTL observation or a gitops path, together with its date.

Path separation
- THE SYSTEM SHALL analyse these paths separately:
  - P1: canonical Temporal DevLoop grant approval, the #681 path: the `aar_` grant with `artifact_hash`, then the human decision, then grant-authorized `/operations/mctl-agents-approve/execute`, then the CWFT `expected_content_digest` check, then the implementer gate.
  - P2: standalone/direct `mctl_trigger_approve` or `mctl-agents-approve` without a DevLoop grant.
  - P3: the incident-responder autonomous/no-human-gate path.
  - P4: policy-checkpoint actions.
  - P5: Agent Commerce.
- WHILE analysing P1 THE SYSTEM SHALL treat mctl-agents#681 as proof of exact-content binding for P1 only.
- WHILE analysing P3 THE SYSTEM SHALL describe it neutrally, and SHALL classify it for F10 only from the policy and authority contract that was read.

Deliverables
- WHEN D1 is complete THE SYSTEM SHALL provide one sequence diagram per path. Each diagram SHALL show the services, the trust boundaries and the actual evaluation order, and SHALL tag every step as implemented or planned.
- WHEN D2 is complete THE SYSTEM SHALL provide a matrix for each path.
  - Its columns SHALL be Capability | Status | Owner/component | Gap | Evidence.
  - It SHALL have at least these 13 rows: intent provenance, unified identity, approval authority, policy evidence, decision context, immutable proposal, execution binding, approval expiry, replay protection, end-to-end trace, escalation, break-glass, governance metrics.
  - Every Status SHALL be one of: implemented, partial, missing, owned by another epic, unknown (not observed).
- WHEN D3 is complete THE SYSTEM SHALL record, for each of F1-F10 and per applicable path:
  - current behavior;
  - the desired invariant;
  - evidence, being an existing test or a safe bounded reproduction;
  - the gap;
  - the owner.
- WHEN F1/F5 are analysed for P1 THE SYSTEM SHALL include the 2026-10-18 production stale-grant case as evidence, and SHALL cover all of the following:
  - The audit records: `action_approval.create` 13:44:01Z, `action_approval.decision` 14:17:38Z and `action_approval.consume` 14:17:40Z for `aar_d3572c56815543f59289fa3bf0a30f6d`.
  - The Argo workflow `mctl-agents-approve-6f23268b`, whose `flip-status` refusal reads "changed after it was approved: the files hash to sha256:2ca80ff5..., the approval was for sha256:09718ba2...".
  - The record `work_item.execution` 14:18:26Z for `we_dadf9c08-0156-4ffa-a306-a11e188ae921`.
  - What held: decision-time binding protected execution. The v2 bytes were refused under the v1 grant, and nothing was recorded as approved for v2.
  - What was not atomic: reinvestigate left a pending grant bound to content that no longer existed, and a human decided it (mctl-agents#701).
  - What was misprojected: the refused approval was projected as execution `Succeeded` and loop `Completed`, which cannot be restarted (mctl-agents#702).
- WHEN the stale-grant case is analysed THE SYSTEM SHALL state the invariant "a free-text approval reason is descriptive metadata only; it confers no binding or authority".
- WHEN F1/F2/F5 are analysed THE SYSTEM SHALL state, per path, whether `approved(action A) + attempt(action B) -> hard fail` holds, and name the enforcing code.
- WHEN D4 is complete THE SYSTEM SHALL map every candidate `GovernedDecision` field to an existing contract field or mark it as a gap.
- WHEN D4 is complete THE SYSTEM SHALL state where append-only references are required for approvals, attempts, policy evaluations and steps.
- WHEN D5 is written THE SYSTEM SHALL derive exactly one of NO NEW EPIC / EXTEND EXISTING / CREATE NEW EPIC from D1-D4, starting from no prior disposition.
- WHEN D5 is written THE SYSTEM SHALL give every gap an existing owner/epic or a justified proposed owner.
- WHEN D5 is written THE SYSTEM SHALL state the recommended roadmap manifest delta as text only.
- IF D5 is CREATE NEW EPIC THEN THE SYSTEM SHALL include a refined EpicDefinition draft and its dependency DAG in the report body, and not under `roadmap/epics/`.
- THE SYSTEM SHALL state in the report that completing the spike does not deliver runtime assurance.

Scope fences
- WHILE the PR is open THE SYSTEM SHALL change no files other than `docs/spikes/agent-governance-decision-assurance.md` and, optionally, one non-semantic link line in `AGENTS.md`.
- THE SYSTEM SHALL NOT change `roadmap/epics/agent-governance-decision-assurance.yaml` or the lifecycle of #181.
- THE SYSTEM SHALL NOT create follow-up issues, ship runtime fixes, enable bypasses, or call any mutating MCTL operation.
- THE SYSTEM SHALL NOT state or prefer a D5 disposition before D1-D4 are written.

## Out of scope

- Fixing mctl-agents#701 (reinvestigate must supersede the pending grant) or #702 (a failed approval projected as success). These are analysed as evidence only.
- Runtime fixes in mctl-api, mctl-agents or mctl-gitops, and filing follow-up issues.
- Archiving, activating or refining the epic manifest or the #181 lifecycle.
- Closing #182. Its owner reviews D5 and closes it; merging this carrier's PR does not close #182.
- A second authorization framework or telemetry system, and an approval UI.
- AssuranceScenario, replay or regression implementation, which #151 / mctl-agents#694-#700 own.
- Storing private model reasoning.

## Open questions

- P4 and F1: the issue's F1 is phrased as `send_message`. The v2 proposal could not confirm a `send_message` action kind in `orchestrator/policy_checkpoint.py`. The report analyses F1 on the closest real action kinds. It marks a Telegram send as `unknown (not observed)` unless the mctl-telegram source is read and pinned.
- P2 support status: the CWFT accepts an empty `expected_content_digest`. P2 is treated as in scope and is not assumed to be deprecated.
- Pin drift: mctl-api `main` moved from `5dd4e73` (the v2 pre-check) to `57864b5` (2026-10-18). The report must re-pin and state whether the P1 controls changed between the two. Deployed mctl-api is `4.102.0` against `4.97.0` in the #681 E2E.
- Audit-record access: the `action_approval.*` and `work_item.execution` records come from the issue body. In this run only the `mctl-agents-approve` audit row and the Argo logs were confirmed through read-only tools. If the implementer cannot read the other records, it marks them "cited from #199/#182, not independently observed".
- The approve audit row records `actor_kind: agent` (`issue-investigator`) with `approver: mashkovd` and `subject_principal_id`. D2's identity row should state whether this actor/subject/approver split matches the #572 model.
