# Tasks: issue-182-spike-evaluate-mctl-governance-beyond-hu

- [ ] 1. Pin and read the sources. Shallow-clone `mctlhq/.github`, `mctlhq/mctl-api`, `mctlhq/mctl-agents` and `mctlhq/mctl-gitops`, and record each HEAD SHA and the date. Read the anchors listed in design.md "Current state", plus the related tests, in full. Add other repos (for example mctl-telegram, mctl-portal) only if a claim depends on them, and pin their SHAs too.
  - DoD: the "Evidence pins" table is filled in. If any mandatory repo is unreadable, write a Blockers section and stop before task 4.
- [ ] 2. Collect read-only deployed evidence (depends on 1). Record:
  - the mctl-api tag from `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`;
  - the agents worker tags from `platform-gitops/services/admins/mctl-agents-worker*/values.yaml`;
  - optionally, read-only MCTL calls (`mctl_list_recent_operations`, `mctl_get_dev_loop`, `mctl_list_agent_executions`) that confirm the P1 chain and the presence of audit records.
  - DoD: every deployed claim has a source and a date, and nothing mutating is called.
- [ ] 3. Build the path inventory and the trust boundaries (depends on 1).
  - The paths: P1 DevLoop grant approve, P2 standalone approve, P3 incident-responder autonomous path, P4 policy-checkpoint actions including delegated approval, and P5 commerce.
  - DoD: each path has an entry point, the components involved, its trust boundaries, and code citations in the form `repo@sha:path#symbol`.
- [ ] 4. Write D1 (depends on 2, 3): one Mermaid sequence diagram per path, in the actual evaluation order, with implemented and planned steps marked.
  - DoD: every arrow is backed by a citation, and no step is inferred from issue text alone.
- [ ] 5. Write scope sections 1-8 (depends on 4). Cover intent provenance, identity/authority (including F3 revalidation at spend versus decide), policy evidence, and the 11-field decision context marked present/missing per path. Also cover approval integrity, the durable end-to-end trace, reject/override/escalation, and the proposed governance metrics with their instrumentation limits.
  - DoD: each section answers the issue's questions, with evidence or `unknown (not observed)` and a reason.
- [ ] 6. Write D2 (depends on 5): one capability matrix per path, with the 13 mandatory rows and statuses taken from implemented / partial / missing / owned by another epic / unknown (not observed).
  - DoD: every row has an owner and an evidence cell. No "implemented" cell lacks a cited test or contract.
- [ ] 7. Write D3 (depends on 5): an F1-F10 table per applicable path, giving current behavior, the invariant, evidence, gap and owner.
  - Run safe bounded reproductions locally only: the pinned repos' unit tests, such as `tests/test_proposal_digest*.py`, `tests/test_action_approvals.py` and the mctl-api `workitems` / `api` approval tests, and the approve CWFT digest script against fixture files in a scratch directory.
  - Name candidate AssuranceScenarios for #151 without implementing them.
  - DoD: the `approved(A)+attempt(B) -> hard fail` verdict is stated per path, P1 and P2 are kept distinct, and P3 is classified for F10 only from the contract that was read.
- [ ] 8. Write D4 (depends on 6, 7): map the `GovernedDecision` fields to existing contracts (`ActionApprovalRequest`, `IntentHash`, execution evidence `ToolCallRef`, WorkItem/execution/snapshot, commerce receipt, audit `Entry`, principal IDs). Mark gaps, and decide where append-only references are needed.
  - DoD: every field is either mapped or marked as a gap, with a citation.
- [ ] 9. Write D5 (depends on 8): a gap-to-owner table, then exactly one disposition derived from D2/D3, then the recommended roadmap manifest delta and follow-up issue drafts as text only.
  - If the disposition is CREATE NEW EPIC, include a refined EpicDefinition draft and DAG inline.
  - DoD: one disposition, every gap owned, and no edit under `roadmap/`.
- [ ] 10. Assemble `docs/spikes/agent-governance-decision-assurance.md` with the header and non-claims. Optionally add a link line in `AGENTS.md`. Open the PR (depends on 9).
  - DoD: the PR diff touches only those two files, and the PR body states that the lifecycle change for #181 is a separate PR.

## Tests

- [ ] T1. `git diff --name-only origin/main` lists only `docs/spikes/agent-governance-decision-assurance.md` and, optionally, `AGENTS.md`.
- [ ] T2. `python roadmap/scripts/validate.py` (and the `roadmap/tests` suite) passes unchanged. This confirms that no manifest was touched.
- [ ] T3. A grep check on the report: it contains the Evidence pins table with 40-hex SHAs for the four mandatory repos; it contains F1 through F10, D1 through D5, and all 13 D2 rows; and it states exactly one disposition token in the D5 heading.
- [ ] T4. A grep check that no D5 disposition token appears before the D5 section, apart from the neutral list of options in the header.
- [ ] T5. Every Mermaid block renders, checked with GitHub preview or `mmdc` locally.
- [ ] T6. The reproduction commands listed in D3 re-run green or produce the documented failure against the pinned SHAs.

## Rollback

The PR is documentation only. Revert the merge commit, or close the PR unmerged. No runtime, manifest or lifecycle state is affected, so no other rollback is needed.
