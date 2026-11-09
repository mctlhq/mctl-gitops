# Tasks: issue-1060-devloop-part-m-slice-m2b-1d-2b-ii-merge

Slice 1d-2b-ii of #1021. Tests, fixtures and one tool only, with no change under `orchestrator/`. The PR body uses
`Refs #1021` and `Refs #1060`, not `Closes`.

- [ ] 0. Baseline. On main (`0ef0e04` or later), run `tests/test_merge_watch_final_read.py`, `test_merge_watch_decision.py`,
  `test_workflow_replay.py`, `test_execution_request_replay.py`, `test_pre_m1_compat.py` and `test_patch_memoization.py`.
  Confirm `PATCHED_CALLS == 38`. — DoD: all green, and the output is pasted in the PR.
- [ ] 1. Shared constants and `terminal_reconcile` keyword (depends on 0). In `tests/test_merge_watch_final_read.py`,
  add `FINAL_READ_FIXTURE_DIR` and `RECORDING_PATCHES`. Add a `terminal_reconcile: bool = True` keyword to `_resume_run`,
  passed to `_resume_record`. Update the module docstring. — DoD: existing tests green and unedited apart from the
  keyword default.
- [ ] 2. Recorder `record_final_read(env, *, hop, monkeypatch)` (depends on 1), as in design section 1. It uses fixed
  workflow ids, `UnsandboxedWorkflowRunner`, 40-minute deadline, floor 1 for `hop`, and returns the deciding run's
  handle and the workflow id. — DoD: called from task 5 tests, and returns a Completed MERGED run.
- [ ] 3. Tool `tools/record_merge_watch_final_read.py` (depends on 2), in the style of `tools/record_pre_m1_histories.py`:
  env-var skip on `MERGE_WATCH_OUT`, `_scrub`, `_canonical_sha256`, `_write`, `test_manifest`, `test_fresh`,
  `test_hop`, and a docstring with the exact command. — DoD: a plain `pytest` run does not collect or record it, and
  running it with the env var writes three files.
- [ ] 4. Record and commit fixtures (depends on 3): `tests/fixtures/histories/merge_watch/dev_loop_final_read.json`,
  `dev_loop_final_read_hop.json`, `MANIFEST.json`. — DoD: files committed. The manifest names the recording commit and
  `temporalio` 1.34.0.
- [ ] 5. D15/D15a/D15b tests (depends on 2, 4), as in design section 4. — DoD: green. Each fixture replays clean, and
  the vacuity and manifest tests pass.
- [ ] 6. D16 (depends on 2), parametrized `nocache` and `restart`. — DoD: green, with one `terminal`, one
  `resolve_deploy_target`, and clean replay.
- [ ] 7. Carry-over D7 (T8a, T8b), D9 window, D12, D14 (depends on 1). — DoD: green. Size guard: if the slice does not
  fit one pass, the implementer STOPS and reports, keeps the D15/D16 core, and proposes a separate coverage issue that
  needs an owner GO. No test is deleted silently.
- [ ] 8. Evidence (depends on 5-7). For each mutation below, run the named tests on a scratch tree, confirm they are
  red, and revert. Paste the table in the PR. No mutation is committed. — DoD: every row red.

  | id | mutation (scratch only, `dev_loop.py`) | must turn red |
  |---|---|---|
  | f1 | drop the `_terminal_claim` call in `_decide_watch_end` | D15b vacuity, D16, D3 |
  | f2 | add one extra `_final_pr_read` call before the MERGED/CLOSED branch | D15b replay (committed fixture vs mutated code), D3 `len(reads)`. NOT D16 replay: a live run records and replays under the same mutated code |
  | f3 | evaluate `workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` also in the resume arm | T4 (marker count 1 on the in-test hop recording, expected 0); the committed hop fixture then also fails replay because the carried flag no longer matches the recorded commands |
  | f4 | swap the settle and the first read | T8b (in-flight gate scenario; D3-D6 cannot see it because nothing is in flight there) |
  | f5 | remove the abandon check after `_settle_watch_work` | D14 |
  | f6 | in `_final_pr_read`, skip the `get_pr_state` activity when `workflow.unsafe.is_replaying()` (a replay-only divergence, exact text recorded in the PR) | T7 `nocache` and `restart` (nondeterminism on replay); D3 stays green, so D16 is proven independent of D3 |

- [ ] 9. PR. State that this is 1d-2b-ii, tests and fixtures only, no release, B4 (#1007) FAIL, and the hold ON. List the
  deferred D13b-e, which are a mandatory input to the future 1d-3 proposal (#1061 is closed, historical reference only). — DoD: PR opened with `Refs #1021`.

## Tests

- [ ] T1 (D15b). `test_merge_watch_fixtures_replay_clean`, parametrized over both fixtures, with `RECORDING_PATCHES`
  applied, unsandboxed Replayer, and the manifest workflow id.
- [ ] T2 (D15b). `test_merge_watch_fixtures_are_not_vacuous`: marker 1 or 0, a post-deadline `get_pr_state`, a later
  `terminal`, `resolve_deploy_target` once, Completed.
- [ ] T3 (D15b). `test_merge_watch_manifest_matches`: sha256 per file, and the directory equals the manifest.
- [ ] T4 (D15). `test_final_read_marker_once_fresh_zero_continued`: on in-test recordings that reach the deadline.
- [ ] T5 (D15). `test_unpatched_record_across_the_deadline_makes_no_final_read_and_replays`: `_resume_run(
  terminal_reconcile=False)`, zero post-deadline reads, `watch_end == ""`, replay clean.
- [ ] T6 (D15a). `test_in_test_recordings_replay_clean`: every run of the fresh and hop chains, nothing written.
- [ ] T7 (D16). `test_duplicate_delivery_of_the_final_read_task[nocache|restart]`: one `terminal`, one deploy
  observation, Completed MERGED, replay adds no command.
- [ ] T8a (D7). `test_final_read_ordering_from_history` over D3-D6: first post-deadline read, then relinquishing write;
  none for D6. With nothing in flight the settle issues no command, so this test does not assert the settle position.
- [ ] T8b (D7, settle position). `test_settle_commands_precede_the_first_read`: `_released_gate_run` with `_StubbornWait`
  holding the gate in flight at the deadline. In history the cancel of the gate and the wait for it come BEFORE the first
  post-deadline `get_pr_state`, which comes before any relinquishing write. This is the only test that can turn f4 red.
- [ ] T9 (D9 window). Abandon during the gate window: one read, `abandoned-unverified`, `release`.
- [ ] T10 (D12). Final-read OPEN bookkeeping. MERGED first seen by the final read gives `acquire` then `terminal`.
- [ ] T11 (D14). Abandon while the settle waits on `_StubbornWait`: no read after the settle, `abandoned-unverified`,
  `release`.
- [ ] T12. Unchanged suites stay green: `test_workflow_replay.py`, `test_execution_request_replay.py`,
  `test_pre_m1_compat.py`, `test_patch_memoization.py`, `test_merge_watch_decision.py` (`PATCHED_CALLS == 38`).

## Rollback

The slice touches only `tests/` and `tools/`, and ships no artifact. Rollback is a revert of the merge commit, which
removes the fixtures, the tool and the tests. Nothing deployed or recorded in production depends on them. Workers stay
on 1.117.0 and the release hold stays ON. If a later intended change to the decision breaks T1, the remedy is a reviewed
re-record through `tools/record_merge_watch_final_read.py` with the reason in the PR. Deleting the fixtures is not a
remedy.
