# Design: issue-1021-devloop-part-m-m2b-feedback-tick-and-dea

## Current state

All paths are in the `mctlhq/mctl-agents` clone at `2ddcf96` (the merge of #1020).

### Merge watch: `orchestrator/temporal/workflows/dev_loop.py`

- `DevLoopWorkflow._watch_pr` (around line 6348) works as follows:
  - **Deadline.** It computes `deadline = workflow.now() + MERGE_WATCH_DEADLINE` (14 days) on a fresh start, or
    parses the carried `resume.deadline`. The deadline is never recomputed.
  - **Loop.** It loops on `while workflow.now() < deadline and not self._abandoned`, with
    `await workflow.sleep(cadence.poll_interval)` at the bottom of each iteration.
  - **Reads.** A found MERGED/CLOSED read writes the lifecycle `terminal` op through `_ownership` /
    `_finish_claim` and returns `_WatchOutcome(last=state)`. A transient `ActivityError` sleeps and `continue`s. A
    non-transient one returns the last observed state.
  - **Gap.** If the worker is down across the deadline, the final sleep's timer fires past the deadline, the
    condition is false, and the loop exits with NO read.
  - **Finally block.** It runs `_settle_tick`, `_settle_gate`, and then, because `last.state` is still OPEN, the
    `release` write. That is the bug described in the issue.
- **Marker convention.** Markers are evaluated once in the fresh-start arm and carried through `MergeWatchResume`
  (around line 1600): `fast_cadence`, `shepherd_in_loop`, `concurrent_ticks`, `track_ownership`,
  `proposal_terminal_end`, `deferred_resume_contract`. `hop_enabled` and `gate_enabled` are the exceptions: they are
  re-evaluated per run. `tests/test_patch_memoization.py` pins this.
- **Hop.** The hop is decided at the top of the loop (`_merge_watch_hop_suggested`) and returns
  `_WatchOutcome(resume=...)`. The caller (`_run_loop` around line 4366, `_resume_merge_watch` around line 4504)
  calls `workflow.continue_as_new`. `_resume_merge_watch` rehydrates instance state and calls
  `_watch_pr(resume=...)`. It contains no `workflow.patched` call of its own.
- **Tail.** `_finish_after_watch` (around line 4611) runs deploy observation, `security-record-landed` and the
  incident watch only when `pr_state.merged`.
- **Docs.** `DevLoopResult.pr` (around line 1170) documents "OPEN means the watch deadline expired with the PR still
  open".

### Deliveries and feedback state (M1 / M2a, #996, #998, #1006, #1013, #1017)

- `accept_execution_request` and the `_validate_execution_request` validator (around line 2786) behave as follows
  after gates pass:
  - `work_merged` is refused;
  - `legacy-loop`, `implement-running` and `recovery-not-ready` are deferred;
  - `no_actionable_intent` is refused;
  - every remaining post-gates contract resume ends in the unconditional `ResumeDeferred("feedback-not-ready")`.
- An id already in `_accepted_request_ids` returns early before these checks.
- `OpenDelivery.accepted_after_gates` (around line 1098) is set by the handler. Because the validator always refuses
  first, it is unreachable in production. `_deliver` (around line 2858) lands such a delivery as
  `Failed feedback-not-ready`.
- `_feedback_done` and `_pending_feedback` already exist (around line 1959). They are carried in `MergeWatchResume`
  (`feedback_done`, `pending_feedback`) and exposed through the `contract_state` query, but nothing writes to them
  yet. `tests/test_deferred_resume_m2a.py` covers the carry.
- `tests/test_deferred_resume_m1.py:105` already round-trips a `MergeWatchResume` carrying
  `OpenDelivery(accepted_after_gates=True)`.
- `_shepherd_tick(service, slug)` (around line 5070) submits the `mctl-agents-shepherd` CWFT through `_run_cwft` and
  swallows failures.
- `WorkflowResult` (`orchestrator/temporal/activities/argo.py:77`) has no output parameters. The activity builds it
  from `status` only (around line 420).
- The grant digest `_approval_digest` and `_approval_ref` are set during the approval park (around lines 2288-2317)
  and checked by `check_grant_freshness` in `_supersede_grant_if_stale` (around line 2321). They are NOT in
  `MergeWatchResume`, so a continued run does not have them.
- The switch truthy set is `dispatcher._TRUTHY = {"1", "true", "yes", "on"}`
  (`orchestrator/temporal/dispatcher.py:173`). `orchestrator/temporal/worker.py:680` defines `short_activities`.

### Shepherd

- `orchestrator/run_shepherd.py` `main()` (around line 5117) has `--service`, `--slug`, `--dry-run`, `--reconcile`,
  `--fix-only` and `--adopt-prs`. There is no feedback mode.
- The review-feedback subprocess is built around lines 3234-3350 (`--review-feedback <bundle>`).
- Intents are read with `orchestrator/work_context/client.py` `WorkItemClient.list_intents` (line 328).

### Tests and fixtures

- Time-skipping environment: `tests/test_dev_loop_workflow.py:228`, harness `tests/temporal_harness.py`.
- Replay scenarios: `tests/replay_scenarios.py`, `tests/test_workflow_replay.py`, `tests/fixtures/histories/`
  (`dev_loop_full.patched.json`, `dev_loop_resumed.json`, `dev_loop_deferred_resume.json`, `pre_m1/`, ...).
- `tests/replay_scenarios.py` forbids re-recording `*.prepatch` fixtures after a change.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image tag `1.117.0`. No `DEVLOOP_*`
  environment variable is set, so `DEVLOOP_DEFERRED_FEEDBACK` is absent, which the switch reads as off.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`: declares `service`, `slug`,
  `dry_run`, `agent_image`, `agent_version`, `work_item_id`, `execution_id`, `temporal_workflow_id`,
  `temporal_run_id` and `execution_request_id`. It does NOT declare `intent_id` or `feedback_actor`, and has no
  `feedback_outcome` output. Task 8 is therefore not live, and a tick would read `feedback-unobservable`.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-993-feat-devloop-deferred-resume-after-imple/`: the
  umbrella design (M4, M5) and tasks 5-8 were read as the source of this slice. They are not modified.
- The mctl MCP tools were not called. Nothing in this slice depends on a live service's runtime state beyond the two
  gitops files above.

## Proposed solution

### A. Deadline-in-gap (first, mandatory gate)

1. **New marker.** `MERGE_WATCH_FINAL_READ_PATCH = "merge-watch-final-read"` is evaluated once in the fresh-start
   arm of `_watch_pr`, beside `proposal_terminal_end`, and stored as a local `final_read`. A new defaulted field,
   `MergeWatchResume.final_read: bool = False`, carries it, and the hop record built in `_watch_pr` fills it in. The
   resume arm reads `resume.final_read`. `_resume_merge_watch` gains no `workflow.patched` call. A pre-change resume
   record decodes as False, so that loop keeps today's behaviour until it ends (migration by attrition, the same
   rule as `deferred_resume_contract`).

