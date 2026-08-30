# Design: issue-239-fix-dev-loop-keep-shepherd-ownership-for

## Current state

**In-loop shepherd (owned proposals).** `DevLoopWorkflow`
(`orchestrator/temporal/workflows/dev_loop.py`) runs `_watch_pr` after a
successful implement step. It polls `get_pr_state`
(`orchestrator/temporal/activities/pr_state.py`) every `MERGE_POLL_INTERVAL`
(30 min) and, every `SHEPHERD_TICK_EVERY_POLLS` (8) polls — about every 4
hours — submits a targeted `mctl-agents-shepherd` CWFT tick via
`_shepherd_tick` (`_run_cwft("mctl-agents-shepherd", {"service": ...,
"slug": ...})`), capped at `SHEPHERD_TICKS_MAX` (12) ticks. It publishes
`shepherd_in_loop` (a `@workflow.query`, line 327-338) the moment the watch
starts, specifically so the ownership check below has a live signal instead
of relying on `ExecutionStatus = Running` alone.

**Ownership check used by the old cron.** `orchestrator/run_shepherd.py`'s
`_dev_loop_owns` (line 128) and `_filter_dev_loop_owned` (line 191) ask
mctl-api's `GET /api/v1/agents/dev-loop/{workflow_id}` for
`{status, shepherd_in_loop}` and treat a proposal as owned only when
`status == "Running" AND shepherd_in_loop is True`. This filter is applied
in `_discover_refs`'s sweep mode (no explicit `--slug`) — a *targeted*
invocation (`--service X --slug Y`, exactly what `_shepherd_tick` and
`mctl_trigger_shepherd --slug` both use) always processes the given slug
regardless of ownership, by design (module docstring, line 191-194).

**Standalone cron.** Per the issue and per `docs/adr/006-...md` /
`docs/agent-inventory.yaml`, the plan was to *narrow*
`cronworkflow-mctl-agents-shepherd.yaml` into a sweeper for proposals with no
live DevLoop, not delete it. The issue reports that in practice it is no
longer deployed after #213 — there is currently no scheduled process left
that calls `run_shepherd.py`'s sweep mode at all.

**ReconcileWorkflow already computes the orphan set, but doesn't act on it.**
`orchestrator/temporal/workflows/reconcile.py` runs on a 15-minute Temporal
Schedule (`orchestrator/temporal/worker.py`, `RECONCILE_SCHEDULE_ID`). Each
run calls `discover_and_project` then `detect_orphans`
(`orchestrator/temporal/activities/orphans.py`). `detect_orphans`:

1. Lists `accepted`/`in-progress`/`implemented`/`review-fixing` proposals via
   `run_shepherd._discover_refs(state_dir, reconcile=True)`.
