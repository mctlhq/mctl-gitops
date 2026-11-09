# Tasks: issue-1041-devloop-part-m-m2b-1c-record-merge-watch

- [ ] 1. Baseline. On a clean checkout of `main` (at or after `883b3a1`), run the full suite and
  `uv run pytest tests/test_merge_watch_worker_gap.py -q`, each within the 300 s bound, in batches if needed. Record the
  pass counts. — DoD: the baseline counts are pasted into the PR. The gap harness passes and shows the defect.
- [ ] 2. Write T-7 (`tests/test_record_merge_watch_reconcile.py`) and T-17 (`tests/test_confirm_no_pr.py`) against
  the specified names, and run them before any implementation code exists. — DoD: the red output (ImportError or
  failing assertions) is pasted into the PR.
- [ ] 3. Implement `ReconcileRecordInput`, `ReconcileRecordResult`, `reconcile_marker`, `_is_trusted_author`,
  `reconcile_comment_body` and `record_merge_watch_reconcile` in `orchestrator/temporal/activities/issue_state.py`
  (depends on 2). — DoD: T-7 is green. A `git diff` shows `get_issue_state` and `post_issue_comment` unchanged.
- [ ] 4. Implement `NoPrProof`, `_ANY_PR_KEY_RE`, `_STRICT_STATUS_RE`, `_NAME_RE`, `_strict_status_content` and
  `confirm_no_pr` in `orchestrator/temporal/activities/pr_state.py` (depends on 2). — DoD: T-17 is green. A `git diff`
  shows `get_pr_state`, `PRState`, `_PR_FIELD_RE` and `_STATUS_FIELD_RE` unchanged.
- [ ] 5. Register both activities in `orchestrator/temporal/worker.py` (imports at lines 69 and 76, `short_activities`
  at line 680). Add the two additive fakes to `_fake_activities` in `tests/test_dev_loop_workflow.py` (depends on 3 and
  4). — DoD: `tests/test_worker_roles.py` and `tests/test_dev_loop_workflow.py` are green with no other edit. If any
  existing pin breaks, stop and report on #1041 which pin it is.
- [ ] 6. Mutation proof (depends on 5). Apply each mutation locally, run the named tests, paste the red output, and revert. No
  mutation may appear in the diff.
  - (k) `_read_comment_page` returns `[]` on a non-200 page. Expected red: `test_page2_500_raises_posts_nothing`,
    `test_page2_malformed_raises_posts_nothing`.
  - (l) `_is_trusted_author` returns `True`. Expected red: `test_third_party_marker_ignored_posts`,
    `test_other_bot_marker_ignored_posts`.
  - (af) `_is_trusted_author` accepts any `user.type == "Bot"`. Expected red: `test_other_bot_marker_ignored_posts`.
  - (ad) return `issue-gone` on 404 as well as 410. Expected red: `test_listing_status_raises[404]`.
  - (o) a status-file 404 returns `NoPrProof(True, ...)` or continues to the listing. Expected red:
    `test_status_file_404_not_confirmed`.
  - (p) a `pr:` line carrying a PR URL is treated as no link (skip the `_ANY_PR_KEY_RE` check when the value is a URL).
    Expected red: `test_pr_line_blocks[url]`.
  - (q) a non-200 later `pulls` page ends the loop as an empty list. Expected red: `test_pulls_page2_500_raises`.
  - (ag-1) drop the `encoding == "base64"` check and the `status:` line requirement. Expected red:
    `test_non_base64_encoding_raises`, `test_no_status_line_not_confirmed`.
  - (ag-2) use `^pr:` instead of `_ANY_PR_KEY_RE`. Expected red: `test_pr_line_blocks[indented]`,
    `test_pr_line_blocks[quoted_double]`, `test_pr_line_blocks[quoted_single]`.
  - (ah) treat a branch 200 as continue. Expected red: `test_branch_200_not_confirmed`.
  — DoD: every mutation is shown red, with commands and outputs pasted, and `git diff` after the revert is empty for the
  mutated files.
- [ ] 7. Final evidence (depends on 6). Run the full existing suite and state the result explicitly. Run
  `git diff --exit-code -- tests/fixtures tests/test_merge_watch_worker_gap.py` (must be empty) and
  `uv run pytest tests/test_merge_watch_worker_gap.py -q` (still green, defect still pinned). Also run
  `git diff --stat`: it must touch only `issue_state.py`, `pr_state.py`, `worker.py`, `tests/test_dev_loop_workflow.py` and
  the two new test files. — DoD: all of this is pasted into the PR, along with the activity names and the rollback
  consequence from the Rollback section.
