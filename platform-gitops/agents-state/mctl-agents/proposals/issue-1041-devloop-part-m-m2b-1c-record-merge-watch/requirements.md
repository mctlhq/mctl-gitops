# DevLoop Part M / M2b-1c: record_merge_watch_reconcile and confirm_no_pr activities

## Context

Issue mctlhq/mctl-agents#1041 is slice M2b-1c of the sequential plan recorded on #1021. It implements tasks 5 and 5a of
the #1021 proposal (`platform-gitops/agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/`
in mctl-gitops, approved digest `sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144`). Design
sections "3. Proof of absence" and "4. The record" of that proposal are the specification. They are not edited. This
proposal is the slice's own canonical proposal and needs its own digest-bound human approval. #1041 and #1021 grant no
implementation approval.

The slice adds two Temporal activities. Nothing calls them yet:

- `record_merge_watch_reconcile` writes an idempotent "reconciliation required" record on the source issue.
- `confirm_no_pr` proves that a proposal has no implementation pull request and no implementation branch, and fails
  closed.

M2b-1d will wire them into the merge watch of `DevLoopWorkflow`. They are split out so they can be reviewed, tested and
mutation-proved on their own, with no change to workflow behaviour or history shape. The #1029 gap harness
(`tests/test_merge_watch_worker_gap.py`) must still show the defect after this slice.

## User stories

- AS an operator I WANT a merge watch that cannot establish its PR state to leave exactly one trusted, visible record on
  the source issue SO THAT I know to reconcile it by hand, and a third party cannot suppress that record.
- AS the M2b-1d author I WANT a proof-of-absence activity that never reads a failed or ambiguous lookup as "no PR" SO THAT
  a grace-polls exit can be closed as no-PR only when that is actually true.
- AS a release owner I WANT this slice to add only registered, unscheduled activity types SO THAT no workflow history
  changes and rolling back is safe.

## Acceptance criteria (EARS)

### record_merge_watch_reconcile (`orchestrator/temporal/activities/issue_state.py`)

- R1. THE SYSTEM SHALL define frozen dataclasses `ReconcileRecordInput(repo: str, issue_number: int, workflow_id: str,
  deadline: str, exit_name: str, last_observed: str, open_request_ids: tuple[str, ...])` and
  `ReconcileRecordResult(status: str, url: str = "")`. `status` is one of `"recorded"`, `"already-recorded"`,
  `"issue-gone"`.
- R2. THE SYSTEM SHALL build the marker `<!-- merge-watch-reconcile-required workflow=<workflow_id> deadline=<deadline> -->`
  from the input alone.
- R2a. IF `workflow_id` or `deadline` is empty, contains whitespace or contains `--`, THEN THE SYSTEM SHALL raise
  `IssueStateError` before any HTTP request.
- R3. IF no GitHub token resolves, THEN THE SYSTEM SHALL raise `IssueStateError` and send no request.
- R4. WHEN the activity runs THE SYSTEM SHALL list every page of
  `GET /repos/<repo>/issues/<n>/comments?per_page=100`, following `Link: rel="next"` only when it points inside
  `https://api.github.com/`, before it decides whether to post.
- R5. IF any comment page has a transport error, answers a status other than 200 or 410, has a non-JSON or non-list body,
  has an item that is not an object, has a non-string `body`, has a missing or non-object `user`, has a `next` link outside the
  GitHub API, or goes beyond the page bound, THEN THE SYSTEM SHALL raise `IssueStateError` and post nothing.
- R6. IF a comment page answers 410, THEN THE SYSTEM SHALL return `ReconcileRecordResult("issue-gone")` and post nothing.
  A 404 SHALL raise `IssueStateError` and is never read as gone.
- R7. WHEN a comment body contains the marker AND its `user.login == "mctl-agents[bot]"` and `user.type == "Bot"`, or its
  `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR`, THE SYSTEM SHALL return
  `ReconcileRecordResult("already-recorded", <that comment's html_url>)` and post nothing.
- R8. WHILE the marker appears only on comments from other authors, including other bots and `mctl-agents[bot]`-named
  users whose `type` is not `Bot`, THE SYSTEM SHALL ignore those comments.
- R9. WHEN no trusted marker is found THE SYSTEM SHALL post exactly one comment whose body is the fixed template: the
  marker, the workflow id, the exit name, the last observed PR (`last_observed`, or `none` when empty), the open request
  ids (or `none`), and the instruction to read the PR by hand and then re-trigger or close the loop deliberately. The
  body SHALL carry no other data.
- R10. WHEN the post answers 201 with a non-empty string `html_url` THE SYSTEM SHALL return
  `ReconcileRecordResult("recorded", html_url)`.
- R11. IF the post has a transport error, answers 201 with no usable `html_url`, or answers anything else (401, 403, 404,
  410, 422, 429, 5xx or other), THEN THE SYSTEM SHALL raise `IssueStateError`.
- R12. WHEN the activity is retried after a post that reached GitHub but whose answer was lost THE SYSTEM SHALL find its
  own marker and return `already-recorded`, so that only one comment exists.

### confirm_no_pr (`orchestrator/temporal/activities/pr_state.py`)

- R13. THE SYSTEM SHALL define the frozen dataclass `NoPrProof(confirmed: bool, reason: str)`. `reason` is
  `"no-link-no-pull"` when confirmed, and otherwise the first thing that blocked the proof.
- R14. IF no GitHub token resolves, or `service` or `slug` is not a plain `[A-Za-z0-9._-]+` name, THEN THE SYSTEM SHALL
  raise `ProposalListingError` and send no request.
