# Design: issue-1132-feat-devloop-s1-replay-safe-event-wake-f

## Current state

All references are to main `eec4fdd` (2026-11-22) of `mctlhq/mctl-agents`
unless marked otherwise.

**Merge watch loop.** `DevLoopWorkflow._watch_pr` is at
orchestrator/temporal/workflows/dev_loop.py:6719. It works in three stages.

- Setup (lines 6762-6904):
  - It fixes the absolute `deadline`. This is `workflow.now() + MERGE_WATCH_DEADLINE` on a fresh start, or `resume.deadline`, never recomputed.
  - It evaluates its markers once. On a fresh start these are `fast-shepherd-cadence`, `shepherd-in-loop` (gated on `_shepherd_is_pinned()`), `concurrent-shepherd-tick`, `lifecycle-ownership`, `PROPOSAL_TERMINAL_PATCH` and `MERGE_WATCH_RECONCILE_PATCH`. On a resume they are carried from `MergeWatchResume`. `merge-watch-continue-as-new` and `gated-merge` are re-evaluated per run.
  - It builds a `_MergeWatchRun` (line 1842).
- Loop (`while workflow.now() < deadline and not self._abandoned`, line 6911). Each pass does five things:
  - Checks the hop predicate `_merge_watch_hop_suggested` (line 6520). The hop is refused while abandoned, while a tick or gate task is in flight, before one poll in this run has completed, and once past `MERGE_WATCH_MAX_HOPS=16`.
  - Calls the `get_pr_state` activity (line 6982).
  - On a transient error it does `await workflow.sleep(cadence.poll_interval)` (line 7017).
  - On found:
    - It calls `_apply_found_state` (line 6580). That sets `watch.last` and `self._last_pr`, resets `polls_without_pr`/`terminal_status_polls`, sets `saw_open_pr`, increments `_poll_index_for_heartbeat` and calls `_track_ownership`, which runs ownership activities.
    - MERGED or CLOSED leads to `_terminal_claim` and a return (lines 7021-7026).
    - Otherwise `watch.poll_index += 1`, then shepherd tick scheduling (lines 7032-7076) and merge gate scheduling (lines 7084-7137).
  - On not found: `polls_without_pr`, the terminal-status confirmation (`PROPOSAL_TERMINAL_CONFIRM_POLLS`) and the grace give-up (`pr_lookup_grace_polls`) (lines 7138-7189). The pass ends with `polls_this_run += 1` and `await workflow.sleep(cadence.poll_interval)` at line 7195.
- `while ... else` deadline decision `_decide_watch_end` (line 6680), then `finally` (line 7213): settle tick and gate, release or terminal the ownership claim unless hopping.

**Cadence.** `_Cadence`/`CADENCE`/`LEGACY_CADENCE` (lines 829-872). The poll interval is 15 min (`MERGE_POLL_INTERVAL`, line 572) under `CADENCE`. Every other wall-clock bound is a poll COUNT against it:

- tick every poll, after poll 1;
- 96 ticks maximum;
- heartbeat every 8 polls;
- unknown-write limit 12;
- refusal backoff 40;
- grace 8;
- merge-gate off reprobe 8 (`MERGE_GATE_OFF_REPROBE_POLLS`, line 613).

Anything that increments `poll_index`, `polls_without_pr`, `terminal_status_polls` or `_poll_index_for_heartbeat` speeds up those clocks. That is the main constraint on this design.

**Continue-as-new.** `MergeWatchResume` (line 1660) is a flat, fully defaulted, frozen dataclass. Its rule is that decisions are carried, never re-derived (lines 1685-1702). It is rehydrated by `_resume_merge_watch` (line ~4704) before the first await, so signals arriving in the continue-as-new gap are not lost (comments at lines 4756-4764).

**Existing signal patterns.**

- `abandon` (line 3730): a defensive parse that never raises. Its docstring states that a signal handler is not a workflow command and needs no patch marker. Abandon is observed only at the `while` condition, so today a mid-sleep abandon waits for the slot to end.
- `ActionApprovalWorkflow.decided` (orchestrator/temporal/workflows/action_approval.py:298) is the model to copy. It validates the reference against `self._approval_id` and ignores and counts mismatches (`_ignored_signals`). An accepted signal sets only a `_wake` flag, which `wait_condition(lambda: self._wake, timeout=...)` consumes (line 422). The authoritative read (`_poll`/`_recheck`) then decides. The timer remains the lost-signal fallback.

**Replay test harness.**

