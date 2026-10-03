# Tasks: issue-141-roadmap-pause-communication-agent-and-re

Nothing below may start before a human approves this proposal. Tasks 1-2 are
read-only verification; tasks 3 onward mutate manifests, the GitHub graph, or both.

- [ ] 1. Confirm with the owner the three decisions this proposal encodes: pause
  `communication-agent` via `spec.lifecycle`; retire `mctl-gitops#1182` and
  `mctl-telegram#400` as not planned; reopen `mctl-telegram#440` (option A) rather than
  binding `mctl-telegram#683` as a new required work item (option B).
  — DoD: a written owner decision on each of the three, recorded on
  `mctlhq/.github#141`, including which #440 option is chosen.

- [ ] 2. Verify the pause suppression path end to end against the live publication,
  read-only. Check that `mctl_get_ready_work_items` with no epic omits every non-active
  epic (it omitted `edge-ai-android` and all five `completed` epics on
  2026-09-26), and record whether it filters an explicitly **named** paused epic.
  Record whether `mctl_plan_epic_wave` on `edge-ai-android` refuses with `epic_paused`
  (the documented contract; the attempt during investigation was intercepted by the
  MCP approval policy before reaching the epic check).
  — DoD: both answers recorded on #141 with the publication's `state_revision` and
  `capturedAt`; any divergence from the documented contract raised before task 3.

- [ ] 3. Open pull request A against `mctlhq/.github`: change
  `roadmap/epics/communication-agent.yaml` line 18 from `lifecycle: active` to
  `lifecycle: paused`. One line, nothing else. (depends on 1, 2)
  — DoD: `.github/workflows/roadmap-validate.yml` green; the diff is exactly one line;
  no work item, `required` flag, `dependsOn`, `parent` or `issue` binding changed.

- [ ] 4. Merge pull request A and confirm the pause landed in the publication.
  (depends on 3)
  — DoD: `roadmap-publish.yml` succeeded; `publication.json` shows
  `epics["communication-agent"].lifecycle: paused`; `mctl_get_ready_work_items` with no
  epic no longer returns the epic; `mctl_get_epic_status communication-agent` still
  shows `completion.status: incomplete` with `blocking: [c2-safety-gate, quota-domain]`
  and `health.state: healthy`; issues #518, #334, #347, #339, #340, #341, #350 are all
  still OPEN and unrelabelled.

- [ ] 5. Open pull request B against `mctlhq/.github`: in
  `roadmap/epics/client-lifecycle.yaml`, edit **only**
  `onboarding-integration.dependsOn`, removing `operator-identity-lookup` so it reads
  `[safe-broadcast, product-update-feed]`. Leave both `lookup-deployment` and
  `operator-identity-lookup` work items and the `identity` phase in place.
  (depends on 1)
  — DoD: roadmap-validate green; `plan.py` against a fresh snapshot shows exactly one
  operation, `RemoveDependency` with `opId f955af581e0687da`, precondition
  `DependencyPresent`, zero refusals, exit 1.

- [ ] 6. Merge pull request B and run the governed apply for it. (depends on 5)
  — DoD: `apply.py --live --execute --actor <actor> --approved-sha256 <sha of the
  merged bytes> --issue-ids <map including #400's numeric id>` records
  `opId f955af581e0687da` as `applied` or `alreadySatisfied`; the
  `RoadmapApplyResult` is archived; `mctlhq/mctl-telegram#679` no longer lists #400
  under "Blocked by".

- [ ] 7. Confirm the epic reconciles cleanly before proceeding. (depends on 6)
  — DoD: `reconcile.py roadmap/epics/client-lifecycle.yaml --live` reports zero drift
  entries; `health.py` exits 0. **Pull request C must not merge until this passes** —
  merging it early puts the manifest into the refused state described in task 8.

