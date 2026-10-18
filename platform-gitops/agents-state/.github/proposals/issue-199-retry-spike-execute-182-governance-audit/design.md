# Design: issue-199-retry-spike-execute-182-governance-audit

## Current state

### This repository (`mctlhq/.github` at `6f35424f140a15557c3405ebed6d08851eb496b2`)
- `docs/` contains only `docs/plans/` (`agent-commerce.md`, `mcp-gateway.md`). `docs/spikes/` does not exist yet.
- `AGENTS.md` has one "Active plans" heading, which links `docs/plans/agent-commerce.md`.
- `roadmap/epics/agent-governance-decision-assurance.yaml` is an `EpicDefinition`:
  - `lifecycle: proposed`, issue #181, owner `mctl-api`;
  - one phase, `discovery`;
  - one required item, `decision-assurance-spike` -> #182;
  - `completion.mode: allRequired`.
  - Its successCriteria already say that "spike closure alone is not evidence of delivered runtime guarantees". This carrier does not touch the file.

### Source specification
- The v2 proposal for #182 is at mctl-gitops `178f7bf9aea0ca2a6e6780662e5a355618935f5e`, in `platform-gitops/agents-state/.github/proposals/issue-182-spike-evaluate-mctl-governance-beyond-hu/`. All three of its files were read: `requirements.md`, `design.md` and `tasks.md`. Its `.status.yaml` is still `status: proposed` and has no `approval:` block. That is consistent with the CWFT refusing before it edited anything.
- The current body of mctlhq/.github#182 was read with `gh issue view 182`, including its new "Execution status and production incident - 2026-10-18" section. The v1 proposal commit `fb63a4b03ba9889e566c4c3bbfe73f21b3b63944` exists.
- The v2 design's cross-repo anchors are still the anchors the implementer must read in full:
  - mctl-api:
    - `internal/workitems/action_approvals.go`: `effectiveState`, `IntentHash`, `ConsumeActionApproval`, `MaxApprovalTTL`.
    - `internal/api/handlers_action_approvals.go`: `DecideActionApproval`, `isHumanAdmin`.
    - `internal/api/handlers_approval_grant.go`: `prepareApprovalGrant`, `bindApprovalGrant`, `spendApprovalGrant`, `approval_content_unbound`, `devLoopApprovalPolicyVersion`.
    - `internal/operations/registry.go`.
    - `internal/mcp/server.go`: `mctl_trigger_approve`.
    - `internal/audit/`.
    - `internal/commerce/receipt.go`.
  - mctl-agents:
    - `orchestrator/policy_checkpoint.py`, `action_approvals.py`, `proposal_state.py`, `run_incident_responder.py`, `run_implementer.py`, `execution_evidence.py`, `commerce_gateway.py`.
    - `temporal/activities/proposals.py` and `delegated_approval.py`.
    - Tests: `tests/test_proposal_digest*.py`, `test_action_approvals.py`, `test_delegated_approval.py`, `test_execution_evidence.py`.
  - mctl-gitops: the CWFTs `cwft-mctl-agents-approve.yaml`, `cwft-mctl-agents-implement.yaml` and `cronworkflow-mctl-agents-incidents.yaml`.
