# Tasks: issue-349-a-proposal-committed-straight-to-accepte

- [ ] 1. Add `BLOCKED_APPROVAL_MISSING = "approval-missing"` and
  `unrunnable_reason(data) -> str | None` to `orchestrator/proposal_state.py`,
  returning the code only when `status == "accepted"` and
  `human_approval_satisfied(data)` is false. Do not change
  `human_approval_satisfied` itself — DoD: the new predicate is a pure function
  over a parsed status mapping, `ruff` and `mypy` pass, and no existing
  assertion in `tests/test_run_implementer_approval.py` changes.

- [ ] 2. Add `UnrunnableProposalError` to `orchestrator/proposal_state.py` and a
  guard in `update_status_file()` that raises it when the merged payload would
  be unrunnable AND the payload previously on disk was not already unrunnable
  (depends on 1) — DoD: writing `accepted` + `requires_human_approval: true`
  with no approval over a clean/absent file raises and leaves the file
  untouched; the same write over a file that is already in that state succeeds
  (this is what keeps the `blocked` annotation in task 5 legal); the
  incident-responder shape (`accepted`, no `control` block) still writes.

- [ ] 3. Add `blocked: str | None = None` to `ImplementResult` and a trailing
  `blocked: int = 0` to `BatchOutcome` in `orchestrator/run_implementer.py`;
  update `_batch_outcome()` to classify in the order
  `error -> blocked -> skipped_reason -> pr_url` (depends on 1) — DoD: a blocked
  result increments `blocked` and not `skipped`; existing equality assertions in
  `tests/test_run_implementer_summary.py` still pass unmodified.

- [ ] 4. Add `_approval_blocked_message(ref) -> tuple[str, str]` returning
  `(message, remedy)`, built from the proposal's `source` block (same read as
  `_issue_closing_line()`) and `workflow_id_for()` from
  `orchestrator.temporal.issue_ref` — DoD: with a `github_issue` source the text
  names `dev-loop-mctlhq-<repo>-<N>` and the
  `POST /api/v1/agents/dev-loop/<id>/approve` endpoint qualified by "if that
  execution is still running"; without one it states no DevLoopWorkflow exists
  and does not mention the endpoint; both variants state that
  `mctl-agents-approve` is a no-op on an already-accepted proposal and name
  re-publishing in `proposed` status as the recovery; neither suggests editing
  `approval.approved_by` by hand.

- [ ] 5. Add `_mark_blocked(ref, *, code, message, remedy)` that writes a
  top-level `blocked` block (`code`, `since`, `message`, `remedy`) via
  `update_status_yaml(ref, "accepted", ...)`, preserving an existing `since` and
  returning without writing when `code`, `message` and `remedy` are all
  unchanged (depends on 2, 4) — DoD: first call writes the block and leaves
  `status: accepted`; second call with identical state leaves the file
  byte-identical; the block contains no per-observation timestamp.

- [ ] 6. Rewrite the gate in `implement_one()`
  (`orchestrator/run_implementer.py:1166-1176`) to return
  `blocked=BLOCKED_APPROVAL_MISSING` with the message from task 4 as
  `skipped_reason`, keeping `counts_toward_limit=False`, and to call
  `_mark_blocked()` only when `dry_run` is false (depends on 3, 4, 5) — DoD: the
  gate still precedes the `--dry-run` early return
  (`tests/test_run_implementer_approval.py::test_the_refusal_precedes_the_dry_run_shortcut`
  still passes) and a dry run writes nothing to disk.

- [ ] 7. Pass `blocked=None` at the four `update_status_yaml()` call sites that
  already clear `failure`: the `in-progress` transition and the `open` /
  `merged` / `closed` adoptions (depends on 5) — DoD: a proposal that was
  blocked and is then approved has no `blocked` key after its next run; a
  `needs-triage` write leaves any existing `blocked` block in place.

- [ ] 8. Print `Finished: blocked` for a blocked outcome in `_implement_refs()`
  (depends on 3) — DoD: the progress marker distinguishes blocked from skipped;
  `tests/test_run_implementer_progress.py` still passes for the ready / failed /
  skipped cases.

- [ ] 9. Add `EXIT_BLOCKED_ONLY = 45` to the sentinel table and wire the summary
  and exit rule in `main()`: a dedicated `=== Blocked ===` section listing each
  blocked proposal with its code, a four-way `Totals:` line, then
  `failed -> exit 1`, `blocked and not succeeded -> exit 45`, otherwise `0`
  (depends on 3) — DoD: exit codes follow the table; `--dry-run` never returns
  45; the docstring at the top of `_review_feedback_exit_code()` is updated to
  note 45 is a batch-mode code and not reachable from review-feedback mode.

