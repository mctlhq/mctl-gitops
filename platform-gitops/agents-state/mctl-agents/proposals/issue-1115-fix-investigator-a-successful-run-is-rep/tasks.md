# Tasks: issue-1115-fix-investigator-a-successful-run-is-rep

- [ ] 1. Add `_WriteConfinementHook` and `_write_confinement_hooks(dirs)` to
  `orchestrator/options.py`, reusing `_containing_dir` and `_FILE_EDIT_TOOLS`. The hook
  fails closed and its deny text names the absolute `$PROPOSAL_DIR` — DoD: hook unit tests
  pass (inside allowed, outside denied, `..` and symlink escape denied, malformed input
  denied).
- [ ] 2. (depends on 1) Compose the hook into all three investigator option paths
  (`build_issue_investigator_options`, `build_issue_investigator_options_from_plan` with
  and without a gateway) — DoD: `tests/test_options.py` equivalence tests still pass, and a
  new assertion checks that the hook is present with `allowed == (str(proposal_dir),)`.
- [ ] 3. In `investigate()` (`orchestrator/run_issue_investigator.py`), keep the
  pre-wrapper staging path in a new local `original_staging` before `staging = secure` —
  DoD: no behaviour change; existing tests pass.
- [ ] 4. (depends on 3) Add `_triplet_diagnostics(...)`: checked and original paths, a
  capped and `repr()`'d listing via `staging_fd`, a per-missing-name
  `os.stat(dir_fd=..., follow_symlinks=False)` with type, symlink and stat-error, and
  misplaced-directory detection under `proposal_dir.parent / original_staging.name`.
  Append its output to the `agent did not write: ...` error, keeping the existing prefix
  and wrong-type suffix — DoD: tests T2-T4 pass.
- [ ] 5. (depends on 4) Add the `agent-output-misplaced` outcome. Add
  `InvestigateResult.retryable` (default True, False for misplaced) and
  `EXIT_NOT_RETRYABLE = 3`, and make `main()` exit 3 for a non-retryable error. Document
  the code in the module docstring and next to the constant — DoD: T5 passes; every other
  error still exits 1.
- [ ] 6. (depends on 3) In the `finally` cleanup, remove the misplaced
  `proposals/<staging basename>/` only if it is a real directory with that exact basename,
  using the existing no-follow and fd-matched removal pattern; otherwise warn and leave it
  — DoD: T6 and T7 pass.
- [ ] 7. Follow-up PR in mctl-gitops (separate repo, not part of this PR): export the
  investigator RC from `run-investigator`, skip `investigate-fallback` when RC is 3,
  tighten the collect-step `ALLOWED` regex to refuse a dot-leading proposal directory,
  and delete `agents-state/mctl-api/proposals/.staging-kptjmuhc/` — DoD: a PR is opened
  and linked from the mctl-agents PR body.

## Tests

- [ ] T1. Reproduction (`tests/test_run_issue_investigator.py`, using `_investigate_harness`):
  a fake agent that writes the full triplet into `proposal_dir.parent.parent / "proposals" /
  proposal_dir.name` (the misplacement seen in mctl-api#549) and returns normally. Assert
  that `result.outcome_reason == "agent-output-misplaced"`, that the error names the
  misplaced path, and that nothing is published. This fails today, where the reason is
  `agent-output-missing` with no path; confirm by reverting task 5.
- [ ] T2. Same agent: assert that the error contains `checked=`, `original=`, `listing=[]`,
  `misplaced=` and, for each name, `requirements.md: absent` (the asserted diagnostic text).
- [ ] T3. Extend `test_a_triplet_document_written_as_a_symlink_is_refused`: the error also
  contains `design.md: type=symlink symlink=True`, and the existing
  `not a regular file` assertion still holds.
- [ ] T4. `test_a_genuinely_absent_document_still_reads_as_absent`: keeps
  `agent did not write: design.md`, has no `misplaced=`, has a listing with the two written
  names, and `outcome_reason == "agent-output-missing"`, so it remains retryable.
- [ ] T5. `main()` with a stubbed `investigate` returning a misplaced result exits 3, and
  with an ordinary error exits 1.
- [ ] T6. After the T1 run, `proposals/<staging basename>/` no longer exists. A
  pre-existing unrelated `proposals/issue-1-x/` is untouched.
- [ ] T7. A symlink placed at `proposals/<staging basename>` pointing elsewhere is not
  followed or removed through, and its target survives.
- [ ] T8. Hook tests (`tests/test_options.py`): a Write to
  `<proposal_dir>/human-input/draft.json` is allowed; a Write to the
  `proposals/<basename>/design.md` sibling is denied with the deny text naming
  `proposal_dir`.

## Rollback

Revert the mctl-agents PR and cut a new image. `retryable` and exit code 3 disappear, and
the CWFT, even if the gitops follow-up has already landed, sees only 0 or 1 again, so its
RC check is inert. If only the confinement hook misbehaves, revert task 2 alone: the
diagnostics and cleanup stand on their own.
