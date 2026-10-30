# Tasks: issue-199-retry-spike-execute-182-governance-audit

- [ ] 1. Pin and read the sources. Shallow-clone `mctlhq/.github`, `mctl-api`, `mctl-agents` and `mctl-gitops`. Record each HEAD SHA and the date. Read the v2 anchors listed in design.md and their tests, plus the reinvestigate/grant-supersede and approve-result-projection code relevant to mctl-agents#701/#702. Add other repos, for example mctl-telegram, only if a claim depends on them, and pin them.
  - DoD: the Evidence pins table is filled in, and the mctl-api change since `5dd4e73` is assessed for the P1 anchors. If a mandatory repo cannot be read, write a Blockers section and stop before task 4.
- [ ] 2. Collect read-only live evidence (depends on 1).
  - Record the deployed tags from the gitops paths.
  - Record `mctl_get_dev_loop` for #182 (`Completed`).
  - Record `mctl_get_workflow_status` and `mctl_get_workflow_logs` for `mctl-agents-approve-6f23268b`.
  - Where readable, record the `action_approval.create/decision/consume` audit rows for `aar_d3572c56815543f59289fa3bf0a30f6d` and the `work_item.execution` record for `we_dadf9c08-0156-4ffa-a306-a11e188ae921`.
  - DoD: every live claim has a source and a date. Records that cannot be read are labelled "cited, not observed". No mutating call is made.
- [ ] 3. Build the path inventory and trust boundaries for P1-P5 (depends on 1).
  - DoD: each path has an entry point, its components, its boundaries, and `repo@sha:path#symbol` citations.
- [ ] 4. Write D1 (depends on 2, 3): Mermaid sequence diagrams in the actual evaluation order. P1 shows the reinvestigate edge and the approve-result projection.
  - DoD: every arrow is cited and tagged implemented or planned.
- [ ] 5. Write scope sections 1-8 (depends on 4).
  - DoD: each issue question is answered, with evidence or with `unknown (not observed)` and a reason.
- [ ] 6. Write D2 (depends on 5): one matrix per path, with the 13 rows and the five-value status vocabulary.
  - DoD: every row has an owner and evidence, and every "implemented" cell has a cited test or contract.
- [ ] 7. Write D3 (depends on 5): F1-F10 per path. Include the "2026-10-18 stale-grant refusal" subsection with findings (a) held, (b) not atomic (#701) and (c) misprojected (#702). Raise the consumed-but-refused grant as an F5 question. State the invariant that a free-text approval reason confers no binding or authority. Run only local bounded reproductions: the pinned repos' unit tests, and the approve CWFT digest script against fixture files in a scratch directory. Name the candidate #151 scenarios, for example "reinvestigate with a pending grant" and "refused approve projected as success".
  - DoD: the `approved(A)+attempt(B) -> hard fail` verdict is given per path with the enforcing code. P1 and P2 are kept distinct. P3 is classified only from the contract that was read.
- [ ] 8. Write D4 (depends on 6, 7): the `GovernedDecision` field map. The approval reason is mapped as descriptive and `artifact_hash`/`intent_hash` as binding. Append-only needs are stated.
  - DoD: every field is mapped or marked as a gap, with a citation.
- [ ] 9. Write D5 (depends on 8): the gap-to-owner table, exactly one disposition, and the recommended manifest delta as text only. If the disposition is CREATE NEW EPIC, include the EpicDefinition draft and DAG inline.
  - DoD: one disposition, every gap owned, and no edit under `roadmap/`.
- [ ] 10. Assemble the report with its header and non-claims. Optionally add the `AGENTS.md` link line. Open the PR referencing #199 and #182 (depends on 9).
  - DoD: the diff touches only those two files. The PR body states that #182's owner decides D5 and that the #181 lifecycle change is a separate PR.

## Tests

- [ ] T1. `git diff --name-only origin/main` lists only `docs/spikes/agent-governance-decision-assurance.md` and, optionally, `AGENTS.md`.
- [ ] T2. The roadmap validation and test suites under `roadmap/` pass unchanged.
- [ ] T3. A grep check on the report finds:
  - 40-hex SHAs for the four mandatory repos;
  - D1-D5, F1-F10 and all 13 D2 rows;
  - `aar_d3572c56815543f59289fa3bf0a30f6d` and `mctl-agents-approve-6f23268b`;
  - the free-text-reason invariant sentence.
- [ ] T4. No D5 disposition token appears before the D5 section, apart from the neutral list of options in the header. The D5 heading contains exactly one token.
- [ ] T5. Every Mermaid block renders.
- [ ] T6. The D3 reproduction commands re-run with the documented results against the pinned SHAs. The CWFT fixture run reproduces the "changed after it was approved" refusal for a mismatched digest.

## Rollback

The PR is documentation only. Close it unmerged or revert the merge commit. No runtime, manifest or lifecycle state is affected, and #182 stays open either way.