2. **Final read on deadline exit.** The `while` loop gets an `else:` clause. In Python it runs only when the
   condition goes false, never after `break` (hop, #516 terminal break) or `return`. The clause runs inside the
   existing `try`, so before the `finally` relinquishing write:

   ```python
   else:
       if final_read and not self._abandoned:
           fresh = await self._final_pr_read(service, slug)
           if fresh is None:
               reconcile_required = True          # D4
           else:
               last = fresh; self._last_pr = fresh
               if fresh.state in ("MERGED", "CLOSED"):
                   await self._terminal_claim(fresh, track_ownership)   # shared with the in-loop branch
                   final_outcome = _WatchOutcome(last=fresh, watch_end="final-read")
               else:
                   watch_end = "final-read"       # OPEN: release in finally, as today
   ```

   - `_final_pr_read` makes up to `FINAL_READ_ATTEMPTS = 3` calls of `get_pr_state`, each with `PR_STATE_TIMEOUT` and
     `PR_STATE_RETRY_POLICY`, with `workflow.sleep(FINAL_READ_BACKOFF = 2 min)` between them. It returns the first
     found state.
   - Any `ActivityError`, transient or not, and any `found=False` counts as a failed attempt. A failed read is never
     OPEN.
   - The bound runs after the deadline and is never added to it (D6). The worst case is about 34 minutes.
   - The in-loop MERGED/CLOSED ownership block is factored into `_terminal_claim(state, track_ownership)`. Both
     sites then issue the identical `terminal` write.
   - The `finally` block is unchanged, except that it does nothing when `_terminal_claim` already finished the
     claim (the same `_owned_entity_id` guard as today). On `reconcile_required` it writes `release` with the reason
     `merge watch deadline: pull-request state unreadable, reconciliation required`. The claim is therefore never
     relinquished before the final read decides (D9).

3. **Typed result.**
   - `_WatchOutcome` gains `watch_end: str = ""` (`"final-read"` or `"reconcile-required"`).
   - `DevLoopResult` gains defaulted `watch_end: str = ""` and `last_observed_pr: PRState | None = None`.
   - On `reconcile-required`, `_finish_after_watch` sets:
     - `pr=None` and `last_observed_pr=last`;
     - `outcome="merge_watch_reconcile_required"`;
     - `ended="merge watch deadline: pull-request state unreadable; reconciliation required"`.

     It skips deploy, security and incidents, because `pr_state` is None, and logs `MERGE_WATCH_RECONCILE_REQUIRED`
     with the repo, the slug and the last observed state.
   - Results are not compared on replay, so the new fields are additive. Old payloads decode with the defaults.

4. **Continue-as-new.** `deadline` is already carried as an absolute ISO string. Only `final_read` is new. A
   continued run that starts after the deadline has passed never enters the loop body, so the `else:` runs at once
   and does the final read (D7). The hop predicate is only evaluated while `now < deadline`, so no hop can happen
   after the deadline, and none during the final read.

5. **Redelivery and replay.**
   - `get_pr_state` is read-only.
   - On replay the recorded result is returned.
   - The `terminal` write goes through the existing idempotent `_ownership` path, and exactly one relinquishing
     write is issued per watch end, either in `_terminal_claim` or in `finally`, never both.
   - Deploy observation and the security record run once in workflow code after the watch. They are deterministic on
     replay.

### B. `read_rollout_switches` (task 5, T5)

- New module `orchestrator/temporal/activities/rollout_switches.py` with
  `@activity.defn read_rollout_switches() -> RolloutSwitches` and the frozen dataclass
  `RolloutSwitches(deferred_feedback: bool = False)`.
- The activity reads `DEVLOOP_DEFERRED_FEEDBACK` in the activity, outside the sandbox. It is true only when
  `.strip().lower()` is in the truthy set; that set is imported from `dispatcher._TRUTHY`, or moved to a shared
  constant, so it is not duplicated. An unknown value is off, with a warning.
- The activity never raises. The workflow also maps an `ActivityError` to off.
- It is registered in `worker.py` `short_activities` and in the test activity registry fake.
- `implement_hold` is NOT added (that is Part S).

### C. Feedback tick (task 6; T6, T7, T8)

1. **Marker.** `DEFERRED_FEEDBACK_PATCH = "deferred-feedback-tick"` is evaluated once in the fresh-start arm of
   `_watch_pr` into `self._feedback_tick` and carried as `MergeWatchResume.feedback_tick: bool = False`. It is
   restored in `_resume_merge_watch` from the record, never by `workflow.patched`. When it is unset, `_deliver`
   keeps today's `Failed feedback-not-ready` landing byte-for-byte, so `dev_loop_deferred_resume.json` and every M1
   or M2a fixture replay unchanged.

2. **Authority record.** At the approve flip, the loop copies `_approval_ref`, `_approval_digest` and `_approver`
   into `self._flip_authority = FlipAuthority(approval_ref, content_digest, approver)`. That is a plain assignment,
   with no command. It is carried as `MergeWatchResume.flip_authority: FlipAuthority | None = None`.
   `_feedback_authority_valid()` works as follows:
   - `None` or any empty field returns False.
   - Otherwise it calls `check_grant_freshness(GrantFreshnessInput(service, slug, bound_digest=content_digest))`.
     `fresh` returns True. Not fresh or an `ActivityError` returns False.

3. **`_deliver` branch.** This replaces the `accepted_after_gates` arm when `self._feedback_tick` is set:

   ```
   rid in _pending_feedback                      -> wait (decided)
   rid in _feedback_done                         -> land Failed feedback-unobservable
   switches = read_rollout_switches (ActivityError -> off); not on -> land Failed feedback-disabled
   not _feedback_authority_valid()               -> land Failed reapproval-required
   _pending_feedback += (rid,)
   await wait_condition(rid in self._feedback_outcomes or self._hopping or self._exiting)
   hopping -> return (carried; the next run re-enters at "rid in _pending_feedback")
   land per F3/F4 using self._feedback_outcomes.pop(rid, "feedback-not-run")
   ```

   `_feedback_outcomes: dict[str, str]` is run-local. A landing that has been decided but has not landed is carried
   through the existing `OpenDelivery.pending_phase` / `pending_refusal` mechanism.

4. **Pickup in `_watch_pr`.**
   - After a found OPEN read, and after the cadence-tick block: if `_pending_feedback` is non-empty, the feedback
     tick task (`feedback_task`) is None, and the cadence `tick_task` is None or done, the watch:
     1. pops the first rid;
     2. adds it to `_feedback_done` before the task is created (so before the tick is awaited);
     3. starts `feedback_task = create_task(self._feedback_tick_run(service, slug, rid))`.
   - `shepherd_ticks` is not incremented.
   - A cadence boundary that lands on an in-flight `feedback_task` is skipped, exactly as for an in-flight
     `tick_task`.
   - `_merge_watch_hop_suggested` gains `feedback_task` and refuses while it is in flight.
   - `finally` settles `feedback_task`:
     - done: its outcome is recorded;
     - in flight: it is cancelled and recorded as `feedback-unobservable`.
   - Every rid still in `_pending_feedback` and not started is recorded as `merged-before-feedback` when
     `last.merged`, and as `feedback-not-run` otherwise.
   - On a hop, `_pending_feedback` and `_feedback_done` are carried untouched.

5. **The tick.** `_shepherd_tick` gains an optional `feedback: FeedbackRequest | None` and returns `str | None`.
   - With feedback, it adds `intent_id`, `execution_request_id` and `feedback_actor` to the tick parameters, and
     returns `tick_result.feedback_outcome`.
   - An `ActivityError` returns the sentinel `"activity-failed"`.
   - The old call shape is unchanged for cadence ticks, with the same commands and the same swallow behaviour.
   - `WorkflowResult` gains `feedback_outcome: str | None = None`, parsed in `argo.py` from
     `status.outputs.parameters[name == "feedback_outcome"].value` when present. While task 8 is not live it is
     always None.
   - The mapping to landings is: `processed` -> Succeeded; `scope-expansion` -> scope-expansion;
     `failed` / `activity-failed` -> feedback-failed; anything else -> feedback-unobservable.
   - The new refusal reasons are added to the vocabulary near `dev_loop.py:506`: `feedback-disabled`,
     `reapproval-required`, `scope-expansion`, `feedback-failed`, `feedback-unobservable`, `merged-before-feedback`
     and `feedback-not-run`.

6. **How T6-T8 reach the tick without the accept path.** The validator is NOT changed: the trailing
   `feedback-not-ready` deferral stays, and F7 is pinned by keeping
   `tests/test_execution_request_resume.py:586` green.
   - **Entry point.** Tests start a real `DevLoopWorkflow` in the time-skipping environment with
     `IssueRef(resume=MergeWatchResume(..., deferred_resume_contract=True, feedback_tick=True, flip_authority=...,
     open_deliveries=(OpenDelivery(delivery=<intent 7>, accepted_after_gates=True),),
     accepted_request_ids=(rid,)))`. This is the continue-as-new entry point. `_resume_merge_watch` ->
     `_start_delivery` -> the real `_deliver` -> the real `_watch_pr` pickup -> the real `_shepherd_tick` against
     faked activities.
   - **Redelivery.** A second `accept_execution_request` Update for the same rid is sent on the live run. The
     validator returns early for an accepted id, so this is a real Update, and the tests assert that no second tick
     follows.
   - **STOPPED.** The leg in which a NEW request is accepted onto a gates-passed loop by the dispatcher through
     `accept_execution_request` cannot be proven without task 4. It is recorded as STOPPED and left to M2c. Nothing
     in this slice enables it.

### D. `run_shepherd --feedback-intent` (task 7)

- New flags `--feedback-intent INT`, `--execution-request-id`, `--feedback-actor` and `--work-item-id`. When the
  environment already provides `work_item_id` (the CWFT passes it today), the flag defaults from it.
- New function `process_feedback(service, slug, intent_id, ...) -> str`:
  1. Fetch the intent: page `WorkItemClient.list_intents(wid, after_id=...)` until the id is found. Not found,
     `text_redacted` or a client error returns `unobservable`.
  2. Classify it with a read-only model call against the approved proposal's `requirements.md` and `design.md`, using
     the read-only options pattern in `orchestrator/options.py` around line 1701. Only an exact `in-scope` proceeds.
     Anything else is `scope-expansion`.
  3. For `in-scope`, build the review-feedback bundle from the intent text and run the existing implementer
     `--review-feedback` path. It uses the same lifecycle claim and `--match-head-commit` fencing, and is accepted
     only on a pushed commit with green gates (`processed`). Otherwise the outcome is `failed`.
- `main()` wraps the call in `try/except Exception -> "failed"`. It writes the outcome to `$FEEDBACK_OUTCOME_PATH`
  (default `/tmp/feedback_outcome`), prints `FEEDBACK_OUTCOME=<value>`, and exits 0 for every typed outcome. The
  outcome is the channel, not the exit code.
- `--feedback-intent` is incompatible with `--reconcile`, `--fix-only` and `--adopt-prs`. That combination exits 2.

## Alternatives

1. **Extend or recompute the deadline after a gap** (for example, give the watch one more `poll_interval` when it
   wakes late). Rejected: the issue forbids it, a hop would compound it, and it still ends on a stale state if the
   read in that window fails.
2. **Do the final read in `_finish_after_watch` or `_resume_merge_watch`.** Rejected:
   - the `finally` block would already have released the claim, breaking D9;
   - a merged PR would get `release` instead of `terminal`;
   - the patch would have to be evaluated in `_resume_merge_watch`, which the issue forbids.
3. **Reach the tick in tests by relaxing the validator behind a test flag.** Rejected: that is the accept path that
   task 4 owns, and the issue forbids enabling it. The carried-`OpenDelivery` entry uses only production code.
4. **Reuse `DEFERRED_RESUME_PATCH` for the tick and the final read.** Rejected: the issue requires the final read to
   have its own marker. A shared marker would also change the shape of histories already recorded under M1.

## Platform impact

- **Replay compatibility.**
  - Both new markers are evaluated only in the fresh-start arm of `_watch_pr` and carried with False defaults, so
    every pre-change history (`dev_loop_full.*`, `dev_loop_resumed.json`, `dev_loop_deferred_resume.json`,
    `pre_m1/`) schedules exactly the same commands.
  - New fixtures are recorded post-change (final read without a hop, final read across a hop, a feedback tick). The
    `*.prepatch` fixtures are not re-recorded.
- **New state.** `MergeWatchResume` gains `final_read`, `feedback_tick` and `flip_authority`. `DevLoopResult` gains
  `watch_end` and `last_observed_pr`. `WorkflowResult` gains `feedback_outcome`. All are defaulted, and old payloads
  decode.
- **Resource impact.** A deadline-ending watch makes 1-3 extra `get_pr_state` calls and up to 2 extra timers. The
  feedback tick is unreachable in production (validator deferral plus switch OFF), so there is no added cost.
- **Production.** Nothing is deployed by this proposal. The release hold stays ON, #1003 stays Draft, and no
  environment variable is added to `mctl-agents-worker`.
- **Risks and mitigations.**
  - *Readers of `DevLoopResult.pr` may treat None as "no PR".* Mitigation: the new `outcome` and `watch_end` fields,
    the log line, and an open question.
  - *Final-read bound under a long GitHub outage.* Mitigation: the read is bounded and ends `reconcile-required`,
    never OPEN.
  - *Parameters the CWFT does not declare.* Mitigation: unreachable until task 8 and M2c.
  - *Mid-flight rollback after release.* Histories with the new markers would need the branch kept. Mitigation:
    roll back only by deprecating the patch, never by deleting it (see Rollback in tasks.md).
- **Merge governance.** Any PR stays blocked for owner approval by the temporary code-owner rule (#1020). It needs
  independent review, green checks and an explicit owner merge decision, and no admin bypass.