- tests/test_workflow_replay.py replays the committed histories in tests/fixtures/histories/. These include `dev_loop_full.{prepatch,patched}.json`, `dev_loop_resumed.json`, `dev_loop_parked.json` and `pre_m1/`.
- The fixtures are recorded by tools/record_workflow_history.py from tests/replay_scenarios.py (`SCENARIOS`, line 228).
- Its docstring measures that replay detects added, removed or reordered commands, but not attribute changes such as timer duration, nor divergence in the last workflow task.
- tests/test_patch_memoization.py pins marker memoization and the "evaluated fresh, carried on hop" rule, for example `test_the_terminal_reconcile_marker_is_recorded_once_fresh_and_never_on_a_merge_watch_hop`, line 303.

**Temporal Python timer behaviour relied on.**

- `workflow.sleep(d)` and `workflow.wait_condition(pred, timeout=d)` both emit one `StartTimer(d)`. When the timer is not interrupted, both end with `TimerFired`.
- When the predicate becomes true first, `wait_condition` emits `CancelTimer`. That is a new command and the reason the wake path must be behind a marker. The task-level test T13 re-measures this on the pinned temporalio, in the style of the existing measured table.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`:
  - `image.tag: "1.117.0"`, `replicaCount: 1`, `strategy: Recreate`.
  - The comment there explains that Recreate exists because a new marker (`deferred-resume-contract`) cannot be replayed by an older worker (TMPRL1100, mctlhq/mctl-agents#1007 B4).
  - So the live worker is 1.117.0, as the issue says, and there is no Temporal worker versioning. No grep hit for `build_id`/`WorkerDeployment` in orchestrator/temporal/*.py.
- `services/admins/mctl-agents-worker-exec` and `services/admins/mctl-agents-worker-implement` exist; their values files were found by grep but not read in detail. Not relevant to the workflow worker.
- `git tag` in the clone returned no tags, so the 1.117.0 source (issue lines dev_loop.py:519/6227/6505/6708) could NOT be read. Not observed; recorded under Open questions.
- No mctl MCP calls were made. Live Temporal or Valkey state is out of scope for this slice and was not read.

## Proposed solution

One file of production code (`orchestrator/temporal/workflows/dev_loop.py`), plus tests and fixtures. No new workflow, no new activity, no new dependency, no second controller.

### 1. Gating: code constant, then marker, then carried flag

```python
EVENT_WAKE_ENABLED: Final = False          # shipped default: off
EVENT_WAKE_PATCH = "merge-watch-event-wake-v1"
```

In `_watch_pr`'s fresh-start arm, next to `MERGE_WATCH_RECONCILE_PATCH`:

```python
event_wake = EVENT_WAKE_ENABLED and workflow.patched(EVENT_WAKE_PATCH)
```

In the resume arm: `event_wake = resume.event_wake`. Add the new field `MergeWatchResume.event_wake: bool = False`.

- With the constant False, `patched` is never called, so the history is byte-identical to today.
- With it True, histories that already passed the watch start replay `patched` as False (memoized, migration by attrition). Only fresh watches adopt the wake path. A hop never adopts it.
- Short-circuiting means a flip from True back to False makes new watches skip the marker. Watches that already recorded it stay on the wake path, because the flag is carried. See Rollback in tasks.md for the replay caveat.

### 2. Signal `pr_event_wake_v1` (handler only, no commands)

`@workflow.signal(name=EVENT_WAKE_SIGNAL)` with `def pr_event_wake(self, *args: object) -> None`. It is modelled on `ActionApprovalWorkflow.decided`.

- A pure helper `_parse_event_wake(args) -> _EventWake | None` does the bounds, regex and unknown-key rejection. It is unit-testable without a workflow context.
- Guards are checked in this order, and the first failing one is counted in `_wake_ignored[reason]`:
  1. `disabled` (no watch with `event_wake`);
  2. `malformed`;
  3. `no_active_watch` (`self._wake_watch is None`; set at loop entry and cleared in `finally`);
  4. `abandoned`;
  5. `unknown_pr` (`self._wake_watch.last` not found);
  6. `mismatch` (repo case-folded, or number);
  7. `mismatch_run` (`run_id` given and differing from `workflow.info().run_id`);
  8. `duplicate` (`event_id` in `_wake_seen`, a tuple ring capped at `EVENT_WAKE_DEDUPE_MAX=32`, insertion order);
  9. `stale` (`head_sha` in `_wake_superseded_heads`, capped at 8).
- When accepted: append to the ring, `_wake_accepted += 1`, `_wake_pending = True`, `_wake_signal_at = workflow.now()`. Nothing else.
- Signal order is history order, so all this state is deterministic. No hash ordering enters it.
- `_wake_superseded_heads` is maintained in pure Python where `_watch_pr` already sees a found state whose `head_sha` differs from the previous `watch.last.head_sha`. No command is added there.

### 3. The wait that replaces the bottom sleep (wake path only)

Line 7195 becomes:

```python
if event_wake:
    ended = await self._wait_slot_with_wake(watch, service, slug, cadence.poll_interval)
    if ended is not None:
        return ended          # a woken read saw MERGED/CLOSED; finally runs as today
