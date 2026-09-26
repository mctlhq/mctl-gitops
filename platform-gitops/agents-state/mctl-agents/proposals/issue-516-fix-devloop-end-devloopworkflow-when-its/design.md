# Design: issue-516-fix-devloop-end-devloopworkflow-when-its

## Current state

### Where the loop ends, and where it does not

`orchestrator/temporal/workflows/dev_loop.py::DevLoopWorkflow` runs
`_run_loop` (line 2564) → `_implement` (3374) → `_watch_pr` (4747) →
`_finish_after_watch` (3286). The merge watch is the only long-lived stage:
its loop condition is

```python
while workflow.now() < deadline and not self._abandoned:      # dev_loop.py:4897
```

with `deadline = workflow.now() + MERGE_WATCH_DEADLINE` (`timedelta(days=14)`,
line 381). Inside, there are exactly four exits:

1. `state.state in ("MERGED", "CLOSED")` → `return _WatchOutcome(last=state)`
   after a `terminal` ownership write (4991-5008).
2. a non-transient `get_pr_state` failure → `return _WatchOutcome(last=last)`
   (4967-4976).
3. `polls_without_pr >= cadence.pr_lookup_grace_polls` → give up (5075-5084);
   `PR_LOOKUP_GRACE_POLLS = 8`, i.e. ~2 h at `MERGE_POLL_INTERVAL = 15 min`.
4. the 14-day deadline, or an `abandon` signal observed by the loop condition.

Nothing reads the proposal's own `status:`. A proposal that parks in
`review-stuck` (written by `run_shepherd` once `MAX_REVIEW_ATTEMPTS = 5`
address-review attempts are spent — see the `review-stuck` arms at
`run_shepherd.py:2790-3152`) leaves the PR OPEN, so exits 1-3 never fire and the
loop runs to exit 4. A proposal parked in `needs-triage` by
`run_implementer._mark_needs_triage` (`code="no-commits"`, `run_implementer.py:4224-4231`)
usually has no `pr:` link, so it converges via exit 3 — but only after eight
polls, and with a stale or recovered `pr:` field (the `branch-collision` shape at
`run_shepherd.py:3418`) it runs to exit 4 as well.

### What a parked watch keeps spending

- `_shepherd_tick` (3714) submits `cwft-mctl-agents-shepherd` scoped to
  `service`+`slug`, on every poll (`SHEPHERD_TICK_EVERY_POLLS = 1`) up to
  `SHEPHERD_TICKS_MAX = 96` (~24 h). `review-stuck` and `needs-triage` are not
  in `run_shepherd.SHEPHERD_INPUT_STATUSES` (`{"implemented", "review-fixing",
  "in-progress"}`, `run_shepherd.py:421`), so every one of those Argo runs is a
  clone plus a few `gh` reads that decide nothing.
- `get_pr_state` every 15 minutes, ~1340 activities over a full watch.
- `continue_as_new` hops: `_merge_watch_hop_suggested` (4696) fires at
  `MERGE_WATCH_HISTORY_FLOOR = 4096` history events, up to
  `MERGE_WATCH_MAX_HOPS = 16`.
- `_track_ownership` heartbeats every `LIFECYCLE_HEARTBEAT_EVERY_POLLS = 8`
  polls (line 460). That is the sharpest cost: ADR-010
  (`docs/adr/010-lifecycle-ownership-contract.md`) makes `held`/`dead` the
  takeover predicate, so a parked-but-heartbeating loop reads as a HEALTHY
  `devloop-workflow` owner (`OWNER_TYPE`, line 520) of a PR nobody is driving,
  and no other actor may take it.

### Why the idempotent start makes this permanent

