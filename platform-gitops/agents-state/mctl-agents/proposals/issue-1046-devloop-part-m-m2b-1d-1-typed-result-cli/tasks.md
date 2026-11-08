# Tasks: issue-1046-devloop-part-m-m2b-1d-1-typed-result-cli

Scope: task 7 of the #1021 proposal only. Two production files (`orchestrator/temporal/workflows/dev_loop.py`,
`orchestrator/temporal/cli.py`) and one new test file (`tests/test_merge_watch_typed_result.py`). No existing test,
fixture or `tests/test_merge_watch_worker_gap.py` is edited. Any STOP condition from #1046 ends the work with a report
on the issue.

- [ ] 0. Baseline — DoD: on a clean checkout of main (`e6b70a3` or later), run the full suite and record the result of
  `tests/test_merge_watch_worker_gap.py`, `tests/test_pre_m1_compat.py` and the replay tests
  (`tests/test_workflow_replay.py`, `tests/test_execution_request_replay.py`, `tests/test_patch_memoization.py`); the
  same results are the target after task 5.
- [ ] 1. Types (R1-R4) — `_WatchOutcome.watch_end`/`reconcile_record`; the `WATCH_END_*`,
  `MERGE_WATCH_RECONCILE_REQUIRED_OUTCOME` and `MERGE_WATCH_RECONCILE_ENDED_FALLBACK` constants next to
  `ABANDONED_ENDED_PREFIX`; `DevLoopResult.watch_end`, `last_observed_pr`, `reconcile_record` appended after `security`,
  all defaulted. DoD: T3 and T4 pass; nothing else changes behaviour.
- [ ] 2. Result tail (R5-R9) (depends on 1) — in `_finish_after_watch`, `reconcile = outcome.watch_end ==
  WATCH_END_RECONCILE_REQUIRED`, `pr_state = None if reconcile else outcome.last`, the three stages unchanged and gated
  on `pr_state`, `ended`/`outcome`/`watch_end`/`last_observed_pr`/`reconcile_record` as in design section 2, the
  `MERGE_WATCH_RECONCILE_REQUIRED` warning; correct the `DevLoopResult.pr` and `_watch_pr` docstrings. No early return.
  DoD: T5 passes, every field asserted.
- [ ] 3. Delivery refusal (R10-R15) (depends on 1) — `MERGE_WATCH_RECONCILE_REFUSAL` beside the delivery constants (not
  in `RESUME_DEFERRAL_REASONS`); `self._reconcile_required = False` in `__init__`; check 1 after the
  `accepted_after_gates` block, check 2 right after `wait_condition`, both landing
  `_land_delivery(opened, "Failed", MERGE_WATCH_RECONCILE_REFUSAL, engine_ref)`; `wait_condition` predicate unchanged;
  nothing sets the flag. DoD: T6 passes; `grep -n "_reconcile_required = True" orchestrator/` finds nothing. If T6
  cannot exercise both checks without 1d-2/1d-3 wiring, STOP and report.
- [ ] 4. CLI (R16-R19) (depends on 1) — in `cli.status`, the reconcile-required branch before `result.pr is not None`,
  the `(last observed before abandon, not verified current)` suffix, the `none (confirmed)` branch before
  `not watched`; import the `WATCH_END_*` constants from `dev_loop`. DoD: T7 passes; existing `tests/test_temporal_cli.py`
  green unedited.
- [ ] 5. Invariants and mutation proof (R20-R22) (depends on 2, 3, 4) — DoD: full suite green with no edit to any
  existing test or fixture and no re-record; `git diff --stat main` touches only the two production files and the new
  test file; `grep -n "workflow.patched(" dev_loop.py` count unchanged from task 0; `record_merge_watch_reconcile` and
  `confirm_no_pr` still have no caller in `orchestrator/temporal/workflows/`; every mutation in the table below applied
  locally, shown red with the named test, reverted, and listed in the PR description; none in the diff.
- [ ] 6. PR — DoD: the PR body cites mctl-api `restartIfAbandoned` at its default branch (Q4), restates the B4/rollback
  paragraph of design.md, links #1046/#1021, and the PR is verified as blocked by GitHub (code-owner hold, #1020); if it
  is not blocked, stop. No merge, release or deploy.

### Mutations (each applied, shown red, reverted)

| Id | Mutation | Expected red test |
|---|---|---|
| (m) | Land an open delivery `Succeeded` on reconcile-required (check 2 lands `"Succeeded"`) | T6a, T6b |
| (an) | Drop check 2 (after the wait) | T6b |
| (d1) | Drop check 1 (after the bind) | T6c |
| (aag) | Move check 1 before the `accepted_after_gates` block | T6e |
| (pend) | Put a flag check before the `pending_phase` early return | T6f |
| (dec) | Remove the default of `DevLoopResult.watch_end` (or `last_observed_pr`) | T3 |
| (end) | Keep the abandon prefix ahead of `ended` on reconcile-required | T5b |
| (fb) | Drop the `MERGE_WATCH_RECONCILE_ENDED_FALLBACK` (empty `ended`) | T5c |
| (gate) | Gate the tail on `outcome.last` instead of `pr_state` on reconcile-required | T5d |
| (ret) | Early return instead of `pr_state = None` (skips the `patched` calls) | T5e |
| (cli1) | Put the reconcile-required branch after the `not watched` branch | T7a |
| (cli2) | Drop the `none (confirmed)` branch | T7b |
| (cli3) | Drop the abandoned-unverified suffix | T7c |

## Tests

All in `tests/test_merge_watch_typed_result.py`.

