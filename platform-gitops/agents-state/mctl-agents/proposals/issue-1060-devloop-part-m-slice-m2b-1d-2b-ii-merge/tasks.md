# Tasks: issue-1060-devloop-part-m-slice-m2b-1d-2b-ii-merge

Slice 1d-2b-ii of #1021. Tests and fixtures only; no file under `orchestrator/` changes. Base: `main` at `0ef0e04`.

- [ ] 0. Baseline. On a clean checkout of `main`, run `uv run --locked pytest -q tests/test_merge_watch_final_read.py
  tests/test_patch_memoization.py tests/test_workflow_replay.py tests/test_execution_request_replay.py
  tests/test_pre_m1_compat.py tests/test_merge_watch_decision.py` and record the result. — DoD: green, output kept for
  the PR.
- [ ] 1. Shared constants helper `_final_read_constants(monkeypatch, *, hop)` and `FINAL_READ_DEADLINE`,
  `MERGE_WATCH_DIR` in `tests/test_merge_watch_final_read.py` (depends on 0). — DoD: sets `dev_loop.MERGE_WATCH_DEADLINE`
  to 40 min and, for `hop`, `dev_loop.MERGE_WATCH_HISTORY_FLOOR` to 1; used by both the recorder and every replay test.
- [ ] 2. Recorder `record_final_read(env, *, hop)` (depends on 1), as in design section 1, with `_scrub`,
  `_canonical_sha256` and `_patch_ids` helpers. Update the module docstring (the committed-fixture half is now here).
  — DoD: both variants assert their own shape (fresh: MERGED, one post-deadline read, one `terminal`, no `release`;
  hop: at least two runs, last run `final-read` with one `release` at `fresh999`) and return the decision run's history
  and workflow id.
- [ ] 3. Tool `tools/record_merge_watch_final_read.py` (depends on 2), in the style of
  `tools/record_pre_m1_histories.py`: env var `MERGE_WATCH_OUT`, `test_manifest`, `test_fresh`, `test_hop`, `_write`
  with a `constants` entry per file. Docstring gives the exact command and says it records from the current tree. —
  DoD: `uv run ruff check tools/record_merge_watch_final_read.py` is clean, the documented command runs from the repo
  root, and CI does not collect the file.
- [ ] 4. Record the fixtures (depends on 3): `tests/fixtures/histories/merge_watch/dev_loop_final_read.json`,
  `.../dev_loop_final_read_hop.json`, `.../MANIFEST.json`. — DoD: files exist, contain no worker identity or stack trace,
  and `git diff --stat` shows nothing under `tests/fixtures/histories/` outside `merge_watch/`.
- [ ] 5. D15b and D7 tests on the committed fixtures (depends on 4). — DoD: green; listed under Tests.
- [ ] 6. D15a tests (depends on 2). — DoD: green; nothing written to disk.
- [ ] 7. D16 test with the `_CrashAfterFinalRead` subclass (depends on 1). — DoD: green.
- [ ] 8. Full suite (depends on 5-7): `uv run --locked pytest -q` and `uv run ruff check`. — DoD: both green; the
  files listed in requirements as "stay green" have no diff.
- [ ] 9. Red evidence (depends on 8). On a scratch worktree, by exact-text substitution, apply each mutation below to
  `orchestrator/temporal/workflows/dev_loop.py`, run only the named tests, record the red output, revert, confirm
  `git diff` is clean. — DoD: every row red with output; none in the diff.

  | Mutation | Change | Expected red |
  |---|---|---|
  | (shape) | in `_decide_watch_end`, call `_final_pr_read` twice on the MERGED branch | D15b replay (fresh) |
  | (tr) | drop `watch.terminal_reconcile` from the `else:` guard of the deadline arm | D15b replay (both), D15a |
  | (order) | issue the relinquishing write before `_final_pr_read` | D7, D15b replay |
  | (dup) | call `_terminal_claim(fresh, watch)` twice on the MERGED/CLOSED branch of `_decide_watch_end` | D16 (`terminal` count), D15b replay (fresh) |
  | (tamper) | edit one byte of a committed fixture (not `dev_loop.py`) | D15b hash check |

- [ ] 10. PR (depends on 9). Title references slice 1d-2b-ii. Description: `Refs #1021` (never `Closes`), links #1052,
  #1053, #1055, #1058, #1060 and this proposal's approved digest; pastes task 0 baseline, the recorder command used,
  manifest summary, mutation table output and full-suite result; states that no production code changed,
  `PATCHED_CALLS` stays 38, B4 (#1007) stays FAIL, the release hold stays ON, #1022 still blocks release, and 1d-3 /
  1d-4 are not started; lists the deferred carry-over (D9 window, D12, D13b-e, D14). — DoD: PR open. Nothing merged,
  released or deployed by the implementer.

## Tests

All new, in `tests/test_merge_watch_final_read.py`, on `WorkflowEnvironment.start_time_skipping()` unless they only
read JSON.

- [ ] T1 (D15b integrity). `MANIFEST.json` lists exactly the `*.json` files in `merge_watch/` (excluding itself); each
  canonical sha256 matches; no non-empty `identity` or `stackTrace`.
- [ ] T2 (D15b markers). Fresh fixture: `merge-watch-terminal-reconcile` patch id exactly once. Hop fixture: zero times,
  and the start input's `resume.terminal_reconcile` is true.
- [ ] T3 (D15b replay). Each manifest entry replays clean through `Replayer(workflows=[DevLoopWorkflow],
  workflow_runner=UnsandboxedWorkflowRunner())` with the entry's constants monkeypatched.
- [ ] T4 (D15a fresh and hop). `record_final_read` in-test, then replay the returned history in the same test: clean.
- [ ] T5 (D15a unpatched). Gap-harness scenario A record with `terminal_reconcile=False`: no `get_pr_state` scheduled
  at or after the deadline; its history replays clean.
- [ ] T6 (D7 ordering). Fresh fixture: first post-deadline `get_pr_state` schedule, then `lifecycle_ownership` with op
  `terminal`, then `resolve_deploy_target`; no `release`. Hop fixture: post-deadline `get_pr_state` schedule, then
  `lifecycle_ownership` with op `release`.
- [ ] T7 (D16). `_CrashAfterFinalRead` run with `max_cached_workflows=0`: one `WORKFLOW_TASK_FAILED`, one post-deadline
  `get_pr_state` schedule, `terminal` once, `resolve_deploy_target` scheduled once, `watch_end == "final-read"`; the
  history replays clean through the plain `DevLoopWorkflow`.
- [ ] T8 (regression). `tests/test_workflow_replay.py`, `tests/test_execution_request_replay.py`,
  `tests/test_pre_m1_compat.py`, `tests/test_patch_memoization.py`, `tests/test_merge_watch_decision.py` green and
  unedited.

## Rollback

Revert the merge commit. It removes the tests, the tool and the `merge_watch/` fixtures together; nothing deployed
depends on them and no production code changed. If a later change legitimately alters the decision's command shape,
re-record with the tool in that change's PR rather than deleting the fixtures.