- [ ] 10. Update the module docstring of `orchestrator/run_implementer.py`
  (the "Idempotency" section) and `README.md`'s approve/implement description to
  describe the blocked outcome, the `blocked` key and exit 45 (depends on 9) —
  DoD: a reader of the docstring can tell blocked from skipped from failed
  without reading the code; English only, no emoji.

- [ ] 11. Open a follow-up issue on `mctlhq/mctl-gitops` covering (a) making
  `mctl-agents-approve` record `approval.approved_by` on an already-accepted
  proposal and (b) running the implement CWFT's `commit-and-push` step even when
  the implement step exits non-zero, and reference it from a comment beside
  `EXIT_BLOCKED_ONLY` (depends on 9) — DoD: the issue link is in the code
  comment so the cross-repo dependency is discoverable from here.

## Tests

- [ ] T1. `unrunnable_reason()` table: `accepted` + `requires_human_approval`
  + no approval returns `"approval-missing"`; `accepted` + named approver,
  `accepted` + no control block, and any non-`accepted` status all return
  `None`.
- [ ] T2. `implement_one()` on the reproduction shape returns
  `blocked == "approval-missing"`, `pr_url is None`,
  `counts_toward_limit is False`, and a `skipped_reason` that mentions
  `requires_human_approval`.
- [ ] T3. `_batch_outcome()` counts a blocked result under `blocked` and not
  under `skipped`; `BatchOutcome(succeeded=1, failed=1, skipped=1)` still
  compares equal to the outcome of the existing three-result fixture.
- [ ] T4. Idempotency: running the gate twice against the same proposal writes
  `.status.yaml` exactly once — capture the file bytes after the first run and
  assert they are unchanged after the second, including `updated_at`.
- [ ] T5. `--dry-run` blocks the proposal in the summary but leaves
  `.status.yaml` absent/unmodified.
- [ ] T6. `main()` exit codes: blocked-only run exits 45; blocked + a result
  with a `pr_url` exits 0; blocked + an `error` result exits 1; a run with
  neither exits 0. Drive through `monkeypatch` on `implement_one` as
  `tests/test_run_implementer_progress.py` already does.
- [ ] T7. Message content: with a `source` block of type `github_issue` for
  `mctlhq/mctl-design` issue 21 the remedy contains
  `dev-loop-mctlhq-mctl-design-21`; with no source block it contains no
  `dev-loop-` id and no `/approve` endpoint; both contain "no-op" and
  "`proposed`"; neither contains `approved_by:` as an instruction.
- [ ] T8. `update_status_file()` raises `UnrunnableProposalError` and leaves the
  previous bytes intact when a clean file would become `accepted` +
  `requires_human_approval` + no approval; permits the same write when the file
  was already in that state; permits `accepted` with no control block.
- [ ] T9. Clearing: a blocked proposal that gains
  `approval: {approved_by: someone}` has its `blocked` key removed by the
  `in-progress` transition; a `_mark_needs_triage()` write preserves it.
- [ ] T10. Regression guard on the investigator: the status file written by
  `run_issue_investigator.write_status_yaml` never satisfies
  `unrunnable_reason()` (it publishes `proposed`), asserted through the existing
  publish fixture in `tests/test_run_issue_investigator.py`.
- [ ] T11. Full suite green: `uv run pytest tests/`,
  `uv run ruff check orchestrator config tests`, `uv run mypy`
  (`CONTRIBUTING.md`).

## Rollback

Every change is additive and confined to `orchestrator/proposal_state.py`,
`orchestrator/run_implementer.py`, their tests and two doc paragraphs. No
migration, no schema change, no new dependency.

- Full revert: `git revert` the merge commit. The only durable artefact left
  behind is the optional `blocked` key in some `.status.yaml` files; it is
  ignored by every reader (`update_status_file()` preserves unknown fields and
  no consumer branches on it), so it can be left in place or removed from
  mctl-gitops with a one-line `yq` sweep at leisure.
- Partial rollback if the red workflow proves too noisy: revert task 9 alone.
  The blocked classification, the durable marker and the corrected message all
  keep working and the process returns to exiting 0.
- Partial rollback if the write-time guard (task 2) surprises an unforeseen
  writer: revert task 2 and the `previously-unrunnable` carve-out; tasks 5-7
  continue to work because `_mark_blocked()` only ever writes over a proposal
  that was already in the blocked state.
- No rollback is required in mctl-gitops, because nothing in this proposal
  changes a CWFT.
