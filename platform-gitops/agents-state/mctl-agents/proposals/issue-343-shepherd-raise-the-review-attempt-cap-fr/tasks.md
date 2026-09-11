# Tasks: issue-343-shepherd-raise-the-review-attempt-cap-fr

- [ ] 1. Raise the constant: `MAX_REVIEW_ATTEMPTS = 3` → `5` in
  `orchestrator/run_shepherd.py:303`, and extend the comment block at `:300-302`
  with one sentence on why five (#343: three left no room for a review that finds
  something new on the fix) plus the explicit non-claim that this does not
  address #342 — DoD: `grep -n "^MAX_REVIEW_ATTEMPTS" orchestrator/run_shepherd.py`
  shows `5`; the comment above it no longer implies three.
- [ ] 2. Rewrite the worked tick example at `orchestrator/run_shepherd.py:1767-1772`
  (depends on 1) so the walk-through runs `tick 1: counter=0 -> call -> counter=1`
  through `tick 5: counter=4 -> call -> counter=5`, with the final line phrased
  against `MAX_REVIEW_ATTEMPTS` (`tick 6: counter=5 == MAX_REVIEW_ATTEMPTS -> flip
  to review-stuck, NO call`) — DoD: the example's arithmetic agrees with the new
  constant and the terminal tick is not a hard-coded number.
