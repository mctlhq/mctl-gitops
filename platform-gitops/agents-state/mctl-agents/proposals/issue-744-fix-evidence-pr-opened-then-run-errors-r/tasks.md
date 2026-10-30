# Tasks: issue-744-fix-evidence-pr-opened-then-run-errors-r

- [ ] 1. Add `_note_subject_pr(pr_url, head_sha=None)` to
  `orchestrator/run_implementer.py`, next to `_note_pushed_head`, delegating to
  `evidence_producer.note("note_subject_pr_url", ...)` and doing nothing for a
  falsy URL — DoD: helper exists, docstring cites #744, never raises.
- [ ] 2. (depends on 1) In `_implement_one`'s new-PR path, call
  `_note_subject_pr(pr_url)` right after `_note_pushed_head(target)` and before
  `_note_pushed`, `update_status_yaml(ref, "implemented", ...)` and
  `_release_claim(...)` — DoD: a raise from any later step still leaves the PR
  on the active run evidence.
- [ ] 3. (depends on 1) In `_implement_one`'s preflight arms (`open`, `merged`,
  `closed`, `needs-triage`), call `_note_subject_pr(existing.pr_url,
  existing.head_sha)` before `update_status_yaml` / `_mark_needs_triage` —
  DoD: a raise from those writes seals a PR subject bound to
  `existing.head_sha`.
- [ ] 4. (depends on 1) In `_review_feedback_one`, keep the pre-push PR URL
  string from `pre_status` and call `_note_subject_pr(...)` right after
  `_note_pushed_head(target)`, before `_note_pushed` and the post-push
  `_load_status` — DoD: a raise after `_push_followup` seals a PR subject bound
  to the pushed head.
- [ ] 5. Sweep: confirm no other implementer arm returns `pr_url=None` after a
  PR was opened, adopted or pushed to (list the arms checked in the PR
  description) — DoD: sweep result written in the PR body.

## Tests

All in `tests/test_evidence_producer.py` (or a new
`tests/test_run_implementer_evidence_subject.py`), with
`MCTL_EVIDENCE_AMENDMENT_2=true` in the evidence environment and a fake post
capturing the sealed envelope, following the existing fixtures in
`tests/test_evidence_producer.py`.

- [ ] T1. New-PR path: monkeypatch the steps before push to succeed,
  `_push_and_open_pr` to return `https://github.com/mctlhq/<svc>/pull/7`,
  `_capture_head_sha` to return a fixed SHA, and `update_status_yaml` to raise
  (e.g. `RuntimeError("gitops write conflict")`). Call `implement_one`. Assert
  the sealed evidence has `subject == pull_request/<repo>/7@SHA` and no
  `("subject", "not_applicable", False)` gap; outcome is `failed`. Verify the
  test fails with task 2 reverted.
- [ ] T2. Same as T1 but `_capture_head_sha` raises: assert a required
  `("subject", "observation_failed", True)` gap and no `not_applicable`.
- [ ] T3. Review-feedback path: `_push_followup` succeeds, `.status.yaml` has
  `pr: https://github.com/mctlhq/<svc>/pull/7`, and the post-push
  `_load_status` (or `_note_pushed`) raises. Call `review_feedback_one`; assert
  a PR subject bound to the pushed head. Fails with task 4 reverted.
- [ ] T4. Preflight `open` arm: `_preflight_existing_result` returns
  `ExistingResult(action="open", pr_url=..., head_sha=SHA)` and
  `update_status_yaml` raises; assert the subject is bound to `SHA`.
- [ ] T5. Regression: a path that never opens a PR (e.g. "no commits") still
  seals `("subject", "not_applicable", False)`.
- [ ] T6. Success path unchanged: subject bound to the pushed head, outcome
  `succeeded` / `pr-opened`; existing evidence tests stay green.

## Rollback

Revert the single PR (helper plus four call sites plus tests). No data,
schema or deployed configuration changes, so a revert restores 1.89.0
behaviour exactly; evidence already sealed by the fixed version remains valid
under the unchanged schema.