2. For each, calls `run_shepherd.find_pr_for_proposal` — this already shells
   out via `gh` (through `_fetch_pr_snapshot`'s GraphQL query) to fetch a
   full `PRSnapshot` (head SHA, `mergeStateStatus`, `checks_green`,
   `reviewDecision`, draft state — everything `decide()` needs), not just
   the coarse `PRState` used by `get_pr_state`.
3. Skips it if the PR is `closed_unmerged` or `merged`.
4. Derives the expected `DevLoopWorkflow` id (`dev-loop-{owner}-{service}-{
   issue-number}`, matching `start.py`'s `workflow_id_for`) and skips it if
   that id is in `active_workflow_ids`.
5. Otherwise emits an `OrphanSignal` and logs `ORPHAN service=... slug=...
   status=... pr_url=... reason=...`.

`active_workflow_ids` comes from `VisibilityActivities.list_active_dev_loop_ids`
(`orchestrator/temporal/activities/visibility.py`), a Temporal visibility
query for `WorkflowType = 'DevLoopWorkflow' AND ExecutionStatus = 'Running'`
— **`Running`, not `shepherd_in_loop`**. This is coarser than
`_dev_loop_owns`'s HTTP check: a `DevLoopWorkflow` that is `Running` but has
not (yet, or ever, on a pre-patch history) reached `_watch_pr`'s
`self._shepherd_in_loop = True` line is counted as "owned" here and
therefore never gets a fallback tick either — the same blind spot the old
cron's extra `shepherd_in_loop` check exists to close, just not yet ported to
the Temporal-native path.

**The gap.** Everything needed to *decide* that PR #234's proposal (and any
future direct-`mctl_trigger_implementer` PR) needs another shepherd tick
already runs, every 15 minutes, inside `detect_orphans`. Nothing downstream
turns that `OrphanSignal` into a submitted tick. `ReconcileWorkflow.run`
returns `ReconcileWorkflowResult(discovery, orphans)` and that's the end of
the road — visible in Temporal history and worker logs, invisible to
anything that could act on it.

## Proposed solution

Keep `ReconcileWorkflow` as the single fallback owner (matching
`docs/agent-inventory.yaml`'s own description of where this was always
headed: "Temporal Schedule that adopts orphan `.status.yaml` entries into
workflows"). Give it an action step after detection, reusing the exact tick
`DevLoopWorkflow` already uses, so there is one code path for "run a targeted
shepherd tick" no matter who calls it.

### 1. Decide, not just detect, inside `detect_orphans`

Extend `OrphanSignal` (`orchestrator/temporal/activities/orphans.py`) with:

```python
@dataclass(frozen=True)
class OrphanSignal:
    service: str
    slug: str
    status: str
    pr_url: str | None
    reason: str
    head_sha: str | None = None
    decision: str | None = None        # run_shepherd.decide()'s first element
    review_attempts: int = 0
```

`_sync_detect_orphans` already has the `PRSnapshot` from
`find_pr_for_proposal` in hand for every candidate; before appending the
`OrphanSignal`, call `run_shepherd.read_codex_review(pr)` and
`run_shepherd.decide(pr, codex)` (both pure/read-only, already imported
transitively) and stash `pr.head_sha`, the decision, and `ref.review_attempts`
on the signal. No new I/O: this is the same data the CWFT tick would compute
moments later, computed once, for free, while we already have the PR
snapshot loaded.

This lets `ReconcileWorkflow` skip proposals whose decision is `"wait"`
(nothing to do this cycle — e.g. codex hasn't responded yet, checks aren't
green) without ever provisioning a shepherd CWFT's Hetzner volume for them,
which matches ADR-006's own stated cost rule for ticks: "each tick must be
justified by a PR-state change ... submit the shepherd CWFT only when there
is something for it to do."

### 2. A shared "submit one targeted tick" helper

`DevLoopWorkflow._shepherd_tick` (dev_loop.py line 694-735) already does
exactly what a fallback tick needs: resolve the released `shepherd` image,
call `_run_cwft("mctl-agents-shepherd", {"service", "slug", "agent_image",
"agent_version"})`, and `_record` the execution, swallowing
`ActivityError`/unexpected exceptions so one bad tick never kills the caller.
Extract this (plus its `_drain_tick`/`_settle_tick` cancellation-on-exit
partner, needed because ReconcileWorkflow — like DevLoopWorkflow — must not
end its execution with a dangling `asyncio.Task`) into a shared module,
e.g. `orchestrator/temporal/shepherd_tick.py`, parameterized by the caller's
name for logging (`"in-loop"` vs. `"reconcile"`). `DevLoopWorkflow` and
`ReconcileWorkflow` both import it. This is a refactor of existing,
already-tested logic, not new decision logic — `tests/test_dev_loop_workflow.py`'s
existing tick tests move with it and gain a `ReconcileWorkflow`-side
counterpart.

### 3. `ReconcileWorkflow` submits ticks for actionable orphans, throttled

After `detect_orphans` returns, `ReconcileWorkflow.run`:

1. Drops any signal whose `decision` is `None` (defensive — PR read failed
   upstream in a way that didn't skip the whole proposal) or `"wait"`.
2. For the rest, reads a small `last_orphan_tick` block from
   `.status.yaml` — `{at, head_sha, decision}` — via a new lightweight
   read helper next to `load_status`/`update_status_file` in
   `orchestrator/proposal_state.py` (no new activity boundary needed for a
   read this cheap; `detect_orphans` already reads the file). Ticks only if
   `head_sha`/`decision` differ from last time, or the cool-down window
   (`ORPHAN_TICK_COOLDOWN`, a new named constant beside
   `SHEPHERD_TICK_EVERY_POLLS`/`SHEPHERD_TICKS_MAX` in `dev_loop.py`,
   default long enough that even a fully "stuck" proposal is not re-ticked
   every 15 minutes forever) has elapsed since `at`.
3. Submits the surviving ticks concurrently via the shared helper from step
   2 above (bounded by a small concurrency cap, e.g. 4, since orphans are
   expected to be rare — this is the safety-net path, not the common one),
   the same "fire as a task, drain/settle on the way out" pattern
   `_watch_pr`/`_settle_tick` already use, so a still-running Argo shepherd
   run is never aborted by `ReconcileWorkflow` finishing — only un-watched,
   exactly like `_settle_tick`'s existing contract.
4. On successful submission, writes `last_orphan_tick = {at: now, head_sha,
   decision}` back to `.status.yaml` via `update_status_file(status_path,
   ref.status, last_orphan_tick={...})` — passing the *current* status back
   unchanged so this is a metadata-only update, not a status transition
   (the tick itself, once it runs, is what may transition status).

`ReconcileWorkflow` remains a short-lived, schedule-driven workflow (not a
long-running loop like `DevLoopWorkflow`); the schedule's own overlap
handling (Temporal's default, same as every other CWFT-backed schedule in
this repo, which is `concurrencyPolicy Forbid`-equivalent) is what prevents
two reconcile passes from double-submitting while ticks from a previous pass
are still settling.

### 4. Close the `Running`-vs-`shepherd_in_loop` ownership gap

Extend `VisibilityActivities` (or add a sibling activity) so
`detect_orphans`'s ownership check matches `_dev_loop_owns` semantics: a
`DevLoopWorkflow` only counts as owning a proposal if it is `Running` *and*
its `shepherd_in_loop` query answers `True`. Concretely, after
`list_active_dev_loop_ids` returns the `Running` set, query each candidate's
`shepherd_in_loop` via the Temporal client (`handle.query("shepherd_in_loop")`)
instead of the HTTP round-trip through mctl-api that `_dev_loop_owns` uses —
this code already runs inside the Temporal worker with a live client
(`VisibilityActivities.__init__` holds one), so there is no need to go back
out through mctl-api's HTTP endpoint the way the pod-based shepherd CWFT
does. Same fail-open rule as everywhere else in this area: a query failure
(workflow gone, non-deterministic error) means "not confirmed owned," so the
fallback sweeps it rather than risk a permanently-orphaned proposal.

### 5. Observability

`detect_orphans` already logs one line per orphan. Extend it with
`head_sha`, `decision`, `review_attempts`. Add one log line per submitted
(or throttled) tick in `ReconcileWorkflow` itself: `RECONCILE_TICK
service=... slug=... decision=... head_sha=... attempt=... submitted=<bool>
next_check=<+15m>` — greppable the same way `run_shepherd.process_one`'s
per-tick line already is. `_record`'s existing `ExecutionRecord` write (via
the shared helper from step 2) already carries `temporal_workflow_id` —
for a `ReconcileWorkflow`-submitted tick that will read
`reconcile-mctl-agents`, which is enough to distinguish "fallback drove
this" from "DevLoop drove this" (`dev-loop-...`) in the executions ledger
without a schema change.

## Alternatives

1. **Restore the standalone Argo CronWorkflow sweeper** (redeploy
   `cronworkflow-mctl-agents-shepherd.yaml` in sweep mode, per ADR-006's
   original plan). Rejected as the primary fix: it reintroduces a second,
   independently-scheduled driver that duplicates work `ReconcileWorkflow`
   already does every 15 minutes (it re-derives the same actionable-proposal
   list and re-fetches the same PR snapshots), and reverses the direction
   `docs/agent-inventory.yaml` already committed to ("becomes: Temporal
   Schedule that adopts orphan `.status.yaml` entries into workflows").
   Still, `run_shepherd.py --reconcile`'s pure functions
   (`_dev_loop_owns`/`_filter_dev_loop_owned`/`decide`) stay exactly as-is
   and are exactly what this proposal reuses, so nothing about this
   alternative is wasted if it's ever needed as a stopgap.

2. **Make `mctl_trigger_implementer` start/adopt a durable DevLoop review
   stage** (the issue's "preferred" option). Rejected for this proposal, not
   architecturally, but scope: `mctl_trigger_implementer` is implemented in
   mctl-api, not in this clone of mctl-agents, so grounding that change in
   real code here isn't possible, and it would still need something to
   handle proposals that predate this fix or whose adoption call itself
   fails — i.e., a fallback reconciler is needed either way. Recorded as
   follow-up scope in requirements.md's "Out of scope."

3. **Have `ReconcileWorkflow` call `run_implementer`/`run_shepherd`'s
   `process_one` in-process** (inside the Temporal activity) instead of
   submitting an Argo CWFT tick. Rejected: `apply_followup`'s implementer
   subprocess needs the Claude Agent SDK, a `GITHUB_TOKEN`-scoped clone, and
   the sandboxed Hetzner-volume workdir the Argo CWFT provisions
   (`config/settings.py`'s `SHEPHERD_DIR`, `orchestrator/options.py`'s
   `build_shepherd_options`) — none of which the lightweight Temporal worker
   pod has or should have. Splitting "decide" (cheap, safe in-process, done
   in step 1 above) from "act" (expensive, sandboxed, stays a CWFT
   submission) is exactly what `DevLoopWorkflow` already does, and this
   proposal keeps that split.

## Platform impact

- **Migrations:** none. `.status.yaml`'s new `last_orphan_tick` block is
  additive; `load_status`/`_load_status` already tolerate unknown keys
  (plain `yaml.safe_load` into a dict).
- **Backward compatibility:** `OrphanSignal`'s new fields are all optional
  with defaults, so `tests/test_reconcile_workflow.py`'s existing fixtures
  (which construct `OrphanSignal` without them) keep working. The
  `shepherd_tick` extraction is a pure refactor of `_shepherd_tick`/
  `_drain_tick`/`_settle_tick`'s existing, tested behavior; `DevLoopWorkflow`
  callers change import paths only.
- **Resource impact:** the new cost is shepherd CWFT ticks (one Hetzner
  volume each) for proposals that previously got none. Bounded by: (a) the
  orphan set itself is small — only proposals with no live DevLoop, which
  today means direct `mctl_trigger_implementer` runs and incident-responder
  PRs; (b) step 1's `decision != "wait"` filter means a tick is only
  submitted when there is a real state change to act on; (c) step 3's
  cool-down prevents re-ticking a proposal whose decision hasn't moved.
  Worst case (many simultaneous orphans all needing action at once) is
  bounded by the concurrency cap in step 3.
- **Risks + mitigations:**
  - *Two actors race on one proposal.* Mitigated by step 4 closing the
    `Running`-vs-`shepherd_in_loop` gap, plus the pre-existing
    `_filter_dev_loop_owned`/`_dev_loop_owns` behavior being unchanged for
    the sweep-mode path (unaffected — this proposal doesn't touch sweep
    mode, only adds a Temporal-native caller of the *targeted* path, which
    already ignores ownership by design).
  - *`ReconcileWorkflow`'s single pass now runs longer* (it awaits/settles
    tick submissions, not just two 5-minute activities). Mitigated by
    firing ticks as concurrent tasks and settling them with the same
    cancel-but-don't-abort-the-Argo-run contract `_settle_tick` already
    proves out in `DevLoopWorkflow`; a `ReconcileWorkflow` run that takes
    longer than 15 minutes simply causes the next scheduled run to be
    skipped/queued per the schedule's overlap policy, not to fail.
  - *`decide()` computed during detection goes stale by the time the CWFT
    tick actually runs* (findings/CI could change in the intervening
    seconds). Not a correctness risk: `process_one` inside the CWFT
    re-fetches a fresh `PRSnapshot` and re-runs `decide()` itself before
    doing anything — the reconcile-side decision is only ever used to decide
    *whether to submit a tick*, never to decide what the tick actually does.

## Accepted design correction (authoritative)

This section supersedes the direct-tick and `last_orphan_tick` design above.

Use a dedicated `FallbackReviewWorkflow` with deterministic ID `fallback-review-{service}-{slug}`. Reconcile starts/adopts it idempotently; the fallback owns one in-flight tick, cooldown timers, bounded retries and terminal exit. All PR/status/Temporal-client/CWFT operations are activities; workflow code performs no direct I/O. Existing `.status.yaml` transitions stay inside the serialized Argo GitOps commit step, so the proposed direct `proposal_state.py` metadata write is removed.

Ownership handoff is bidirectional: fallback checks `Running && shepherd_in_loop` before each tick; DevLoop cancels and awaits fallback before setting `shepherd_in_loop=True`. The submission helper returns `submitted`, `already_exists`, `transient_failure` or `deterministic_failure`; only success advances cooldown. The targeted shepherd revalidates head and gates before acting. The reconcile Schedule explicitly uses non-overlap (`SKIP`).

## P1 concurrency and retry correction (authoritative)

Each fallback cycle allocates and persists one deterministic `tick_id = <fallback-workflow-id>-<proposal>-<head-sha>-<cycle>` before calling the submission activity. The mctl-api/CWFT boundary maps that ID to an explicit Argo workflow name or idempotency key. Activity retries never allocate another cycle or ID; `AlreadyExists` means adopt and observe the existing run. The durable cycle advances only after the tick reaches a terminal outcome.

Submission errors are classified. Retryable transport errors use bounded Temporal activity retry/backoff without incrementing `review_attempts`. Deterministic validation/auth/configuration failures increment a separately persisted, bounded `submission_failures` counter; exhaustion records evidence and ends in `review-stuck`.

Cancellation is a handoff protocol, not merely a Temporal child cancellation. The fallback cancellation handler determines whether the external Argo run was created. If created, it requests cancellation when supported and waits for terminal confirmation; otherwise it adopts and waits for terminal completion. DevLoop waits for that handler to finish before setting `shepherd_in_loop=True`. Thus no external fallback tick remains able to write status after ownership transfers.

## Create-after-cancellation barrier correction

The submission activity and deterministic remote tick ID form a two-phase handoff barrier. Cancellation does not infer absence from a single lookup. The fallback requests activity cancellation, then awaits the activity's terminal outcome (or a durable cancellation acknowledgement whose contract guarantees the remote request cannot later create). Only then does it reconcile the deterministic ID. An existing run is adopted and driven to terminal cancellation/completion. An absent run is accepted only after the activity is terminal, so a late remote create cannot appear after DevLoop takes ownership. DevLoop awaits the entire barrier before publishing `shepherd_in_loop=True`.