- [ ] T1. Inertness pins: `DevLoopWorkflow()` starts with `_reconcile_required is False`; `MERGE_WATCH_RECONCILE_REFUSAL
  == "merge-watch-reconcile-required"` and it is not in `RESUME_DEFERRAL_REASONS`; `MergeWatchResume` has no
  `reconcile_required` field; an AST scan of `dev_loop.py` finds no assignment of `True` to `_reconcile_required` and no
  `watch_end=` keyword in any `_WatchOutcome(...)` construction.
- [ ] T2. Command shape: a full DevLoop run to a MERGED PR on the existing time-skipping harness produces the same
  sequence of scheduled activities and patch ids as before (asserted against a list derived from the committed
  `tests/fixtures/histories/dev_loop_full.patched.json` fixture, read only), and its `DevLoopResult` has `watch_end == ""`, `last_observed_pr is None`,
  `reconcile_record == ""`, `outcome == ""`.
- [ ] T3 (T-13, old into new). A `DevLoopResult` payload without the three keys (hand-built, and every completed DevLoop
  result payload found in the committed fixtures under `tests/fixtures/histories/`, if any carry one) decodes through
  `DataConverter.default` into the new class with `watch_end == ""`, `last_observed_pr is None`,
  `reconcile_record == ""`, all other fields equal on the wire.
- [ ] T4 (T-13, new into old). A new `DevLoopResult` with all three fields set, encoded, decodes into a class rebuilt
  from the current fields minus the three (the `_rebuild` approach of `tests/test_pre_m1_compat.py`) without error, the
  three fields absent, and re-encoded back into the new class they are at their defaults. Docstring states this is the
  pinned rollback hazard.
- [ ] T5. `_finish_after_watch` result shape, via the probe workflow:
  - a. `_WatchOutcome(last=PRState(found=True, state="OPEN", ...), watch_end="reconcile-required",
    reconcile_record="https://github.com/.../issues/1#issuecomment-1", ended="merge watch deadline: ...")` ->
    `pr is None`, `last_observed_pr == last`, `reconcile_record` as given, `watch_end`, `outcome ==
    "merge_watch_reconcile_required"`, `ended` as given, `deploy`, `security`, `incidents` None, one
    `MERGE_WATCH_RECONCILE_REQUIRED` log record naming repo, workflow id, ended and record;
  - b. the same with `self._abandoned = True` (set by the probe) -> `ended` is the outcome's, not `abandoned: ...`;
  - c. `ended=""` -> `MERGE_WATCH_RECONCILE_ENDED_FALLBACK`;
  - d. `last=PRState(found=True, state="MERGED", merged=True, merge_commit="abc")` with reconcile-required -> no
    deploy-observation, security or incident activity scheduled, `deploy`/`security`/`incidents` None;
  - e. the patch ids recorded by the probe history for case a equal those of the same probe with `watch_end=""` and the
    same OPEN `last`;
  - f. `watch_end=""` with OPEN `last` and with abandon -> today's result (`pr == last`, `ended` abandon prefix,
    `outcome == ""`), new fields at defaults; `watch_end="abandoned-unverified"` -> same plus `watch_end` copied.
- [ ] T6 (T-12, reachable part). On the `tests/test_execution_request_resume.py` harness with `_FlaggedLoop` (test-only
  subclass with a signal that sets `_reconcile_required = True`), starting from a `MergeWatchResume` carrying an
  `OpenDelivery`:
  - a. flag set, then the dispatcher fulfils: the delivery polling its bind binds and lands `Failed` with refusal
    `merge-watch-reconcile-required`, never `Succeeded`;
  - b. a delivery whose bind and flag signal arrive so that `wait_condition` resolves in the activation that sets the
    flag -> the same (exercises check 2);
  - c. a loop not past the gates (parked at approval, `_gates_passed` False) with the flag set before the fulfil ->
    the delivery lands `Failed merge-watch-reconcile-required` while the loop is still RUNNING (exercises check 1);
  - d. a delivery that never binds, loop ended -> `request-not-fulfilled`, not `Succeeded`;
  - e. `accepted_after_gates=True` with the flag set -> `feedback-not-ready`;
  - f. `pending_phase="Succeeded"` carried with the flag set -> lands `Succeeded` as recorded (keeps its pending phase);
  - g. the same scenarios with `DevLoopWorkflow` (no flag) -> today's outcomes (`Succeeded` for a, b).
- [ ] T7 (T-13, CLI). With `_stub_client`-style stubs returning a real `DevLoopResult`:
  - a. `watch_end="reconcile-required"`, `pr=None`, implement succeeded -> prints
    `pr:          reconcile required (<record>)`, not `not watched`; with empty record prints `(no record)`;
  - b. `watch_end="no-pr-confirmed"`, `pr=None` -> `pr:          none (confirmed)`, not `not watched`;
  - c. `watch_end="abandoned-unverified"`, `pr` OPEN -> the existing line plus
    ` (last observed before abandon, not verified current)`;
  - d. `watch_end=""` -> output identical to today's for pr set, pr None with implement succeeded, and pr unresolvable.
- [ ] T8. Pins: the whole existing suite, every replay fixture and `tests/test_pre_m1_compat.py` green with no edit;
  `tests/test_merge_watch_worker_gap.py` unchanged with the task-0 result.

## Rollback

Revert the single implementer PR. The slice adds no marker, activity, command or persisted state that any history
depends on, and every result it can produce carries only default values in the new keys, so a revert loses nothing and
needs no fixture or data change. Rollback of the worker image below `883b3a1bf` (M2b-1b) remains unsafe for watches
whose first run recorded `merge-watch-terminal-reconcile`; this slice does not change that and is never released on its
own (release hold ON, #1022 open). Once 1d-3 produces reconcile-required results, a rollback below this slice would
make readers drop `watch_end`, `last_observed_pr` and `reconcile_record` silently (T4); that is to be weighed under
#1022/B4 before any release, not here.