`orchestrator/temporal/start.py` sets `DEV_LOOP_ID_CONFLICT_POLICY =
USE_EXISTING` against `workflow_id_for(issue_url)`
(`dev-loop-mctlhq-{repo}-{issue}`), so a second start attaches to the parked
execution and returns its handle. The dispatcher path is worse than a no-op:
`_validate_execution_request` refuses a `start` delivery to a live loop with
`loop-active` (`LOOP_ACTIVE_ERROR_TYPE`, line 1877). The intake poller uses
`DEV_LOOP_ID_REUSE_POLICY = ALLOW_DUPLICATE_FAILED_ONLY`, and the dispatcher
`DISPATCH_ID_REUSE_POLICY = ALLOW_DUPLICATE` — both only apply to a CLOSED run,
which is exactly what a parked loop never becomes.

### The status is already on the wire

`orchestrator/temporal/activities/pr_state.py::get_pr_state` GETs the
proposal's `.status.yaml` through the GitHub contents API (lines 98-123) and
then extracts only the `pr:` field with `_PR_FIELD_RE` (line 38). The decoded
file content is in hand at that point; `PRState` (42-67) simply carries no
status field. A terminal-status vocabulary already exists in this repo, just
not in the workflow: `pr_adoption.TERMINAL_STATUSES = frozenset({"merged",
"rejected", "review-stuck"})` (`orchestrator/pr_adoption.py:643`), duplicated in
`run_issue_directive_poller.py:129`, and the full status vocabulary is
enumerated in `run_shepherd.RECONCILE_INPUT_STATUSES` (422-432).

## Proposed solution

Three edits, no new activity, no new GitHub request, no new external contract.

### 1. `PRState` carries the proposal status

In `orchestrator/temporal/activities/pr_state.py`:

- add `proposal_status: str | None = None` to `PRState`, defaulted for the same
  reason `merged_at` and `head_sha` are (lines 57-67): results recorded before
  the field existed must still deserialize;
- add a `_STATUS_FIELD_RE` in the style of `_PR_FIELD_RE` (the module
  deliberately uses regexes over a YAML parse) and populate the field on every
  return path that has decoded the file — including the `found=False` ones (no
  `pr:` field, unparseable `pr:` URL, PR 404, wrong-repo refusal). `None` stays
  the answer only when the file itself was 404 or undecodable.

Populating it on the `found=False` paths is what lets a `needs-triage` proposal
with no PR link end on the FIRST poll instead of after eight.

### 2. `dev_loop.py` ends the watch on a terminal proposal status

- **Vocabulary**, beside the merge-watch constants (~line 405):

  ```python
  LOOP_TERMINAL_PROPOSAL_STATUSES = frozenset({
      "needs-triage", "review-stuck", "rejected", "error",
  })
  ```

  `merged` is deliberately EXCLUDED: the PR-state arm at 4991 already ends the
  watch on a merged PR and is what drives stages 6.2-6.4 in
  `_finish_after_watch` (deploy observation, incident watch), so ending on the
  *status* would skip them. `proposed`, `accepted`, `in-progress`,
  `implemented` and `review-fixing` are the live set and must keep the watch
  running.

- **Patch marker** `PROPOSAL_TERMINAL_PATCH = "proposal-terminal-end"`, beside
  `LAUNCH_CORRELATION_PATCH` (line 334), evaluated ONCE in `_watch_pr` next to
  `hop_enabled` (4800) and the cadence/shepherd/ownership markers (4819-4860).
  A pre-marker execution keeps polling to its deadline — migration by attrition,
  the rule `tests/test_patch_memoization.py` pins.

- **Carried across a hop**: `MergeWatchResume` gains
  `proposal_terminal_end: bool = False`, set in the hop's `resume_record`
  (4913-4945) and read in the `if resume is not None:` arm (4801-4810) beside
  `fast_cadence` / `shepherd_in_loop` / `concurrent_ticks` / `track_ownership`.
  Carried rather than re-derived for the reason stated there: a continued run
  must not adopt different behaviour than the run it replaces just because a
  marker was re-evaluated on a fresh history.

