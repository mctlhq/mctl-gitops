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
- **Finally block** (line 6835). It settles the tick and the gate, then, unless hopping and while a claim is held,
  writes `terminal` or `release` by `last.state`, and reports claim abandonment.
- **Claim liveness.** The `progress` write is refreshed every 8th poll (about 2 h). The liveness bound is 40 polls
  (about 10 h), after which the owner can be reaped.
- **Marker convention.** Markers are evaluated once in the fresh-start arm and carried through `MergeWatchResume`
  (around line 1600). `tests/test_patch_memoization.py` pins this.
- **Hop.** The hop is decided at the top of the loop and returns `_WatchOutcome(resume=...)`. `_resume_merge_watch`
  rehydrates instance state and calls `_watch_pr(resume=...)`, with no `workflow.patched` call of its own.
- **Tail.** `_finish_after_watch` (line 4611) runs deploy observation, `security-record-landed` and the incident watch
  only when `pr_state.merged`.
- **Result.** `DevLoopResult` (line 1163): `pr` (line 1175, documented as "OPEN means the watch deadline expired"),
  `ended` (line 1195), `outcome` (line 1198).

### Deliveries

`_deliver` (line 2858) binds, then waits, then lands `Succeeded if decided else Failed`, where `decided` is
`(_is_approved() or _gates_passed) and not _abandoned`. `_settle_deliveries(hopping=False)` sets `_exiting` and waits
for every delivery task. An unbound delivery closes as `request-not-fulfilled`. The validator defers a post-gates
resume, so a delivery is rarely open during a watch, but one can be carried across a hop. The loop's own canonical
`we_` ends at the approve flip, before the watch.

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

- `orchestrator/temporal/cli.py:109` prints `not watched` for a None `pr` once implement succeeded. That would be
  misleading here, so it changes.
- `dispatcher._reconcile_closed_loops` (line 577) only fails non-terminal executions of a closed loop.
- mctl-api `restartIfAbandoned` (`internal/api/handlers_dev_loop.go`, read at its default branch) decodes `ended` and
  `implement` only. It answers `already_exists` for a Completed run with a non-abandon `ended`, and for a Failed run.

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
async def _decide_watch_end(self, service, slug, exit_name, last, deadline, track_ownership) -> _WatchDecision:
    fresh = await self._final_pr_read(service, slug)        # R2
    if fresh is None and exit_name == "grace-polls" and await self._no_pr_proven(
        service, slug, final_state, last, saw_open_pr):     # R5a
        return _WatchDecision(kind="no-pr")
    if fresh is None:
        record = await self._record_reconcile(exit_name, last, deadline, track_ownership)  # R7-R10
        return _WatchDecision(kind="reconcile" if record else "unrecorded", record=record)
    if fresh.state in ("MERGED", "CLOSED"):
        await self._terminal_claim(fresh, track_ownership)  # same write as the in-loop branch
        return _WatchDecision(kind="final", last=fresh)
    return _WatchDecision(kind="open", last=fresh)