- [ ] 8. Open the PR and verify that GitHub reports it blocked by the code-owner hold (#1020). If it is not blocked, stop
  and report. — DoD: the blocked state is recorded in the PR. There is no merge, release, deployment or flag change.

## Tests

- [ ] T-7a. Marker absent: the record posts once and returns `recorded` with the 201 `html_url`. The posted body equals
  `reconcile_comment_body(inp)`, contains the marker, the workflow id, the exit, the last observed PR or `none`, the
  request ids or `none`, and the instruction, and nothing else.
- [ ] T-7b. Marker on a `mctl-agents[bot]` / `Bot` comment with `author_association` `CONTRIBUTOR` returns
  `already-recorded`. So does the marker on an `OWNER`, `MEMBER` or `COLLABORATOR` comment (parametrized). No POST in
  either case.
- [ ] T-7c. Marker on a third-party `NONE` / `CONTRIBUTOR` comment, on another bot's comment (`renovate[bot]`, `Bot`),
  and on a `mctl-agents[bot]` login whose type is `User`: each is ignored, and exactly one POST follows.
- [ ] T-7d. Marker on page 2, reached through `Link: rel="next"`, is found, with no POST.
- [ ] T-7e. Page 2 answering 500, a malformed body (a non-list, or an item without `user`), a transport error, or a next
  link outside `api.github.com`: each raises `IssueStateError`, with zero POSTs.
- [ ] T-7f. No token raises before any request. A listing answering 401, 403, 404, 429 or 500 raises. A POST answering
  401, 403, 404, 410, 422, 429 or 500 raises.
- [ ] T-7g. A listing answering 410 returns `issue-gone`, with zero POSTs.
- [ ] T-7h. A 201 with no `html_url`, an empty one, or a non-JSON body raises.
- [ ] T-7i. The first POST lands server-side but the client gets `httpx.ReadTimeout`, so the first call raises. A second
  call finds the marker and returns `already-recorded`. One comment exists in total.
- [ ] T-7j. A `workflow_id` or `deadline` containing whitespace or `--` raises before any request.
- [ ] T-17a. A status file with `status: proposed`, no `pr` key, `200 []` on two pages and a branch 404 returns
  `NoPrProof(True, "no-link-no-pull")`.
- [ ] T-17b. Status file 404 returns `confirmed=False` (`status-file-missing`). Status file 500, a non-JSON body, a JSON
  list, `encoding` `"none"` or missing, invalid base64, or invalid UTF-8: each raises `ProposalListingError`. Empty or
  whitespace-only content returns `status-file-empty`. No `status:` line returns `status-line-missing`.
- [ ] T-17c. `pr:` lines, parametrized: blank, a URL, `null`, indented, `"pr":`, `'pr':`, and `pr :`. Each returns
  `pr-line-present`, and no pulls request is sent.
- [ ] T-17d. A non-empty listing returns `pull-request-listed`. That includes a page-1 item whose `head.ref` is an
  unrelated branch, and an item first appearing on page 2.
- [ ] T-17e. Pulls page 2 answering 500, a non-list body, or a next link outside the API: each raises.
- [ ] T-17f. Branch 200 returns `branch-exists`. Branch 500 or 403 raises.
- [ ] T-17g. A transport error at each of the three reads raises. No token raises before any request. An invalid
  `service` or `slug` (containing `/` or `..`) raises before any request.
- [ ] T-17h. Across all T-17 cases, `confirmed` is `True` only in T-17a. This is asserted by a shared helper.
- [ ] T-reg. `test_worker_roles.py` is green unchanged and the control plan's `activity_names` contains both new names.
  A new assertion goes in the new test files, not in `test_worker_roles.py`.

## Rollback

Revert the single implementation PR. Nothing schedules `record_merge_watch_reconcile` or `confirm_no_pr` before M2b-1d,
so no workflow history can reference them, and a worker build without them can safely receive every existing history.
The revert needs no data migration, fixture change or flag change. After M2b-1d ships, this changes: both activities
must stay registered in every worker build until no history that scheduled them remains open or replayable, and a
rollback below this slice would then need a new proposal.