- **The check**, one site, right after the `get_pr_state` read so it covers both
  the `found` and the not-found branch, and positioned so the merged/closed arm
  still wins:

  ```python
  terminal_status = (
      _loop_terminal_status(state.proposal_status) if terminal_end_enabled else ""
  )
  if state.found:
      last = state
      polls_without_pr = 0
      if track_ownership and ...: await self._track_ownership(state)
      if state.state in ("MERGED", "CLOSED"):
          ...                                   # unchanged
      if terminal_status:
          watch_ended = f"proposal {terminal_status}"
          break
      poll_index += 1
      ...                                       # shepherd tick, unchanged
  else:
      polls_without_pr += 1
      if last is None and state.number is not None:
          last = state
      if terminal_status:
          watch_ended = f"proposal {terminal_status}"
          break
      if polls_without_pr >= cadence.pr_lookup_grace_polls:
          ...                                   # unchanged
  ```

  `_loop_terminal_status` is a module-level pure helper that strips and
  case-folds (the normalisation `ProposalCandidate.ignorable` already applies)
  and returns `""` for `None` or an unknown status — missing evidence is never
  terminal, matching `orchestrator/proposal_identity.py`'s stated rule.

  `break`, not `return`: the `finally` at 5091 is what settles an in-flight tick
  and issues the relinquishing ownership write, and `hopping` stays `False`, so
  the claim is RELEASED (or `terminal`, on the existing PR-state-derived
  `op` at 5131) rather than held the way a hop holds it. This is the same
  structural choice the abandon path makes, for the reason spelled out in
  `_watch_pr`'s own docstring (4762-4782).

- **Reason text**: inside the `finally`, when `watch_ended` is set, the
  `reason=` passed to `self._ownership(...)` (5142-5146) names the observed
  proposal status instead of "merge watch ended without a terminal
  pull-request state" — the row should record why the owner let go.

- **Carrying it out**: `_WatchOutcome` (1362) gains `ended: str = ""` (a plain
  return value, never serialized), returned at 5170. `_finish_after_watch`
  (3286) already takes `outcome`, so it sets
  `DevLoopResult.ended` from `outcome.ended` with the existing abandon string
  still taking precedence (3348). No new `DevLoopResult` field: `ended` was
  added by mctl-agents#420 for exactly this class of exit.

### 3. Nothing before the watch

No pre-watch status read is added. `_implement` already fails the workflow with
a typed `ApplicationError` (`ImplementationNotStarted` /
`ImplementationFailed` / `ImplementationFinalizationFailed`, 3453-3471) when the
implement run is not a success, and a run that reports Succeeded while its
proposal was parked reaches the watch's first poll immediately — the new check
catches it there, at the cost of one already-scheduled activity.

### What the operator sees afterwards

The execution COMPLETES, with `DevLoopResult.ended == "proposal review-stuck"`
(or `needs-triage`). `GET /api/v1/agents/dev-loop/{id}` then derives
`shepherd_in_loop = False` from the closed status with no query change here, so
`run_shepherd._dev_loop_owns` (`run_shepherd.py:203`) stops standing down and
the cron sweeper is free again. A later `/dev-loop/start` reports
`already_exists` rather than silently attaching to a parked run (mctl-api#287 /
#408), and the execution-request dispatcher can start a continuation under
`ALLOW_DUPLICATE` instead of being refused `loop-active`.

## Alternatives

1. **A separate `get_proposal_status` activity, polled alongside
   `get_pr_state`.** Cleanest separation, dropped on cost: it doubles the
   activity count per poll on the longest-lived workflow in the system — the
   exact objection `LIFECYCLE_HEARTBEAT_EVERY_POLLS`' own comment (lines
   455-459) records against one extra activity per poll — and it re-fetches a
   file `get_pr_state` has already downloaded in the same poll.