```

The three sites use it as follows, all under `if terminal_reconcile:`, so that an unpatched history takes today's line:

| Site | `final` | `open` | `no-pr` | `reconcile` | `unrecorded` |
|---|---|---|---|---|---|
| `while ... else:` (deadline), guarded by `not self._abandoned` | return, `watch_end="final-read"` | `last=fresh`, release in `finally`, `watch_end="final-read"` | not reachable | release in `finally`, typed end | no release, raise after `finally` |
| grace-polls | same | `polls_without_pr=0`, `last=fresh`, fall through to the poll sleep | return `last=None`, `watch_end="no-pr-confirmed"` | same | same |
| non-transient read | same | `last=fresh`, sleep and `continue` | not reachable | same | same |

`_final_pr_read` keeps the last `found=False` state in `final_state`, so that `_no_pr_proven` can see whether a
reference was recorded. `_no_pr_proven` returns False without any activity when `final_state` carries a number or URL,
`last` carries a number, `saw_open_pr` is true, or every attempt failed with an `ActivityError`. Otherwise it runs
`confirm_no_pr` and returns `result.confirmed`. An `ActivityError` is False.

**Abandon (R16).** The deadline `else:` is guarded by `not self._abandoned`, so an abandon reaches no read and no
record. The watch sets `watch_end="abandoned-unverified"`, which is a local assignment with no command. It adds no
delay, and `finally` issues today's `release`.

In Python a `while ... else:` runs only when the condition goes false, never after `break` or `return`. So the hop and
the #516 break do not reach it. It sits inside the existing `try`, so before the relinquishing write in `finally`. A
continued run that starts past the deadline never enters the loop body, so the `else:` runs at once (R13). The hop
predicate is evaluated only inside the loop, so no hop can occur during the final read or the record.

- `_final_pr_read`: up to `FINAL_READ_ATTEMPTS = 3` calls of `get_pr_state`, each with `PR_STATE_TIMEOUT` and
  `PR_STATE_RETRY_POLICY`, with `workflow.sleep(FINAL_READ_BACKOFF = 2 min)` between them. It returns the first found
  state. Any `ActivityError`, transient or not, and any `found=False` counts as a failed attempt. The worst case is
  about 34 minutes after the exit, and it is never added to the deadline.
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
`confirmed=False`. `200 []` on every page is the provider's documented absence signal, and only that, with the
no-link status file, returns `confirmed=True`. The bad-filter case, where GitHub ignores a malformed `head` and returns
unrelated PRs, fails closed through "any item".

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
   failed read, so nothing is posted (R8). A 404 or 410 on the issue returns `issue-gone`.
3. Returns `already-recorded` with that comment's URL if the marker is on a comment where `user.type == "Bot"` or
   `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR`. Others are ignored, so a third party cannot suppress
   the record by pasting the marker text.
4. Otherwise posts the fixed template. A 201 returns `recorded` with the URL. A missing token, 401, 403, 429, 5xx or
   any other answer raises, so the workflow retries. A post that succeeded but timed out is caught by step 3 on retry.

The template names the workflow id, the exit, the last observed PR (state, URL, head SHA, or "none"), the open request
ids, and what to do: read the PR by hand, then re-trigger or close deliberately. It carries no other data.

`_record_reconcile` in the workflow:

```python
started = workflow.now()
last_refresh = started
interval = RECONCILE_RECORD_RETRY_MIN                 # 5 minutes
while True:
    try:
        result = await workflow.execute_activity(record_merge_watch_reconcile, inp,
            start_to_close_timeout=PR_STATE_TIMEOUT, retry_policy=RetryPolicy(maximum_attempts=3))
        if result.status in ("recorded", "already-recorded") and result.url:
            return result.url
        return ""                                   # issue-gone: R10
    except ActivityError:
        pass
    if workflow.now() - started >= RECONCILE_RECORD_WAIT:
        return ""                                   # R10
    await workflow.sleep(min(interval, started + RECONCILE_RECORD_WAIT - workflow.now()))
    interval = min(interval * 2, RECONCILE_RECORD_RETRY_MAX)  # 5, 10, 20, 30, 30, ...
    if workflow.now() - last_refresh >= timedelta(hours=2):
        await self._refresh_claim_liveness()          # the existing `progress` write
        last_refresh = workflow.now()
```

An unparsable `self._issue_url` returns `""` at once. `self._abandoned` is deliberately not in this loop (R9). The wait
is about 50 iterations over 24 hours, about 300 history events including the liveness writes. The liveness bound is
about 10 h and the refresh runs every 2 h, so four consecutive lost refreshes are tolerated, as on the watch's own
cadence.

**Fail closed (R10).** On `""` the watch sets `retain_claim = True`. The `finally` then skips the relinquishing write,
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
  - `ended="merge watch <exit>: pull-request state unreadable; reconciliation required"`, ahead of the abandon prefix;
  - it skips deploy, security and incidents because `pr_state` is None, and logs `MERGE_WATCH_RECONCILE_REQUIRED`.
- `reconcile-required` takes `self._reconcile_required = True` so that `_deliver` lands a still-undecided or
  newly settling delivery `Failed` with `merge-watch-reconcile-required` instead of evaluating `decided` (R11). The
  flag is set only under the marker, so no earlier history changes shape. The reason is added to the refusal vocabulary
  near line 506.
- The `finally` release reason is `merge watch <exit>: pull-request state unreadable, reconciliation recorded`.
- The `DevLoopResult.pr` and `_watch_pr` docstrings are corrected. The `pr` docstring states that on
  `abandoned-unverified` it is the last observed state and not verified current state.
- `cli.py` prints `pr: reconcile required (<record>)` before the `not watched` branch, `pr: none (confirmed)` on
  `no-pr-confirmed`, and adds `(last observed before abandon, not verified current)` on `abandoned-unverified`.

### 6. Redelivery and replay

- `get_pr_state` and `confirm_no_pr` are read-only, and on replay the recorded result is returned.
- The record activity is idempotent through its marker, and on replay its recorded result is returned.
- The `terminal` write goes through the existing idempotent `_ownership` path, and exactly one relinquishing write is
  issued per watch end, either in `_terminal_claim` or in `finally`, never both.
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

## Platform impact

- **Replay compatibility.** The marker is evaluated only in the fresh-start arm of `_watch_pr` and carried with a False
  default, so every pre-change history (`dev_loop_full.*`, `dev_loop_resumed.json`, `dev_loop_deferred_resume.json`,
  `pre_m1/`) schedules exactly the same commands. New fixtures are recorded post-change. The `*.prepatch` fixtures are
  not re-recorded.
- **New state.** `MergeWatchResume.terminal_reconcile`; `DevLoopResult.watch_end`, `last_observed_pr`,
  `reconcile_record`. All are defaulted, and old payloads decode. The feedback fields from M2a are untouched.
- **Resource impact.** A deadline-ending watch makes 1-3 extra `get_pr_state` calls and up to 2 extra timers. A
  grace-polls exit adds one `confirm_no_pr`, at least 2 GitHub reads. A reconcile-required watch adds a few GitHub reads
  and one comment. The workflow can stay open up to 24 hours longer in the worst case.
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