else:
    await workflow.sleep(cadence.poll_interval)
```

`_wait_slot_with_wake`:

```text
slot_end = now + interval            # absolute; never extended or shortened
reads = 0; next_ok = now + EVENT_WAKE_MIN_SPACING
loop:
  remaining = slot_end - now; if remaining <= 0: return None
  if _wake_pending and not _abandoned and reads < PER_SLOT and run_reads < PER_RUN:
      if now < next_ok:  await workflow.sleep(min(next_ok - now, remaining)); continue   # debounce timer
      _wake_pending = False; reads += 1; run_reads += 1
      state = get_pr_state(...) with PR_STATE_TIMEOUT / PR_STATE_RETRY_POLICY  (ActivityError -> count, continue)
      record latency = now - _wake_signal_at; _wake_last_head = state.head_sha
      if state.found and state.state in (MERGED, CLOSED):
          await self._apply_found_state(state, watch); await self._terminal_claim(state, watch)
          return _WatchOutcome(last=state)
      _wake_noop_reads += 1; next_ok = now + EVENT_WAKE_MIN_SPACING; continue
  try: wait_condition(lambda: self._wake_pending, timeout=remaining); continue
  except TimeoutError: return None
```

The scheduled poll clears `_wake_pending` before its `get_pr_state`.

Properties this gives:

- **No events.** Each slot is one `StartTimer(interval)` and one `TimerFired`, the same shape as `workflow.sleep`. Under the marker the only difference is the marker itself.
- **Wake latency.** A woken read starts at `max(signal time, slot start + 60 s)`. The bound is 60 s plus the activity duration, against 15 min today.
- **Clocks stay put.**
  - A non-terminal woken read changes none of `poll_index`, `polls_without_pr`, `terminal_status_polls`, `saw_open_pr`, `watch.last` or `_poll_index_for_heartbeat`.
  - It schedules no tick, gate or ownership activity.
  - Tick cadence and budget, heartbeat, refusal backoff, grace, terminal-status confirmation, gate reprobe and the deadline therefore all keep their wall-clock meaning.
  - The next scheduled poll lands at `slot_end`, which is the same time as today.
- **Terminal by event.** A woken read that sees MERGED or CLOSED goes through the same terminal statements as a scheduled poll. Today one MERGED/CLOSED read already ends the watch. The confirmation rule applies only to the not-found proposal-status exit, which woken reads never touch.
- **Legacy sweeper owns the PR.** `_terminal_claim` writes only when `self._owned_entity_id` is set, which means the loop already held the claim. No acquire is ever issued from a woken read.
- **Abandon.** Abandon is not in the wait predicate, so it is still observed at the slot boundary as today. No woken read starts once `_abandoned` is set.
- **Hop.** The hop check stays at the loop top. A woken read is awaited inline in the slot, so the hop is never taken mid-read. The tick and gate in-flight guards are unchanged.
- **Signal before or during a read.** The flag is cleared before the read starts, so a signal during the read sets it again. The result is exactly one follow-up read, subject to the caps. A signal before the watch starts, or after it ends, is ignored (`no_active_watch`).
- **Lost signal.** The scheduled poll is the fallback, at 15 min under `CADENCE`.

### 4. Caps and history budget

| cap | value | why |
| --- | --- | --- |
| `EVENT_WAKE_MIN_SPACING` | 60 s | debounce; at most about 15 woken reads per 15-min slot in theory, capped below |
| `EVENT_WAKE_MAX_READS_PER_SLOT` | 3 | at most 4 reads per slot, counting the scheduled one |
| `EVENT_WAKE_MAX_READS_PER_RUN` | 192 | reset per run; with about 9 events per woken read (CancelTimer/StartTimer pair, activity scheduled/started/completed, task events), at most about 1.7k extra events per run |
| `EVENT_WAKE_DEDUPE_MAX` | 32 ids x 128 chars | at most 4 KiB carried in `MergeWatchResume` |
| `EVENT_WAKE_STALE_HEADS_MAX` | 8 heads | at most 512 B carried |

Extra history counts toward `MERGE_WATCH_HISTORY_FLOOR` (4096), so the existing hop predicate keeps every run bounded. More reads mean earlier hops, still capped by `MERGE_WATCH_MAX_HOPS`. Each ignored signal is still one `WorkflowExecutionSignaled` event, which the workflow cannot prevent. Debounce at the producer is a requirement on the future producer slice.

The carried fields are `event_wake`, `wake_seen`, `wake_superseded_heads` and `wake_pending`. The counters are diagnostics: they reset per run, and `event_wake_state` reports per-run values plus `hops`.

### 5. Query `event_wake_state`

A read-only `@workflow.query`. It returns enabled, accepted, the ignored-by-reason dict (keys sorted), woken reads, no-op reads, terminal-by-wake, and the last latency in seconds. It adds no history.

### 6. What does NOT change

- `_shepherd_tick`, `_merge_gate`, `_track_ownership`, `_decide_watch_end`, `_merge_watch_hop_suggested`, the `finally` block, the transient-error sleep (line 7017), the approval park and the stage 6.2+ observation.
- No review or merge gate is weakened, and there are no new activities or workflows.

## Alternatives

1. **Turn sleep into wait and run a full scheduled poll iteration on wake.** This is the smallest diff: it replaces only line 7195 with `wait_condition(wake, timeout=interval)` and loops. Rejected because every woken iteration increments `poll_index` and the heartbeat counter, and can schedule a shepherd tick or gate attempt. Events would then mint paid no-op shepherd runs, use up `SHEPHERD_TICKS_MAX`, and shorten grace (`pr_lookup_grace_polls`), terminal-status confirmation, refusal backoff and gate reprobe in wall-clock terms. The issue forbids exactly that.
2. **Event also brings forward the next shepherd tick (read plus paid scheduling).** For example, a review event could move the next tick earlier while charging the same budget. Rejected for S1: it couples a paid side effect to an untrusted hint, and it needs a separate debounce on the tick budget. This proposal keeps read scheduling (event-driven) separate from paid scheduling (cadence-only), so it can be added later as its own slice with its own marker.
3. **A separate signal-driven child workflow or watcher, or a new controller.** Rejected: it duplicates ownership, tick and gate exclusivity across two executions, and the issue explicitly says no new workflow and no second controller.
4. **Gating through an `IssueRef` input flag set by the starter instead of a code constant.** Deferred: it needs mctl-api changes, which are out of scope. The carried `MergeWatchResume.event_wake` field already gives the per-execution contract a later starter flag would feed.

## Platform impact

- **Migrations.** None. `MergeWatchResume` gains defaulted fields, and old records decode with the wake path off.
- **Backward compatibility and replay.**
  - With `EVENT_WAKE_ENABLED=False` (this slice's shipped state), new code emits exactly the old commands, so old histories replay and 1.117.0 can still replay new histories.
  - Adding a signal handler and a query is not a command.
  - Signals sent to a 1.117.0 worker, which has no handler, are buffered and dropped with a warning; no command is produced. No sender exists in this slice anyway.
- **Rollback constraint.**
  - Once a released worker runs with the constant True, histories carrying `merge-watch-event-wake-v1` plus `CancelTimer` cannot be replayed by any older worker (TMPRL1100, the same class as `deferred-resume-contract`).
  - Rollback is then roll-forward only: set the constant to False, which stops new adoption while existing watches keep the carried path. Otherwise, drain or abandon the affected watches before downgrading.
  - This is recorded for the canary slice. This slice does not flip the constant.
- **Resource impact.**
  - Off by default: zero.
  - When enabled later: at most 3 extra `get_pr_state` calls (2 GitHub reads each) per 15 min per watch, plus their history.
  - No model calls and no Argo submissions.
- **Risks and mitigations.**
  - An unbounded signal flood bloats history. The reaction is capped, the hop is by history length, and producer debounce is required in the producer slice.
  - Temporal timer-cancel semantics could differ on the pinned SDK. T13 measures this; if the assumption fails, return feasibility HOLD.
  - A woken terminal read could race a scheduled tick or gate in flight. This is identical to today's scheduled terminal read, and `finally` settles both.
  - 1.117.0 could differ from main in `_watch_pr`. Fixtures are recorded on main, and the implementer diffs against the tag first.
- **Estimated cost.** One implementer run for this slice (the diff is about 250 lines of workflow code and about 500 lines of tests, plus two new fixtures), and no runtime model cost.
- **Feasibility.** The signal fits the current replay contract, because the handler is not a command and the timer change sits behind a marker and a constant. If T13 shows that `wait_condition` with a timeout does not produce the same uninterrupted timer command shape as `workflow.sleep`, the implementer stops with a feasibility HOLD and a split instead of broadening the scope.
