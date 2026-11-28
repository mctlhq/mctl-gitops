# Tasks: issue-1132-feat-devloop-s1-replay-safe-event-wake-f

All production changes go in `orchestrator/temporal/workflows/dev_loop.py`. Tests go under `tests/`. Do not touch mctl-api, mctl-gitops, any `.status.yaml`, worker values or image tags.

- [ ] 0. Baseline check. Diff `_watch_pr`, `MergeWatchResume` and `_resume_merge_watch` between tag 1.117.0 and main (fetch tags first; the investigator's clone had none). Then measure on the pinned temporalio that an uninterrupted `wait_condition(pred, timeout=d)` emits the same command shape as `workflow.sleep(d)` (T13). — DoD: findings are written into the PR description. If the shapes differ, stop and report feasibility HOLD with a proposed split. Do not broaden the scope.
- [ ] 1. Add the constants: `EVENT_WAKE_ENABLED = False`, `EVENT_WAKE_PATCH = "merge-watch-event-wake-v1"`, `EVENT_WAKE_SIGNAL = "pr_event_wake_v1"`, `EVENT_WAKE_STATE_QUERY = "event_wake_state"`, `EVENT_WAKE_MIN_SPACING = 60s`, `EVENT_WAKE_MAX_READS_PER_SLOT = 3`, `EVENT_WAKE_MAX_READS_PER_RUN = 192`, `EVENT_WAKE_DEDUPE_MAX = 32`, `EVENT_WAKE_STALE_HEADS_MAX = 8`. Place them next to the merge-watch constants (around line 572), with comments that state the bounds. — DoD: the constants exist and are documented.
- [ ] 2. Add a pure `_parse_event_wake(args) -> _EventWake | None` plus a frozen dataclass `_EventWake(event_id, repository, pr_number, head_sha, run_id)`. It rejects unknown keys, wrong types, oversize values and bad regex matches. — DoD: unit tests (T2) pass with no workflow context.
- [ ] 3. Add instance state in `__init__`: `_wake_watch`, `_wake_pending`, `_wake_seen`, `_wake_superseded_heads`, `_wake_signal_at`, `_wake_last_head`, the counters and `_wake_ignored` (a dict). Add the `@workflow.signal(name=EVENT_WAKE_SIGNAL)` handler with the ordered guards from design section 2, and the `@workflow.query(name=EVENT_WAKE_STATE_QUERY)` (depends on 2). — DoD: the handler never raises, never awaits and never schedules anything.
- [ ] 4. Add `MergeWatchResume` fields, all defaulted: `event_wake: bool = False`, `wake_seen: tuple[str, ...] = ()`, `wake_superseded_heads: tuple[str, ...] = ()`, `wake_pending: bool = False`. Populate them in `_watch_pr`'s resume-record construction (line 6939), and rehydrate them in `_resume_merge_watch` before its first await. — DoD: an old record decodes with the wake path off. A round trip keeps each list within its cap.
- [ ] 5. In `_watch_pr` (depends on 1, 3 and 4):
  - Fresh arm: `event_wake = EVENT_WAKE_ENABLED and workflow.patched(EVENT_WAKE_PATCH)`. Resume arm: `event_wake = resume.event_wake`.
  - Set `self._wake_watch = watch` at loop entry and clear it in `finally`.
  - Clear `_wake_pending` before the scheduled `get_pr_state`.
  - Maintain `_wake_superseded_heads` in pure Python when a found head differs from the previous head.
  - Replace line 7195's sleep with the `if event_wake: _wait_slot_with_wake(...) else: workflow.sleep(...)` fork.

  DoD: with `event_wake` False the code path is textually the old one; T1 and T12 pass.
- [ ] 6. Implement `_wait_slot_with_wake(watch, service, slug, interval) -> _WatchOutcome | None` as in design section 3: an absolute slot end, debounce, per-slot and per-run caps, flag cleared before the read, the terminal path through `_apply_found_state` + `_terminal_claim`, and no other state mutated (depends on 5). — DoD: T3-T11 pass.
- [ ] 7. Add a replay scenario `dev_loop_event_wake` to `tests/replay_scenarios.py`. Run it with `EVENT_WAKE_ENABLED` monkeypatched True, and drive it with one matching signal that leads to a woken MERGED read. Record `tests/fixtures/histories/dev_loop_event_wake.patched.json` with `tools/record_workflow_history.py`. Keep every existing fixture unchanged and green (depends on 6). — DoD: T12 passes; the new fixture contains the marker exactly once.
- [ ] 8. Add a short entry to docs/adr/006-dev-loop-merge-deploy-monitor.md, or a note in docs/ beside it. It covers the signal contract, the caps, the default-off constant, the rollback constraint, and that the producer, consumer and canary are later slices under mctlhq/.github#437. — DoD: the doc is merged with the PR.
- [ ] 9. PR description. Record the measured fixture wake latency (workflow time from signal to read start), the no-op read count per scenario, the actual test list and run output, and the remaining risks. — DoD: present in the PR. There is no rollout step, no worker bump and no change to the constant.

## Tests

All tests run in `WorkflowEnvironment.start_time_skipping()` with mocked activities, following the style of tests/test_dev_loop_workflow.py and tests/test_merge_watch_*.py. Monkeypatch `EVENT_WAKE_ENABLED` where noted.

- [ ] T1. No events, constant False: the command sequence (timers, durations, activities) equals the baseline for a watch that merges at poll N. No `merge-watch-event-wake-v1` marker is present. Same check with the constant True and no signals: identical except the single marker, and every slot timer fires uncancelled.
- [ ] T2. `_parse_event_wake` table: valid payloads; each bound exceeded; unknown key; wrong types; bare string; empty args.
- [ ] T3. A matching event wakes a read ahead of the timer. The read starts at `max(signal, slot_start + 60s)`. A MERGED result ends the watch with `_WatchOutcome(last=MERGED)`. The ownership `terminal` write happens only when the claim is held. Record the measured latency.
- [ ] T4. A burst of 10 accepted distinct signals within one spacing window gives exactly 1 woken read. A duplicate `event_id` is ignored as `duplicate`. The per-slot cap of 3 and the per-run cap of 192 are enforced, and further wakes wait for the scheduled poll.
- [ ] T5. Each of these is ignored with the right reason and causes no read: mismatched repository; mismatched PR number; mismatched `run_id`; stale head; `unknown_pr` before the first resolve; `no_active_watch` before the watch and after it returns; `disabled` when `event_wake` is False.
- [ ] T6. A signal before a read (pending at slot start), and a signal during a woken read and during a scheduled read: exactly one follow-up read, or none when the scheduled read covered it.
- [ ] T7. Lost signal: with no signal delivered, a MERGED PR is detected at the next scheduled poll, exactly as in the baseline.
- [ ] T8. An OPEN, not-found or `ActivityError` woken read leaves `poll_index`, `polls_without_pr`, `terminal_status_polls`, `saw_open_pr`, `watch.last` and `_poll_index_for_heartbeat` unchanged. It schedules no `_shepherd_tick`, `_merge_gate` or ownership activity, and the shepherd tick count over a 2 h window equals the baseline. The grace give-up and the terminal-status exit happen at the same workflow time as without events.
- [ ] T9. Abandon: a signal after abandon is ignored. Abandon mid-slot is still observed at the slot boundary (same time as baseline), and the ownership release in `finally` is unchanged. Terminal PR: CLOSED from a woken read ends the watch like a scheduled CLOSED read.
- [ ] T10. Concurrent tick: a woken read while a tick task is in flight creates no second tick. The hop is not taken while a tick or gate is in flight. The deadline: the watch ends at the same absolute deadline, and `_decide_watch_end` runs unchanged.
- [ ] T11. Continue-as-new: force a hop by lowering `MERGE_WATCH_HISTORY_FLOOR`. Check that `event_wake`, `wake_seen`, `wake_superseded_heads` and `wake_pending` are carried and capped, that the marker is not re-evaluated on the hop (extend tests/test_patch_memoization.py), and that a pending wake carried across the hop gives one read in the new run.
- [ ] T12. Replay: every existing fixture in tests/fixtures/histories/ (`dev_loop_full.*`, `dev_loop_resumed.json`, `dev_loop_parked.json`, `pre_m1/`, ...) replays green against the new code with the constant at both False and True. The new `dev_loop_event_wake.patched.json` replays green. A negative check: removing the marker gate makes the new fixture fail replay.
- [ ] T13. Measurement, kept as a test: an uninterrupted `wait_condition(timeout=d)` and `workflow.sleep(d)` produce the same command shape on the pinned temporalio, and an interrupted one adds `CancelTimer`.
- [ ] T14. Safety: with mocks that fail on any call to `submit_and_wait`/CWFT, model, merge, approval or release activities, a woken read schedules only `get_pr_state` (plus `_terminal_claim`'s ownership write on terminal when the claim is held).

## Rollback

- This slice ships with `EVENT_WAKE_ENABLED = False`. No marker is ever written, so reverting the PR, or deploying any older worker including 1.117.0, is safe. Histories are unchanged.
- The constraint for the later canary slice: once a released worker runs with the constant True, histories carrying `merge-watch-event-wake-v1` cannot be replayed by older workers (TMPRL1100). Two safe paths:
  - Roll forward with the constant False. New watches stop adopting the path, and existing ones keep their carried path until they end.
  - Abandon or drain the marker-bearing watches (`mctl_abandon_dev_loop`) before downgrading the worker.

  The worker's `strategy: Recreate` (services/admins/mctl-agents-worker/values.yaml) already prevents old and new pods from polling at the same time.
