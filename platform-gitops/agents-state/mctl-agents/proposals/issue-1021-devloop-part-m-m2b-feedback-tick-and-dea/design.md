# Design: issue-1021-devloop-part-m-m2b-feedback-tick-and-dea

## Current state

All paths are in the `mctlhq/mctl-agents` clone at `2ddcf96` (the merge of #1020).

### Merge watch: `orchestrator/temporal/workflows/dev_loop.py`

- `DevLoopWorkflow._watch_pr` (around line 6348) works as follows:
  - **Deadline.** It computes `deadline = workflow.now() + MERGE_WATCH_DEADLINE` (14 days) on a fresh start, or
    parses the carried `resume.deadline`. The deadline is never recomputed.
  - **Loop.** It loops on `while workflow.now() < deadline and not self._abandoned` (line 6522), with
    `await workflow.sleep(cadence.poll_interval)` at the bottom of each iteration.
  - **Reads.** A found MERGED/CLOSED read writes the lifecycle `terminal` op through `_ownership` / `_finish_claim`
    and returns `_WatchOutcome(last=state)` (around line 6665). A transient `ActivityError` sleeps and `continue`s.
- **Exits that end on a last observed state**, all three followed by the `finally` release:
  - the loop condition going false, with no read (the deadline gap);
  - `polls_without_pr >= cadence.pr_lookup_grace_polls`, `return _WatchOutcome(last=last)` (line 6824);
  - a non-transient read error, `return _WatchOutcome(last=last)` (line 6619).
- **Exits this slice leaves alone:** the MERGED/CLOSED return, the hop `break`, the #516 terminal-status `break`
  (`watch_ended="proposal ..."`), abandon (the loop condition, guarded), and the early `_WatchOutcome(last=None)`
  (line 6386, unreachable in production).
- **Finally block** (line 6831). It settles the tick and the gate, then, unless hopping and while a claim is held,
  writes `terminal` or `release` by `last.state`, and reports claim abandonment.
- **Claim liveness.** The heartbeat is an idempotent `acquire` every `heartbeat_every_polls` (every 8th poll, about 2 h,
  line 6051), which refreshes `last_seen_at`. `progress` is written only when the head moved, and its docstring forbids
  writing it with nothing new (line 5689). The liveness bound is 40 polls (about 10 h), after which the owner can be
  reaped.
- **Own merge attempts.** `_settle_gate` (line 5359) cancels an in-flight gate, but a consume already running still runs
  `gh pr merge`, and `_apply_gate_outcome` (line 5287) relies on the next poll to observe MERGED. `_settle_tick` (line
  5129) cancels the wait, and the Argo run it submitted finishes on its own. A read taken before these settle can
  therefore be overtaken by this loop's own merge.
- **Marker convention.** Markers are evaluated once in the fresh-start arm and carried through `MergeWatchResume`
  (around line 1600). `tests/test_patch_memoization.py` pins this.
- **Hop.** The hop is decided at the top of the loop and returns `_WatchOutcome(resume=...)`. `_resume_merge_watch`
  rehydrates instance state and calls `_watch_pr(resume=...)`, with no `workflow.patched` call of its own.
- **Tail.** `_finish_after_watch` (line 4611) runs deploy observation, `security-record-landed` and the incident watch
  only when `pr_state.merged`.
- **Result.** `DevLoopResult` (line 1163): `pr` (line 1177, documented as "OPEN means the watch deadline expired"),
  `ended` (line 1195), `outcome` (line 1198).

### Deliveries

`_deliver` (line 2858) binds, then waits, then lands `Succeeded if decided else Failed`, where `decided` is
`(_is_approved() or _gates_passed) and not _abandoned`. On a watch `_gates_passed` is True, so that wait passes at once
and the only deliveries actually open are one still polling its bind and one holding a `pending_phase`.
`_settle_deliveries(hopping=False)` sets `_exiting` and waits for every delivery task. An unbound delivery closes as
`request-not-fulfilled`. The validator defers a post-gates resume, so a delivery is rarely open during a watch, but one
can be carried across a hop. The loop's own canonical `we_` ends at the approve flip, before the watch.

### What `get_pr_state` can and cannot prove

`activities/pr_state.py` returns `found=False` for all of: a status file answering 404, no `pr:` line, an unusable
`pr:` line, a PR outside the repo, and a recorded PR answering 404. Its docstring notes that GitHub answers
unauthorized and missing lookups identically. So `found=False` is not proof of absence, and `proposal_status` alone
does not separate these cases. The implementer's branch is deterministic, `feat/agents-<slug>`
(`run_implementer.py:1942`), except when an adopted PR overrides it, and an adopted PR has a recorded link. The typed
`implementation_completion` outcome, such as `deliberate_no_op`, does not reach the workflow because `WorkflowResult`
carries no output parameters.

### Durable-write primitives examined

| Primitive | Why it is or is not the record |
|---|---|
| `lifecycle_ownership` `release` reason | The release itself, so it cannot precede the release. |
| `record_execution` | A best-effort audit write that swallows failure, with no confirmed read-back. |
| `advance_dispatched_execution` | Ends an execution; the loop's own `we_` has already ended by the watch. |
| `.status.yaml` in mctl-gitops | No workflow activity writes it, and the writer path is a governed CWFT. |
| `post_issue_comment` (`activities/issue_state.py:114`) | Durable and visible, already registered and tokened, but not idempotent, and it maps 4xx to a quiet False. |

The source issue is the one place an operator already looks for a DevLoop, and `self._issue_url` is set on every run
(line 3571). So the record is a comment there, written by a new idempotent activity. `post_issue_comment` is not
changed.

### Readers of the result

- `orchestrator/temporal/cli.py:117` prints `not watched` for a None `pr` once implement succeeded. That would be
  misleading here, so it changes.
- `dispatcher._reconcile_closed_loops` (line 577) only fails non-terminal executions of a closed loop.
- mctl-api `restartIfAbandoned` (`internal/api/handlers_dev_loop.go`, read at its default branch) decodes `ended` and
  `implement` only. It answers `already_exists` for a Completed run with a non-abandon `ended`, and for a Failed run.
- `orchestrator/temporal/start.py` sets the reuse policies. Intake uses `ALLOW_DUPLICATE_FAILED_ONLY` (line 33), and the
  dispatcher uses `ALLOW_DUPLICATE` (line 42), so a later claim may start a continuation after any closed run
  (`dev_loop.py:515`).

### Deployed state checked

`$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image tag `1.117.0`. This slice needs no
environment variable and no CWFT change. The mctl MCP tools were not needed for the design; nothing here depends on a
live service's runtime state.

## Proposed solution

### 1. Marker

`MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` is evaluated once in the fresh-start arm of
`_watch_pr`, beside `proposal_terminal_end`, into a local `terminal_reconcile`. A defaulted
`MergeWatchResume.terminal_reconcile: bool = False` carries it and the hop record fills it in. The resume arm reads
`resume.terminal_reconcile`. `_resume_merge_watch` gains no `workflow.patched` call. A pre-change record decodes as
False, so that watch keeps today's behaviour until it ends (migration by attrition, as for `deferred_resume_contract`).

### 2. One decision for all three exits

```python
async def _decide_watch_end(self, exit_name, watch, deadline) -> _WatchDecision:
    self._retain_claim = True                               # R10a: from here to a confirmed outcome
    settled_at = None
    unobserved = False
    if exit_name == "deadline":
        unobserved = await self._settle_watch_work(watch)   # R1a
        settled_at = workflow.now()
        if self._abandoned:
            return self._decided("abandoned")
    read = await self._final_pr_read(watch)                 # R2, wakes on abandon
    if read.abandoned:
        return self._decided("abandoned")
    if read.fresh is None and exit_name != "deadline":
        unobserved = await self._settle_watch_work(watch)   # R1a
        settled_at = workflow.now()
        if self._abandoned:
            return self._decided("abandoned")
    if read.fresh is not None and read.fresh.state == "OPEN" and exit_name == "deadline":
        unobserved = unobserved or read.fresh.head_sha == self._gate_ran_head
    if unobserved and (read.fresh is None or read.fresh.state == "OPEN"):
        if await self._wait_unless_abandoned(settled_at + GATED_ACTIVITY_TIMEOUT - workflow.now()):
            return self._decided("abandoned")
        read = await self._final_pr_read(watch)
        if read.abandoned:
            return self._decided("abandoned")
    fresh = read.fresh
    if fresh is not None and fresh.state in ("MERGED", "CLOSED"):
        await self._terminal_claim(fresh, watch)            # same write as the in-loop branch
        return self._decided("final", last=fresh)
    if fresh is not None and not (exit_name == "deadline" and unobserved):
        return self._decided("open", last=fresh)
    if fresh is None and exit_name == "grace-polls" and await self._no_pr_proven(read, watch):
        if self._abandoned:
            return self._decided("abandoned")               # R16 outranks a proven absence
        return self._decided("no-pr")                       # R5a
    if self._abandoned:
        return self._decided("abandoned")                   # last check before the decision point
    self._reconcile_required = True                         # R11: before the first record attempt
    record = await self._record_reconcile(exit_name, watch, deadline)  # R7-R10
    return self._decided("reconcile" if record else "unrecorded", record=record, last=fresh or watch.last)
```

`self._decided` builds the decision and clears `_retain_claim` for every kind except `unrecorded`. `watch` is a small
mutable per-run record that holds the settled tasks and the poll counters which are locals today (`last`,
`polls_without_pr`, `terminal_status_polls`, `saw_open_pr`, `tick_task`, `gate_task`, `track_ownership`, `poll_index`).
`poll_index` must be the real one, because `_settle_gate` feeds it to the gate-off latch. `read.abandoned` is True when
the flag is set after an attempt, checked after `_apply_found_state` has finished, and that attempt did not find a MERGED or CLOSED PR, so a found OPEN with an abandon is
abandoned, with `last` holding the fresh state.

`_apply_found_state(state, watch)` is the found branch's bookkeeping (lines 6628-6644) factored out: `last`,
`self._last_pr`, `polls_without_pr = 0`, `terminal_status_polls = 0`, `saw_open_pr` when not terminal, the heartbeat
index, and `_track_ownership(state)`. The in-loop found branch and `_final_pr_read` both call it, so a state first seen
by the final read takes a claim before `_terminal_claim` and cannot be finalized later through the #516 break as if no
PR had ever resolved. The in-loop commands do not change.

`_settle_watch_work(watch)` records whether the tick or the gate is still in flight, calls `cancel()` on those, and then,
only if at least one was in flight, `await workflow.wait([...])`, since an empty list raises `ValueError`. An outer workflow cancel raises from that wait, whereas awaiting a cancelled task inside
`_settle_tick` or `_settle_gate` catches `CancelledError` and would absorb it (lines 5149-5159, 5389-5399). Only then
does it call `_settle_tick` and `_settle_gate`, which take their `done()` branch and drain, so `MERGE_APPROVED` is still
logged. It sets both tasks to None so that `finally` finds nothing, and returns the flag. If a tick was in flight it sets
`watch.tick_blocked_until = workflow.now() + SDK_STEP_TIMEOUT`, because cancelling the wait does not stop the Argo run
(line 5135), and setting `tick_task` to None would otherwise clear the guard "Never two shepherds on one proposal"
(line 6694). The loop's tick boundary treats that time like a running tick: skipped, not queued, and no budget consumed.
`MergeWatchResume` carries it with an empty default. `_record_gate_result` also sets `self._gate_ran_head` when
`result.ran`, and `MergeWatchResume` carries that with an empty default too. `_gate_head` is rewritten when an attempt
starts, and a cancelled attempt sets no latch, so a new attempt on the same head stays allowed after a resume.

`_ownership` swallows cancellation in two branches (lines 5449-5473), which is right in `finally` and wrong while
deciding. Both branches gain `if self._retain_claim and <the failure is a cancellation>: raise`. `_retain_claim` is True
only under the marker and only while deciding, and `finally` issues no lifecycle write while it is True, so nothing on
an existing path changes.

The three sites use it as follows, all under `if terminal_reconcile:`, so that an unpatched history takes today's line:

| Site | `final` | `open` | `no-pr` | `reconcile` | `unrecorded` | `abandoned` |
|---|---|---|---|---|---|---|
| `while ... else:` (deadline), guarded by `not self._abandoned` | return, `watch_end="final-read"` | `last=fresh`, release in `finally`, `watch_end="final-read"` | not reachable | release in `finally`, typed end | no release, raise after `finally` | release, `abandoned-unverified` |
| grace-polls, guarded by `not self._abandoned` | same | `polls_without_pr=0`, `last=fresh`, fall through to the poll sleep | return `last=None`, `watch_end="no-pr-confirmed"` | same | same | same |
| non-transient read, guarded by `not self._abandoned` | same | `last=fresh`, sleep and `continue` | not reachable | same | same | same |

On a deadline exit an `open` decision is reached only when no attempt is unobserved. On the other two sites an `open`
decision resumes the loop even after a settle, because the loop keeps observing and may start a new attempt.

`_final_pr_read` and the window catch the same timeout exception as `_land_delivery`'s `wait_condition`.

`_no_pr_proven` returns False without any activity when `read.state` carries a number or URL, `watch.last` carries a
number, `watch.saw_open_pr` is true, or every attempt failed with an `ActivityError`. Otherwise it runs `confirm_no_pr`
and returns `result.confirmed`. An `ActivityError` is False, except a cancellation, which is re-raised.

**Abandon (R16).** Each site is guarded by `not self._abandoned`, and the guard's other arm sets
`watch_end="abandoned-unverified"`, a local assignment with no command, and takes today's line. `_final_pr_read` checks
the flag after each attempt, and its backoff and the R1a window use `_wait_unless_abandoned`, a `wait_condition` with a
timeout, so an abandon adds no delay. `finally` issues today's `release`. After the decision point `self._abandoned` is
not consulted again.

**Cancellation (R10a).** `_retain_claim` is True from the start of `_decide_watch_end`, so a `CancelledError` raised from
any sleep or wait leaves through `finally` with no relinquishing write, and `finally` logs
`MERGE_WATCH_RECONCILE_UNRECORDED`. Every new `except ActivityError`, and the `get_pr_state` handler of the loop's poll
under the marker, starts with `if is_cancelled_exception(exc): raise` (`temporalio.exceptions`), so a cancelled activity
is never a failed read. The settle and `_ownership` are covered above. Ordinary in-loop lifecycle writes and
`_merge_gate_identity` (line 5208) keep today's handling, as R10a states. `run`'s existing `except (Exception,
asyncio.CancelledError)` ends the deliveries.

In Python a `while ... else:` runs only when the condition goes false, never after `break` or `return`. So the hop and
the #516 break do not reach it. It sits inside the existing `try`, so before the relinquishing write in `finally`. A
continued run that starts past the deadline never enters the loop body, so the `else:` runs at once (R13). The hop
predicate is evaluated only inside the loop, so no hop can occur during the final read or the record.

- `_final_pr_read`: up to `FINAL_READ_ATTEMPTS = 3` calls of `get_pr_state`, each with `PR_STATE_TIMEOUT` and
  `PR_STATE_RETRY_POLICY`, with `FINAL_READ_BACKOFF = 2 min` between them. It applies `_apply_found_state` to, and
  returns, the first found state, and keeps the last `found=False` state for `_no_pr_proven`. Any `ActivityError` other
  than a cancellation, transient or not, and any `found=False` counts as a failed attempt. A set is about 34 minutes at
  worst, up to two sets with the R1a window between them are about 80 minutes at worst, and neither is added to the
  deadline. A "failed attempt" is one workflow-level `execute_activity`, and each may run up to 5 activity executions
  under the policy.
- `_terminal_claim(state, track_ownership)`: the in-loop MERGED/CLOSED ownership block, factored out so that both
  sites issue the identical `terminal` write (a pure refactor, with the same commands on existing histories).

### 3. Proof of absence

New in `orchestrator/temporal/activities/pr_state.py`, registered in `worker.py` `short_activities`:

```python
@dataclass(frozen=True)
class NoPrProof:
    confirmed: bool
    reason: str   # "no-link-no-pull" or the first thing that blocked the proof
```

`confirm_no_pr(service, slug)` raises `ProposalListingError` when no token exists, and on a transport error, an
unexpected status, or a malformed body, so a failure is never read as absence. It returns `confirmed=False` for a 404 on
the status file, and for a `pr:` line of any shape. It then lists
`GET /repos/mctlhq/<service>/pulls?head=mctlhq:feat/agents-<slug>&state=all&per_page=100`, following every page. A
non-200 or non-list page raises, and a later page failing is a failed read, not a shorter list. Any item returns
`confirmed=False`. It then reads `GET /repos/mctlhq/<service>/branches/feat/agents-<slug>`, after the listing has proved
repository access: 200 returns `confirmed=False`, because a pushed branch with no PR is undecided
(`run_implementer.py:3787`), 404 continues, and anything else raises. `200 []` on every page and a 404 on the branch,
with the no-link status file, return `confirmed=True`. The bad-filter case, where GitHub ignores a malformed `head` and
returns unrelated PRs, fails closed through "any item".

The status file check is stricter than `get_pr_state`'s `_PR_FIELD_RE`, which accepts only a usable value and decodes
with `"replace"`. It requires `encoding == "base64"`, non-empty content, a strict decode and a parsed `status:` line. Any
line matching `^\s*["']?pr["']?\s*:` blocks the proof, whatever its value.

### 4. The record

New in `orchestrator/temporal/activities/issue_state.py`, registered in `worker.py` `short_activities`:

```python
@dataclass(frozen=True)
class ReconcileRecordInput:
    repo: str; issue_number: int; workflow_id: str; deadline: str
    exit_name: str; last_observed: str; open_request_ids: tuple[str, ...]

@dataclass(frozen=True)
class ReconcileRecordResult:
    status: str   # "recorded" | "already-recorded" | "issue-gone"
    url: str = ""
```

`record_merge_watch_reconcile`:

1. Builds the marker `<!-- merge-watch-reconcile-required workflow=<id> deadline=<iso> -->`. The absolute deadline makes
   it unique per watch, including a later run on the same issue-keyed workflow id, and stable across hops and retries.
2. Lists every comment page. A non-200 page, a transport error or a malformed body raises `IssueStateError`: it is a
   failed read, so nothing is posted (R8). A 410 on the issue returns `issue-gone`. A 404 raises and is retried, because
   GitHub answers unauthorized and missing lookups identically.
3. Returns `already-recorded` with that comment's URL if the marker is on a comment where `user.login` is the writer
   login `mctl-agents[bot]` (`user.type == "Bot"`, whose `author_association` is `CONTRIBUTOR` in practice) or
   `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR`. Others, including other bots, are ignored, so a third
   party cannot suppress the record by pasting the marker text. A writer under another login posts again, which is a
   visible duplicate and never a suppressed record.
4. Otherwise posts the fixed template. A 201 with a URL returns `recorded`. A 201 with no URL, a missing token, 401, 403,
   404, 429, 5xx or any other answer raises, so the workflow retries. A post that succeeded but timed out is caught by
   step 3 on retry. A 301 for a transferred issue is not followed, so it raises for the whole wait and ends in the Failed
   run of R10. That is a stated, visible limit.

The template names the workflow id, the exit, the last observed PR (state, URL, head SHA, or "none"), the open request
ids, and what to do: read the PR by hand, then re-trigger or close deliberately. It carries no other data.

`_record_reconcile` in the workflow:

```python
started = workflow.now()
await self._reconcile_heartbeat(watch)
last_refresh = workflow.now()
interval = RECONCILE_RECORD_RETRY_MIN                 # 5 minutes
while True:
    try:
        result = await workflow.execute_activity(record_merge_watch_reconcile, inp,
            start_to_close_timeout=PR_STATE_TIMEOUT, retry_policy=RetryPolicy(maximum_attempts=3))
        return result.url if result.status in ("recorded", "already-recorded") else ""  # issue-gone: R10
    except ActivityError as exc:
        if is_cancelled_exception(exc):
            raise                                     # R10a
    if workflow.now() - started >= RECONCILE_RECORD_WAIT:
        return ""                                     # R10
    if workflow.now() - last_refresh >= RECONCILE_LIVENESS_INTERVAL:  # 90 minutes, before the sleep
        await self._reconcile_heartbeat(watch)
        last_refresh = workflow.now()
    remaining = started + RECONCILE_RECORD_WAIT - workflow.now()      # after the heartbeat
    if remaining <= timedelta(0):
        return ""                                     # a negative sleep is a RuntimeError, which wedges the run
    await workflow.sleep(min(interval, remaining))
    interval = min(interval * 2, RECONCILE_RECORD_RETRY_MAX)  # 5, 10, 20, 30, 30, ...
```

`_reconcile_heartbeat(watch)` returns at once unless `watch.track_ownership and self._owned_entity_id`, so an unclaimed
run writes nothing and never derives a `#0` entity. It parses repo and number from `_owned_entity_id`, as `finally` does,
and calls `self._ownership("acquire", repo=repo, number=number, head_sha=<last head>)`. If the caller owns the row it
updates the epoch. On `OWNED_BY_OTHER` with `_lost_to_someone_else` it calls `_lose_claim`, which empties
`_owned_entity_id`, and the record retries continue. Any other answer is logged, and `_give_up_claim_if_unanswered` is
not called, so an outage of the lifecycle store does not drop the claim during this wait.

An unparsable `self._issue_url` returns `""` at once, as a defensive branch: `_target_repo` raises earlier on a real run
(lines 1318 and 4522), so it is pinned by a method-level unit test. `self._abandoned` is deliberately not in this loop
(R9). The wait is about 50 iterations over 24 hours, about 550 history events including the heartbeats. The check runs
before every sleep of at most 30 minutes, so refreshes land at most about 2 hours apart, and the liveness bound is about
10 hours.

**Fail closed (R10).** On `""` the decision is `unrecorded` and `_retain_claim` stays True. The `finally` then skips the
relinquishing write,
logs `MERGE_WATCH_RECONCILE_UNRECORDED`, and after `finally` the watch raises
`ApplicationError(type="MergeWatchReconcileUnrecorded", non_retryable=True)`. `run`'s existing `except` ends the
deliveries. The held claim lasts until the store reaps it at the liveness bound, about 10 h after the workflow closes,
which is the existing behaviour for a dead owner. From then on the trace is the Failed run and the log line, and
mctl-api answers `already_exists` for it. A Failed run is the signal, because a Completed one would claim a record that
does not exist.

### 5. Typed result

- `watch_end` takes the values `final-read`, `reconcile-required`, `no-pr-confirmed`, `abandoned-unverified`, or `""`
  on the paths this slice leaves alone.
- `_WatchOutcome` gains `watch_end: str = ""` and `reconcile_record: str = ""`.
- `DevLoopResult` gains defaulted `watch_end: str = ""`, `last_observed_pr: PRState | None = None` and
  `reconcile_record: str = ""`. Old payloads decode with the defaults, and results are not compared on replay.
- On `reconcile-required`, `_finish_after_watch` sets:
  - `pr=None`, `last_observed_pr=last`, `reconcile_record=<url>`;
  - `outcome="merge_watch_reconcile_required"`;
  - `ended="merge watch <exit>: pull-request state not established; reconciliation required"`, ahead of the abandon
    prefix;
  - it skips deploy, security and incidents because `pr_state` is None, and logs `MERGE_WATCH_RECONCILE_REQUIRED`.
- `_reconcile_required` is set at the decision point, before the first record attempt, on both end states (R11). The
  check sits in `_deliver` after the bind and before the existing wait: an undecided delivery then calls
  `_land_delivery(opened, "Failed", MERGE_WATCH_RECONCILE_REFUSAL, engine_ref)`. The same check runs again after the
  wait, immediately before the existing landing, because `wait_condition` suspends the delivery task even when its
  predicate is already true, and the flag can be set in that activation. A delivery with a `pending_phase` keeps it. The flag is set only under the marker, so no earlier history changes shape. The constant lives beside the delivery
  landing code, not in `RESUME_DEFERRAL_REASONS`, which is a validator vocabulary.
- The `finally` release reason is `merge watch <exit>: pull-request state not established, reconciliation recorded`.
- The `DevLoopResult.pr` and `_watch_pr` docstrings are corrected. The `pr` docstring states that on
  `abandoned-unverified` it is the last observed state and not verified current state.
- `cli.py` prints `pr: reconcile required (<record>)` before the `not watched` branch, `pr: none (confirmed)` on
  `no-pr-confirmed`, and adds `(last observed before abandon, not verified current)` on `abandoned-unverified`.

### 6. Redelivery and replay

- `get_pr_state` and `confirm_no_pr` are read-only, and on replay the recorded result is returned.
- The record activity is idempotent through its marker, and on replay its recorded result is returned.
- The `terminal` write goes through the existing idempotent `_ownership` path. At most one relinquishing write lands per
  watch end, in `_terminal_claim` or in `finally`. A failed `terminal` write leaves the claim behind and `finally` retries
  it, as `_finish_claim` does today (line 5574), and the store treats the retry as idempotent.
- Deploy observation and the security record run once in workflow code after the watch.

## Alternatives

1. **Extend or recompute the deadline after a gap.** Rejected: the owner forbids it, a hop would compound it, and it
   still ends on a stale state if the read in that window fails.
2. **Do the final read in `_finish_after_watch` or `_resume_merge_watch`.** Rejected: `finally` would already have
   released the claim, a merged PR would get `release` instead of `terminal`, and the patch would have to be evaluated
   in `_resume_merge_watch`.
3. **End reconcile-required as Failed in every case.** Rejected by the owner's decision: Completed with a typed outcome
   when the record exists. Failed is kept for the case where the record does not exist.
4. **Use the `release` reason as the record.** Rejected: the owner requires the record before the release, and a
   release that lands with a lost reason would leave nothing.
5. **Use `record_execution` as the record.** Rejected: it is best effort by contract, and its success is not read back.
6. **A new mctl-api endpoint or store column.** Rejected for this slice: it widens the slice across repositories for a
   record whose first reader is a human.
7. **Keep the claim instead of releasing after the record.** Rejected: nothing would release it except the reaper, the
   work could not be picked up in the meantime, and the owner accepted release after the record.
8. **Prove absence from `found=False`, `proposal_status`, or the grace-poll count.** Rejected: all three are consistent
   with lost token access, and repetition of an unknown answer is not proof.
9. **Prove absence from the implementer's typed `deliberate_no_op`.** Rejected for this slice: `WorkflowResult` carries
   no output parameters, and adding one needs a CWFT output, which is a live change.
10. **Have the dispatcher defer or refuse while the last run is unreconciled.** Not in this text: it needs cross-run state
    that the dispatcher does not have today. A restart re-reads live state and the record stays on the issue, so it is
    documented in R15 and pinned by T-23. It is the open question in `requirements.md`.
11. **Treat an in-flight tick or gate as harmless because a read is only a moment anyway.** Rejected: a human merging
    after a read is outside this loop's knowledge, but this loop knows that it has an attempt running.

## Platform impact

- **Replay compatibility.** The marker is evaluated only in the fresh-start arm of `_watch_pr` and carried with a False
  default, so every pre-change history (`dev_loop_full.*`, `dev_loop_resumed.json`, `dev_loop_deferred_resume.json`,
  `pre_m1/`) schedules exactly the same commands. New fixtures are recorded post-change. The `*.prepatch` fixtures are
  not re-recorded.
- **New state.** `MergeWatchResume.terminal_reconcile`, `gate_ran_head` and `tick_blocked_until`; `DevLoopResult.watch_end`,
  `last_observed_pr`, `reconcile_record`. All are defaulted, and old payloads decode. The feedback fields from M2a are
  untouched.
- **Resource impact.** A deadline-ending watch makes 1-3 extra `get_pr_state` calls and up to 2 extra timers, doubled
  with one window timer added when an attempt is unobserved. A grace-polls exit adds one `confirm_no_pr`, at least 3
  GitHub reads. A reconcile-required watch adds a few GitHub reads and one comment. The workflow can stay open up to 24
  hours longer in the worst case.
- **GitHub.** New writes are comments on source issues, using the worker's existing token. A public source issue gets a
  public comment, so the template holds only what the issue and PR already expose.
- **Behaviour change on grace polls.** A loop with proven absence ends as it does today, with a typed `watch_end`. A
  loop whose absence cannot be proven now ends reconcile-required with a comment on its source issue.
- **Production.** Nothing is deployed by this proposal. The release hold stays ON, #1003 stays Draft, B4 stays FAIL,
  and no environment variable is added to `mctl-agents-worker`.
- **Risks and mitigations.**
  - *Readers of `DevLoopResult.pr` may treat None as "no PR".* Mitigation: the typed fields, the CLI change, and the
    reader sweep in R15.
  - *Record and read share GitHub as a failure domain.* Mitigation: the patient retry and the claim held meanwhile.
  - *A state nobody notices.* This slice has no detector. Mitigation: the separate gate #1022 blocks any release that
    carries this slice (R17), so these states cannot reach production on logs alone.
  - *A false proof of absence.* A PR opened by hand from another branch and never linked is outside the proof.
    Mitigation: it is stated in R5a. Any link or any PR on the loop's branch fails closed.
  - *Mid-flight rollback after release.* See Rollback in `tasks.md`.
- **Merge governance.** Any PR stays blocked for owner approval by the temporary code-owner rule (#1020). It needs
  independent review, green checks and an explicit owner merge decision, and no admin bypass. The supervising session
  verifies on the first implementer PR that GitHub actually blocks the merge, and stops if it does not.