- [ ] 3. Make the surrounding prose symbolic (depends on 1): module docstring
  `orchestrator/run_shepherd.py:16` ("The 3-attempt cap" → "The
  `MAX_REVIEW_ATTEMPTS` cap") and the inline comment at
  `orchestrator/run_shepherd.py:1789` ("one of the three slots" → "one of the
  `MAX_REVIEW_ATTEMPTS` slots") — DoD: neither line states a digit.
- [ ] 4. Update the test-side prose (depends on 1): `tests/test_run_shepherd.py:8`
  ("T6: outer-loop 3-attempt cap" → "outer-loop `MAX_REVIEW_ATTEMPTS` cap"), the
  T6 section banner at `tests/test_run_shepherd.py:1662-1664`, and the docstring
  of `test_shepherd_ticks_stop_at_the_cap` at `tests/test_dev_loop_workflow.py:1690`
  ("after 3 address-review attempts" → "after `MAX_REVIEW_ATTEMPTS`
  address-review attempts") — DoD:
  `grep -rn "3-attempt\|three attempts\|after 3 address-review" orchestrator tests`
  returns nothing.
- [ ] 5. Update `README.md:266-272` (depends on 1): retitle "**Three-attempt
  cap.**" → "**Review-attempt cap.**" and change "After three consecutive
  `address-review` ticks" to "After five consecutive `address-review` ticks" —
  DoD: the README section describes a cap of five and no longer encodes the
  number in its heading.
- [ ] 6. Update the architecture facts (depends on 1):
  `docs/diagrams/archify/facts.yaml:214` → `max_review_attempts: '5'` and the
  review-loop note at `docs/diagrams/archify/proposal-status.lifecycle.json:32`
  ("up to three times" → "up to five times") — DoD:
  `python3 tools/diagram_facts.py` (no `--gitops`/`--api`) reports no drift on
  `shepherd.max_review_attempts`.
- [ ] 7. Rewrite T6 in `tests/test_run_shepherd.py:1665-1731` (depends on 1) as
  `test_outer_loop_review_stuck_at_max_review_attempts`: keep the existing
  `patch.object` harness (`find_pr_for_proposal`, `read_codex_review`,
  `read_copilot_review`, `apply_followup`, `trigger_review`) and drive
  `process_one` in a `for i in range(1, run_shepherd.MAX_REVIEW_ATTEMPTS + 1)`
  loop, asserting `decision == "address-review"`,
  `read_status(ref)["review_attempts"] == i` and `status == "implemented"` each
  pass, reloading `ref.review_attempts` from disk between ticks; then one final
  `process_one` returning `review-stuck`, with
  `len(apply_calls) == len(trigger_calls) == run_shepherd.MAX_REVIEW_ATTEMPTS` —
  DoD: no literal `1`/`2`/`3` attempt counts remain in the test; it reads the
  bound from the constant, and its docstring matches the new walk-through.
- [ ] 8. Pin the new boundary (depends on 7): inside the loop of task 7, assert
  at `i == 4` (guarded by `if run_shepherd.MAX_REVIEW_ATTEMPTS >= 4`) that the
  proposal is still `implemented` with `review_attempts == 4` and no
  `review-stuck` flip; and add a small
  `test_max_review_attempts_is_five` asserting
  `run_shepherd.MAX_REVIEW_ATTEMPTS == 5` with a `#343` reference in its
  docstring — DoD: reverting task 1 to `3` makes both fail, which is what
  acceptance criterion 2 requires.
- [ ] 9. Pin the operator-facing note (depends on 7): in the `review-stuck`
  branch assertion, check the written note contains
  `f"{run_shepherd.MAX_REVIEW_ATTEMPTS} follow-up attempts"` (reading
  `.status.yaml` via the existing `read_status` helper) — DoD: with the cap at
  `5` the note reads "persisted across 5 follow-up attempts"; the assertion
  contains no literal number and does not pin the full sentence.
- [ ] 10. Final sweep (depends on 1-9): `grep -rn "MAX_REVIEW_ATTEMPTS - 1\|attempts=3" tests/`
  returns only assertions written against the constant (today:
  `tests/test_run_shepherd.py:1995-2000`, which is already correct), and
  `grep -rn "MAX_REVIEW_ATTEMPTS" orchestrator tests tools docs README.md` shows
  every mention either the constant itself or symbolic prose — DoD: no bare `3`
  anywhere describes the cap.

## Tests

- [ ] T1. `test_outer_loop_review_stuck_at_max_review_attempts` — five
  consecutive `address-review` returns each call `apply_followup` + `trigger_review`
  and increment `review_attempts` to 1..5 with `status: implemented`; the sixth
  tick flips to `review-stuck` and calls neither. Exactly
  `MAX_REVIEW_ATTEMPTS` followups and triggers.
- [ ] T2. Boundary assertion inside T1: after the fourth round the proposal is
  still `implemented` with `review_attempts == 4` — fails at the old cap of `3`.
- [ ] T3. `test_max_review_attempts_is_five` — the constant is `5`; the single
  place the literal is allowed.
- [ ] T4. `review-stuck` note assertion — contains
  `f"{MAX_REVIEW_ATTEMPTS} follow-up attempts"`, i.e. "across 5 follow-up
  attempts" at the new value.
- [ ] T5. Regression, unmodified and must still pass: transient follow-up failure
  does not consume an attempt (`tests/test_run_shepherd.py:1905-1946`);
  deterministic failure does (`:1951-1986`); deterministic failure at
  `MAX_REVIEW_ATTEMPTS - 1` flips to `review-stuck` (`:1993-2021`) — the last one
  is already constant-driven and should pass at `5` with no edit.
- [ ] T6. `tests/test_diagram_facts.py::test_facts_from_code_extracts_every_local_fact_from_this_repo`
  still passes (the `^MAX_REVIEW_ATTEMPTS = (\d+)` regex at
  `tools/diagram_facts.py:62` still matches) and
  `python3 tools/diagram_facts.py` exits 0 rather than 3 for this key.
- [ ] T7. Full gate: `uv run pytest tests/`, `uv run ruff check orchestrator config tests`,
  `uv run mypy` — all green (`.github/workflows/pr-validation.yml`).

## Rollback

The change is one constant plus comments, tests and docs — no schema, no
migration, no gitops values. Revert the merge commit (`git revert -m 1 <sha>`) and
the cap is back to `3` on the next shepherd tick; running proposals are
unaffected because `review_attempts:` is read fresh from `.status.yaml` on every
tick and is a plain integer under either cap. The one asymmetry: proposals that
reached `review_attempts: 4` or `5` while the higher cap was live will be at or
over the reverted cap and will flip to `review-stuck` on their next
`address-review` tick — expected, and recoverable by an operator moving them back
to `implemented` (or `mctl_trigger_reconcile`), the same path used for a
`review-stuck` proposal today. If only the docs sweep needs undoing, revert the
`facts.yaml` / `proposal-status.lifecycle.json` hunks alone; the weekly
diagrams-refresh job will re-report the drift rather than break anything.