- [ ] 8. Open and merge pull request C against `mctlhq/.github`: in
  `roadmap/epics/client-lifecycle.yaml`, delete work item `lookup-deployment` (#1182)
  with its leading comment block, delete work item `operator-identity-lookup` (#400),
  and delete the now-empty `identity` phase. (depends on 7)
  — DoD: roadmap-validate green across the whole corpus; `plan.py` shows
  `operations: 0`, `refusals: 0`, `notes: 2` — `HierarchyUnexpectedChild` for
  `mctl-gitops#1182` and for `mctl-telegram#400`, both under `mctlhq/.github#22` — and
  exits 0; `health.py` exits 0; work items #438, #619, #439, #440 and #679 and every
  other epic manifest are untouched.

- [ ] 9. Verify whether the DevLoop `issue-poll` schedule
  (`cronworkflow-mctl-agents-issue-poll.yaml`, `*/15 * * * *`; ADR-005 "Temporal
  Schedule → DevLoopWorkflow") selects issues independently of roadmap lifecycle. A
  code search of `mctlhq/mctl-agents` during investigation found no roadmap-lifecycle
  awareness. If the poller is label- or state-driven, apply a GitHub-side hold to
  `mctl-telegram#334`, `#347`, `#339`, `#340`, `#341` and `#350` so the pause is
  enforced on that path too. (depends on 4)
  — DoD: the selection criteria are written down on #141; either the poller is shown to
  respect `lifecycle`, or the hold is applied and one full poll cycle passes with no
  DevLoop started for any of the six issues.

- [ ] 10. Apply the #440 remedy the owner chose in task 1. Option A (recommended):
  reopen `mctlhq/mctl-telegram#440`, citing the 2026-09-26T01:56:17Z acceptance matrix
  and noting that the 06:52Z closure came from release-please pull request #682.
  Option B: open a further pull request adding a required work item
  `product-update-delivery` bound to `mctl-telegram#683` in phase `updates` with
  `dependsOn: [product-update-feed]`, and add it to `onboarding-integration.dependsOn`.
  (depends on 1, 8)
  — DoD option A: #440 is OPEN; `mctl_get_epic_status client-lifecycle` shows required
  complete 3, ready 1 (`product-update-feed`), blocked 1 (`onboarding-integration`).
  — DoD option B: roadmap-validate green; the governed plan's new operations
  (`AddSubIssue` for #683 under #22, `AddDependency` #679 ← #683) are applied and
  reconcile shows zero drift.

- [ ] 11. Perform the manual GitHub operations that the governed apply path
  deliberately cannot. (depends on 8)
  — DoD: `mctl-gitops#1182` detached as a sub-issue of `mctlhq/.github#22` and closed
  with state reason **`not_planned`**; `mctl-telegram#400` detached from #22 and closed
  with state reason **`not_planned`**; neither closed as `completed`; a comment on each
  links `mctlhq/.github#141` and states that the shipped `admin:users` lookup tier
  (#511, #575) is retained and unaffected.

- [ ] 12. Request a fresh publication and record the final state of both epics.
  (depends on 4, 10, 11)
  — DoD: `publication_request.py` run and `capturedAt` moved; the after-state counts
  from `design.md` section 5 are confirmed against the live publication and posted on
  #141.

- [ ] 13. Optional hardening, separate slice, separate approval: add an optional
  `lifecycle` property to `$defs.epic` in
  `roadmap/schemas/roadmap-ready-set.schema.json` and
  `roadmap/schemas/roadmap-health.schema.json`, populated by `ready.render` and
  `health.render` from the validated manifest bytes the way
  `publish._epic_identity` already does. (depends on 4)
  — DoD: a separate issue is filed with this scope; if built, existing published
  `ready-set.json` and `health.json` documents still validate, `ready.consistency_errors`
  and `health` tests pass, and a new test asserts a paused manifest's ready set carries
  `lifecycle: paused`.

## Tests

- [ ] T1. Corpus validation after each manifest edit: `python roadmap/scripts/
  validate.py roadmap/epics` exits 0 with all 17 manifests PASS. Verified offline
  during investigation for both edited manifests.
- [ ] T2. Pause does not complete: `health.py roadmap/epics/communication-agent.yaml`
  against a live snapshot still reports `completion.status: incomplete`,
  `required.complete: 0`, `required.total: 2`, `blocking: [c2-safety-gate,
  quota-domain]`, `state: healthy`, exit 0.
- [ ] T3. Pause is relation-free: `plan.py roadmap/epics/communication-agent.yaml`
  reports `operations: 0`, `notes: 0`, `refusals: 0`, exit 0 — so merging pull request A
  requires no governed apply at all.
- [ ] T4. Pause is honoured by the consumer: `mctl_get_ready_work_items` with no epic
  omits `communication-agent` after task 4, and `mctl_plan_epic_wave communication-agent`
  refuses with `epic_paused`.
- [ ] T5. Sequencing guard (negative test, offline only): planning the **combined**
  Client Lifecycle change against today's graph refuses with
  `RemoveDependency targets an identity this manifest does not author:
  mctlhq/mctl-telegram#400` and exits 3, writing nothing. Reproduce this before task 5
  so the reviewer sees why the change is split.
- [ ] T6. Pull request B plan: exactly one operation, `RemoveDependency`,
  `opId f955af581e0687da`, blocked `mctl-telegram#679`, blocker `mctl-telegram#400`,
  precondition `DependencyPresent`, exit 1.
- [ ] T7. Pull request C plan: `operations: 0`, `refusals: 0`, exactly the two
  `HierarchyUnexpectedChild` notes for #1182 and #400 under `mctlhq/.github#22`,
  exit 0; `health.py` exit 0.
- [ ] T8. Idempotency: re-running the task 6 apply reports `alreadySatisfied` for
  `opId f955af581e0687da` and issues zero writes.
- [ ] T9. Unrelated children survive: after task 8, `client-lifecycle` still authors
  `client-reachability-preferences` (#438), `login-bot-update-receiver` (#619),
  `safe-broadcast` (#439), `product-update-feed` (#440) and `onboarding-integration`
  (#679), and the other sixteen epic manifests are byte-identical to before this change.
- [ ] T10. #440 evidence: after task 10 option A, `product-update-feed` reports
  `completion.reason: open` and `onboarding-integration` is `blocked` on it — i.e. #679
  is not offered as ready work on the strength of a release-please closure.
- [ ] T11. Unpause dry run (offline, before task 3 merges): flipping `lifecycle` back to
  `active` on a scratch copy reproduces today's ready set and health byte-for-byte,
  proving the pause needs no compensating change to reverse.

## Rollback

**Communication Agent pause.** Revert pull request A, or set `spec.lifecycle` back to
`active` in one line. Nothing else has to be restored: the pause changed no work item,
no `required` flag, no dependency and no issue, and `plan.py` is empty in both
directions, so there is no governed apply to undo and none that can be forgotten.
`roadmap-publish.yml` runs on the merge and the epic returns to wave selection with
exactly the ready set it has today. Confirmed by T11.

**Client Lifecycle retirement.** Heavier and asymmetric, so revert in reverse order:

1. Reopen `mctl-gitops#1182` and `mctl-telegram#400` (state reason cleared), and
   re-attach them as sub-issues of `mctlhq/.github#22` if task 11 detached them.
2. Revert pull request C, restoring the two work items and the `identity` phase.
   `plan.py` should then report zero operations, because the restored items are bound
   to issues that are open again.
3. Revert pull request B, restoring `operator-identity-lookup` in
   `onboarding-integration.dependsOn`. The next governed apply plans
   `DependencyMissing` → `AddDependency` and re-creates the
   `#679 ← #400` `blocked_by` edge.
4. Run `apply.py --live --execute` and confirm `reconcile.py --live` reports zero drift.

Do not revert pull request B before pull request C: that reproduces exactly the refused
state in T5.

**#440 remedy.** Option A is reversible by closing #440 again as completed. Option B is
reversible by reverting its pull request; the resulting `DependencyUnexpected` for
`#679 ← #683` is removable by a governed `RemoveDependency` because #683 would still be
authored at that point — the same ordering lesson as task 5.

**If anything is written that this proposal did not describe**, the audit trail is the
`RoadmapApplyResult` for each run: `opId`, `planId`, `manifest.sha256`,
`manifest.gitRevision` and the per-operation outcome. Every write is preceded by a
re-read and is one of four allow-listed calls, so an unrecorded mutation is not a state
the apply engine can produce.