2. **Fail the workflow instead of completing it** (e.g. a
   `ProposalTerminal` `ApplicationError`). Tempting because
   `ALLOW_DUPLICATE_FAILED_ONLY` would then let a re-added intake label restart
   the issue after a human moves the proposal back to `accepted`. Dropped:
   investigate, approve and implement all succeeded, so a Failed execution
   misreports which layer broke — the distinction `_implement`'s typed errors
   exist to make — and every `no-commits` run would read red. mctl-agents#420
   set the precedent that a non-pipeline exit is a normal completion with
   `ended` set. Restart belongs to mctl-api#404. Recorded as an open question.

3. **Let the shepherd tick decide** — have `_shepherd_tick` report its verdict
   back and end the loop. Dropped twice over: the tick swallows its own
   failures by contract (3739-3771), and ticks stop at `SHEPHERD_TICKS_MAX`
   (~24 h) while the watch runs 14 days, so a proposal that goes terminal after
   the tick budget is spent would never be noticed.

4. **Shrink `MERGE_WATCH_DEADLINE`.** Cheapest possible change, dropped because
   it cannot tell "still under review" from "parked forever": it would cut
   legitimate long-lived reviews and still leave a terminal proposal watched for
   whatever the new deadline is.

## Platform impact

- **Migrations / state**: none. Three dataclasses gain defaulted fields
  (`PRState.proposal_status`, `MergeWatchResume.proposal_terminal_end`,
  `_WatchOutcome.ended`), which is the repo's stated rule for keeping recorded
  histories and results deserializable.
- **Backward compatibility / replay**: the behaviour change is gated on
  `workflow.patched(PROPOSAL_TERMINAL_PATCH)`, evaluated once per watch beside
  the existing markers, and carried across a hop. No command is added on the
  unpatched path. `tests/test_workflow_replay.py` asserts that each prepatch
  fixture predates each marker, so `tests/fixtures`' `dev_loop*` prepatch
  histories must be preserved (restored from git, never re-recorded) and a
  guard test added in the family of
  `test_dev_loop_full_prepatch_history_predates_the_launch_correlation_marker`.
- **Resource impact**: strictly negative cost. Per parked loop it removes up to
  ~1340 `get_pr_state` activities, up to 96 shepherd Argo submits (each a repo
  clone), up to 16 `continue_as_new` hops, and a worker slot held for 14 days.
  No new activity, no new HTTP request.
- **Lifecycle ownership (ADR-010)**: the terminal end goes through the existing
  `finally`, so the claim is relinquished with the `op` derivation at 5131
  unchanged — a `release` for a still-open PR ("work remains, somebody must
  take it"), which is what makes the entity claimable instead of showing a
  healthy owner heartbeating for a fortnight.
- **Risk: a momentarily unreadable or half-written `.status.yaml`.**
  Mitigation: `proposal_status=None` and any unknown status are never terminal
  (fail-open), the same rule `proposal_identity.py` states for an unreadable
  status; comparison is on a stripped, case-folded string.
- **Risk: an operator moves the proposal out of `needs-triage` back to
  `accepted` and finds the loop gone.** Mitigation: `ImplementSweepWorkflow`
  (`orchestrator/temporal/workflows/implement_sweep.py` with
  `activities/stranded.py`, which selects `status == "accepted"`) already picks
  up a stranded accepted proposal after
  `IMPLEMENT_SWEEP_GRACE_MINUTES`; explicit restart is mctl-api#404. This is a
  behaviour change operators must be told about, not a regression: today the
  parked loop would not have implemented it either.
- **Risk: ending early on a hand-edited `rejected` status whose PR is still
  open.** Blast radius is bounded — the watch is observational, and the PR falls
  back to the cron sweeper, which is where `pr_adoption.TERMINAL_STATUSES`
  already classifies `rejected`.
- **Risk: the terminal break skipping `_settle_tick`.** Prevented by
  construction: `break` keeps the `try`/`finally` intact, and T4 below asserts
  no tick is scheduled at or after the terminal poll.