- R15. WHEN the status file
  `GET /repos/mctlhq/mctl-gitops/contents/platform-gitops/agents-state/<service>/proposals/<slug>/.status.yaml?ref=main`
  answers 404 THE SYSTEM SHALL return `NoPrProof(False, "status-file-missing")`.
- R16. IF the status file read has a transport error, answers a non-200 non-404 status, has a body that is not a JSON
  object, has `encoding != "base64"`, has missing or non-string `content`, fails strict base64 decoding
  (`validate=True` after removing newlines), or fails strict UTF-8 decoding, THEN THE SYSTEM SHALL raise
  `ProposalListingError`.
- R17. IF the decoded status file is empty or whitespace only, THEN THE SYSTEM SHALL return
  `NoPrProof(False, "status-file-empty")`. IF it has no line matching `^status:\s*\S`, THEN THE SYSTEM SHALL return
  `NoPrProof(False, "status-line-missing")`.
- R18. IF any line matches `^\s*["']?pr["']?\s*:`, whatever its value (blank, indented, quoted, a URL or anything else),
  THEN THE SYSTEM SHALL return `NoPrProof(False, "pr-line-present")`.
- R19. WHEN the status file passes R15 to R18 THE SYSTEM SHALL list
  `GET /repos/mctlhq/<service>/pulls?head=mctlhq:feat/agents-<slug>&state=all&per_page=100` over every page, following
  `Link: rel="next"` inside the GitHub API only.
- R20. IF any pulls page has a transport error, a non-200 status, a non-JSON or non-list body, a `next` link outside the
  GitHub API, or goes beyond the page bound, THEN THE SYSTEM SHALL raise `ProposalListingError`. A later page failing is
  never read as a shorter list.
- R21. IF any pulls page holds any item, including an item whose head does not match the branch, THEN THE SYSTEM SHALL
  return `NoPrProof(False, "pull-request-listed")`.
- R22. WHEN the listing is empty on every page THE SYSTEM SHALL read
  `GET /repos/mctlhq/<service>/branches/feat/agents-<slug>`. A 200 SHALL return `NoPrProof(False, "branch-exists")`, a
  404 SHALL continue, and a transport error or any other status SHALL raise `ProposalListingError`.
- R23. WHEN R15 to R22 all pass THE SYSTEM SHALL return `NoPrProof(True, "no-link-no-pull")`.
- R24. THE SYSTEM SHALL never return `confirmed=True` on a path where any read failed.

### Registration, invariants and evidence

- R25. THE SYSTEM SHALL register both activities in `orchestrator/temporal/worker.py` `short_activities`, and SHALL add
  same-named fakes to the `_fake_activities` registry in `tests/test_dev_loop_workflow.py`.
- R26. THE SYSTEM SHALL leave `post_issue_comment`, `get_issue_state`, `get_pr_state`, `PRState`,
  `orchestrator/temporal/workflows/dev_loop.py`, `DevLoopResult`, every carried dataclass, the `M1_ADDED` table in
  `tests/test_pre_m1_compat.py`, `tests/fixtures/` and `tests/test_merge_watch_worker_gap.py` unchanged.
- R27. WHILE this slice is applied, `tests/test_merge_watch_worker_gap.py` SHALL still pass and still show the defect
  (scenario A ends on a stale `OPEN` with no final read).
- R28. THE implementation PR SHALL show red-before-code and green-after-code for T-7 and T-17. It SHALL show each of
  mutations (k), (l), (af), (ad), (o), (p), (q), (ag) and (ah) applied locally, red, and reverted. It SHALL report the
  full suite result and `git diff --exit-code` on `tests/fixtures` and `tests/test_merge_watch_worker_gap.py`. Every
  command SHALL finish within 300 s.
- R29. IF any existing test or replay fixture would need editing or re-recording (beyond the additive `_fake_activities`
  registration of R25), or the gap harness would need a change, or a caller, patch marker or typed result field would be
  needed, THEN THE implementer SHALL stop and report on #1041 rather than work around it.

## Out of scope

- M2b-1d: the final read, `_decide_watch_end`, `_record_reconcile`, `_reconcile_heartbeat`, the typed result fields, the
  `cli.py` change, replay fixtures, and every caller of these two activities.
- Any change to `dev_loop.py`, to `DevLoopResult`, to `MergeWatchResume` or any other carried dataclass, or to the
  carried-dataclass pin table.
- Changes to `post_issue_comment` or `get_pr_state`.
- Any worker image, flag, deployment or release change, and any B4 (#1007) decision. Merge stays behind the code-owner
  hold from #1020, with no autonomous merge or admin bypass.

## Open questions

- Mutation (p) wording differs between sources. #1021 task 9 says "treat a recorded PR answering 404 as proven
  absence". #1041 says "treat a `pr:` line of a recorded PR as no link". `confirm_no_pr` never reads the recorded PR, so
  this proposal follows #1041: drop the `pr:` line check for a line carrying a PR URL. The #1021 wording would need
  `get_pr_state`-style PR reads that the specified algorithm does not contain.
- #1041 forbids test edits but also tells this slice to register the activities in `_fake_activities`. This proposal
  reads that as one sanctioned, additive edit: two new fake activity definitions appended to the returned list, with no
  existing assertion touched. If that reading is wrong, the STOP condition applies.
- A 410 on the POST, after a listing that answered 200, is treated as "any other answer" and raises (R11). The #1021
  design names 410 only "on the issue", meaning the listing. M2b-1d may want `issue-gone` there too. This slice leaves
  it strict.
- The #1021 design allows a 404 or an undecodable status file to return `confirmed=False` or to raise. This proposal
  fixes the split: 404, empty content and a missing `status:` line return `False` with a reason, and every shape or
  decode failure raises.