- To account for the new P1 evidence, the reinvestigate path is added to the reading list. That means the mctl-agents code that handles `@MCTL reinvestigate` and the code that creates and supersedes the DevLoop grant (#701), plus the projection of the approve result into `work_item.execution` and the loop result (#702). Their exact symbols were not confirmed in this run. The implementer locates them at the pinned SHA.

### Approve CWFT behaviour (read locally at mctl-gitops `4681bc0`)
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`:
- `expected_content_digest` is optional (lines 71-77). Empty "keeps the #658 behaviour: record the digest of whatever is there at flip time". This is the binding difference between P2 and P1.
- A malformed expected digest is refused (lines 209-219).
- An already-`accepted` proposal is a no-op. When an expected digest is set, the recorded `content_digest` must match it (lines 242-256).
- Any status other than `proposed` is refused (line 261).
- The digest is computed with the same framing as mctl-agents `proposal_state.proposal_content_digest` (lines 270-297).

### Deployed state checked
- `gh api repos/mctlhq/<repo>/commits/main` on 2026-10-18 shows all four mandatory repos are readable:
  - `.github` `6f35424f140a15557c3405ebed6d08851eb496b2`;
  - `mctl-api` `57864b56c07fdda5de9a52c404c33557e11c6e27`, which differs from the v2 pre-check `5dd4e73...`, so a re-pin is required;
  - `mctl-agents` `50e703dfcf75ce25c674f1151879d6bcc0e1c239`, the same as v2;
  - `mctl-gitops` `4681bc0adf91295d767f65c895c873f68fa2fd0f`.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api tag `4.102.0`.
- `platform-gitops/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`: tag `1.84.0`.
- `mctl_get_dev_loop(dev-loop-mctlhq-.github-182)`: `status: Completed`. That matches #702: a refused approval ended as Completed and not as abandoned.
- `mctl_get_dev_loop(dev-loop-mctlhq-.github-199)`: `status: Running`. This is the carrier loop.
- `mctl_list_agent_executions(workflow_id=dev-loop-mctlhq-.github-182)`: one record, `issue-investigator` 1.84.0, `mctl-agents-investigate-ef070691`, `Succeeded`, 13:43:57Z. The approve step does not appear as an agent execution.
- `mctl_get_workflow_status(mctl-agents-approve-6f23268b)`:
  - The audit row is at 14:17:40Z with operation `mctl-agents-approve`, `status: failed`.
  - Its parameters are `grant_ref=aar_d3572c56815543f59289fa3bf0a30f6d`, `expected_content_digest=sha256:09718ba2d821...277e`, `approver=mashkovd`, `actor_kind=agent`, `actor_name=issue-investigator`, `subject_principal_id=prn_01M39HRB7JRXZ2PHW5VVB695YZ` and `execution_id=we_dadf9c08-0156-4ffa-a306-a11e188ae921`.
  - The Argo phase is `Failed` at the `flip` (`flip-status`) step with exit code 1. The onExit notify step `Succeeded`.
  - The trace id is `9706d41dea602d8fe389f6a1021cbbd8`.
- `mctl_get_workflow_logs(mctl-agents-approve-6f23268b, step=flip)`: "issue-182-... changed after it was approved: the files hash to sha256:2ca80ff53425...9a17, the approval was for sha256:09718ba2d821...277e".
- Not observed in this run: the `action_approval.create/decision/consume` audit rows and the `work_item.execution` 14:18:26Z record with its `phase: Succeeded` projection. They are cited from the #199/#182 bodies. The implementer verifies them read-only, or labels them as cited and not observed.

## Proposed solution

This proposal is the same as the v2 design (mctl-gitops `178f7bf9a`) with three changes required by #199. The spike PR adds one file, `docs/spikes/agent-governance-decision-assurance.md`. It may also add one link line under a new "Spikes" heading in `AGENTS.md`. Nothing else changes.

Report structure, unchanged from v2:
1. **Header and non-claims.**
   - The report is the execution carrier for #182, run under #199, and #182's owner decides D5.
   - Spike completion does not mean runtime assurance has been delivered.
   - Links to #181, #182, #199, mctl-agents#681/#701/#702, #91, #18, #173, #55 and #151.
2. **Evidence pins.**
   - Repo, 40-hex SHA, read date and the files/tests read.
   - Deployed tags with their gitops path and date.
   - The read-only MCTL observations used.
   - A Blockers section, which must be empty for D1-D4 to proceed.
3. **Path inventory P1-P5**, with entry points and trust boundaries.
4. **D1**: one Mermaid sequence diagram per path, with `repo@sha:path#symbol` citations and an implemented/planned tag on every step.
   - P1 includes the reinvestigate edge, showing that proposal rewrite and grant lifecycle are separate, and the approve-result projection edge.
5. **Scope sections 1-8**, including the 11-field decision context marked present or missing per path.
6. **D2**: one matrix per path, with the 13 rows and the five-value status vocabulary.
7. **D3**: F1-F10 per path, with current behavior, invariant, evidence, gap and owner. Candidate #151 scenarios are named only.
8. **D4**: a `GovernedDecision` field map onto existing contracts, with gaps marked and append-only reference needs stated.
9. **D5**: a gap-to-owner table, then exactly one disposition, then "Recommended roadmap action (not applied in this PR)" as text.

Changes over v2, all required by #199:
- **D3 P1 production case (F1/F5).** A dedicated subsection, "2026-10-18 stale-grant refusal", with a timeline:
  - create 13:44:01Z, then reinvestigate rewrites v1 to v2;
  - decision 14:17:38Z, then consume 14:17:40Z;
  - the CWFT refusal between 14:17:40Z and 14:17:59Z;
  - `work_item.execution` at 14:18:26Z.

  It has three findings:
  - (a) **Held:** the decision-time content binding enforced `approved(v1) + attempt(v2) -> hard fail`. The enforcing code is the CWFT expected-digest check, and the report names its exact lines and the mctl-api grant spend that carried the digest. No `approval:` block was written for v2.
  - (b) **Not atomic:** proposal mutation does not invalidate or supersede a pending grant, so a human decided a grant for content that no longer existed (#701). This is a D2 "immutable proposal / approval expiry / invalidation on mutation" gap, owned by mctl-agents.
  - (c) **Misprojected outcome:** the refusal was projected as execution `Succeeded` and loop `Completed`, so the loop could not be restarted (#702). This is a D2 "end-to-end trace / governance metrics" gap. A mismatched-execution attempt that is recorded as success cannot be counted.

  The subsection also records that the grant was consumed (`action_approval.consume`) even though execution was refused. Whether a consumed-but-refused grant is correct replay protection or a lost decision is a stated F5 question.
- **Invariant.** "A free-text approval reason is descriptive metadata only; it confers no binding or authority." The approver wrote the v2 digest in the reason, and nothing checks it. The report places this invariant in D3 F1/F6 and maps it in D4: the reason is a descriptive field, and `artifact_hash`/`intent_hash` are the binding fields.
- **Re-pin.** mctl-api moved to `57864b5`. The report pins the SHA it actually reads and states whether the P1 anchors changed since `5dd4e73` and since deployed `4.102.0`. If that cannot be established, the claim is marked unverified.

Why this shape: #199 requires the scope to be identical to v2 unless pinned evidence forces a change. The production refusal is new evidence inside the existing F1/F5 frame, not a scope change. A single docs file keeps the roadmap control plane untouched and keeps D5 owner-reviewable.

## Alternatives

- **Restart `dev-loop-mctlhq-.github-182`.** Not possible. It ended `Completed` and not abandoned, and mctl-api#640 `restartIfAbandoned` only restarts abandoned loops. That is why this carrier exists.
- **Rewrite the scope around the incident, for example a P1-only lifecycle-atomicity audit.** Dropped. #199 fixes the scope as identical to v2. The incident is one D3 data point and does not replace the five-path audit.
- **Fix #701/#702 in the same PR, or file follow-ups.** Dropped. Both are forbidden by binding constraint 6 and are owned by mctl-agents.
- **Put the report under `docs/plans/` or apply the manifest delta.** Dropped for the same reasons as in v2: owner correction 2, and the fact that `docs/spikes/` is the accepted location.

## Platform impact

- **Migrations:** none. **Compatibility:** documentation only.
- **Roadmap control plane:** no manifest change, so `roadmap/scripts/*` validation and publication output are unchanged. #182 stays the only required item, and closing #199 does not complete it.
- **Resources:** source reads use shallow clones. Live evidence uses only read-only get/list calls.
- **Risks and mitigations:**
  - *Risk: the refusal is over-read as proof that P1 is fully safe, or the #681 proof leaks into P2-P5.* Mitigation: findings (a), (b) and (c) are kept separate, and each path has its own D2/D3.
  - *Risk: identifiers in the report expose sensitive data.* Mitigation: cite IDs, digests and timestamps only, and never payload bodies.
  - *Risk: stale pins.* Mitigation: re-pin at read time and record dates.
  - *Risk: a D5 bias carries over from the v1 proposal.* Mitigation: T4 checks that no disposition token appears before the D5 section.
