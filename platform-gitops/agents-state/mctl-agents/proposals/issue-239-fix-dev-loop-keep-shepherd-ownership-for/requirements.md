# fix(dev-loop): keep shepherd ownership for PRs created by direct implementer runs

## Context

`DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py`) drives its own
in-loop shepherd ticks (`_watch_pr` / `_shepherd_tick`, added by #213/#231) for
any proposal it owns end-to-end: investigate -> approve -> implement -> review
-> merge. That loop is the only thing left in mctl-agents that actively drives
a PR through review/fix/merge — the standalone shepherd CronWorkflow that used
to sweep every actionable proposal every 2 hours is gone from the deployed
gitops state (per the issue; `docs/adr/006-dev-loop-merge-deploy-monitor.md`
and `docs/agent-inventory.yaml` both still describe it as "narrowed to a
sweeper, not deleted" — the actual deployment has drifted from that decision).

`mctl_trigger_implementer` (Tier 2, invoked directly by an operator or by the
incident responder) can open a PR for an `accepted` proposal without ever
starting a `DevLoopWorkflow` — there is no issue-driven Temporal execution for
that proposal at all. Today, once such a PR receives a `CHANGES_REQUESTED`
review, nothing in the system drives it further. The only currently-running
fallback, `ReconcileWorkflow` (`orchestrator/temporal/workflows/reconcile.py`,
scheduled every 15 minutes), already computes exactly this set in
`detect_orphans` (`orchestrator/temporal/activities/orphans.py`) — an
"actionable" proposal (`accepted`/`in-progress`/`implemented`/`review-fixing`)
with an open, unmerged PR and no matching `Running` `DevLoopWorkflow` — but it
only logs an `ORPHAN ...` line. It never acts. PR #234 (opened from the
`issue-227-*` proposal via a direct `mctl_trigger_implementer` run) is the
concrete incident: after one manual `mctl_trigger_shepherd` tick, a fresh
`CHANGES_REQUESTED` round produced no further ticks, and the PR head never
moved again.

This proposal closes that gap: turn `ReconcileWorkflow`'s existing orphan
*detection* into orphan *action*, submitting the same targeted
`mctl-agents-shepherd` tick that `DevLoopWorkflow` already uses
(service+slug, which bypasses `run_shepherd`'s sweep-mode ownership filter),
so every orphaned proposal keeps getting driven to merge/close/`review-stuck`
without an operator having to notice and re-trigger it by hand.

## User stories

- AS an operator running `mctl_trigger_implementer` directly (outside a
  DevLoop) I WANT the resulting PR to keep receiving review/fix ticks after
  `CHANGES_REQUESTED` SO THAT I never have to notice a stalled PR and manually
  call `mctl_trigger_shepherd`.
- AS the platform I WANT exactly one actor driving each proposal's review loop
  at a time SO THAT an in-loop `DevLoopWorkflow` shepherd tick and a fallback
  tick never race on the same `.status.yaml` or the same PR.
- AS an operator debugging a stuck PR I WANT to see, per proposal, who owns
  its review loop (a live DevLoop vs. the fallback reconciler), the last head
  SHA acted on, the attempt count, and the next scheduled tick SO THAT I can
  tell "still working" from "actually stuck" without reading Temporal history.

## Acceptance criteria (EARS)

- WHEN an `accepted`/`in-progress`/`implemented`/`review-fixing` proposal has
  an open, unmerged PR and no `Running` `DevLoopWorkflow` owns it, THE SYSTEM
  SHALL submit a targeted `mctl-agents-shepherd` tick (service+slug) for that
  proposal within one `ReconcileWorkflow` cycle of the condition becoming
  true, without any operator calling `mctl_trigger_shepherd`.
- WHEN a fallback-driven tick pushes a review-fix commit and the PR's head
  SHA changes, THE SYSTEM SHALL re-evaluate that proposal on a later
  `ReconcileWorkflow` cycle and submit another tick if the PR is still
  actionable — the loop SHALL NOT be one-shot.
- WHILE a `DevLoopWorkflow` execution actively ticks shepherd for a proposal
  (`shepherd_in_loop` true and `Running`), THE SYSTEM SHALL NOT submit a
  fallback tick for that same proposal — exactly one owner acts on it at a
  time.
- IF a proposal's `.status.yaml` already carries `review_attempts >=
  MAX_REVIEW_ATTEMPTS` THEN THE SYSTEM SHALL leave it in (or flip it to)
  `review-stuck` and SHALL NOT submit another fallback tick for it.
- WHEN a fallback tick evaluates a PR, THE SYSTEM SHALL base its decision
  only on review findings anchored to the PR's current head SHA — stale
  findings from a superseded head SHALL NOT trigger a fix or a merge.
- IF a fallback tick's implementer follow-up subprocess fails for a
  transient reason (auth/network/branch-protection) THEN THE SYSTEM SHALL
  retry on a later cycle without incrementing `review_attempts`; IF it fails
  deterministically (no commits produced, branch missing) THEN THE SYSTEM
  SHALL count the attempt.
- WHEN a fallback tick is submitted or skipped, THE SYSTEM SHALL record
  enough information (proposal, PR, head SHA, decision, attempt count, and
  that the fallback path — not a DevLoop — acted) for an operator to
  reconstruct what happened without re-deriving it from GitHub.

## Out of scope

- The "preferred" design option named in the issue (making a direct
  `mctl_trigger_implementer` run start/adopt a durable `DevLoopWorkflow`
  review stage) — that trigger lives in mctl-api, outside this repo's clone,
  and would require a second, cross-repo change. This proposal implements
  the "compatible fallback" instead: a scheduled sweeper that only acts on
  proposals no live DevLoop owns, which is already the direction
  `docs/agent-inventory.yaml` names for `ReconcileWorkflow` ("Temporal
  Schedule that adopts orphan `.status.yaml` entries into workflows").
- A GitHub review webhook. The issue itself treats this as a latency
  optimization on top of polling/reconciliation, not a replacement for it.
- Restoring the old standalone `cronworkflow-mctl-agents-shepherd.yaml` sweep
  (every actionable proposal, every 2h) as a separate Argo cron. Its
  ownership-skip behavior (`_dev_loop_owns` / `_filter_dev_loop_owned` in
  `orchestrator/run_shepherd.py`) is preserved and reused, but the sweep
  itself is folded into the already-scheduled `ReconcileWorkflow` rather than
  reintroduced as a second, separately-scheduled driver.
- Changing `decide()`, `MAX_REVIEW_ATTEMPTS`, the settle window, or any other
  part of the pure shepherd decision logic in `orchestrator/run_shepherd.py`.
  Those already satisfy the head-pinning, attempt-cap, and
  transient-vs-deterministic-failure requirements; this proposal only adds a
  new *caller* of the existing, unmodified tick.
- Deploy/monitor stages (ADR-006 §6.2-6.4) — unrelated to review-loop
  ownership.

## Open questions

- Exact cool-down interval between fallback ticks for the same proposal.
  `DevLoopWorkflow` ticks roughly every 4 hours because each tick provisions
  a Hetzner volume (ADR-006 cost note). This proposal assumes a similar,
  configurable cool-down (default: skip re-ticking a proposal whose last
  fallback tick recorded the same head SHA and decision, tick immediately on
  a head-SHA or decision change, otherwise wait at least one full cool-down
  window) rather than ticking on every 15-minute `ReconcileWorkflow` cycle.
  The concrete default value is left to the implementer; record it as a
  named constant next to `SHEPHERD_TICK_EVERY_POLLS`/`SHEPHERD_TICKS_MAX`.
- Whether the ownership check should be tightened to match
  `run_shepherd._dev_loop_owns`, which additionally requires
  `shepherd_in_loop is True` (not just `Running`) before treating a proposal
  as owned. Today's `list_active_dev_loop_ids` /
  `orchestrator/temporal/activities/orphans.py` ownership test only checks
  `Running`, so a `DevLoopWorkflow` that is running but has not yet reached
  (or, on a pre-patch history, will never reach) its ticking stage is
  currently treated as "owned" and skipped by both the old cron's HTTP check
  and this proposal's Temporal-native check. This proposal assumes closing
  that gap is in scope (see design.md) since it is required for AC1 to hold
  in that case, but flags it as the one place where matching "the existing
  ownership query/filter" literally (unchanged) versus tightening it are in
  tension.
- Whether fallback-triggered ticks need a distinct marker in the executions
  audit trail (`ExecutionRecord` in `orchestrator/temporal/activities/state.py`
  has no "trigger source" field today) versus being distinguishable only by
  their `temporal_workflow_id` (`reconcile-mctl-agents`) already recorded on
  every audit row. Assumed sufficient without a schema change; revisit if an
  operator later needs to filter executions by trigger source at the API
  layer.

## Contract corrections before acceptance (authoritative)

- The fallback SHALL be a durable single-owner Temporal execution (`FallbackReviewWorkflow`) with deterministic ID; `ReconcileWorkflow` only discovers and idempotently starts/adopts it.
- The reconcile Schedule SHALL declare an explicit non-overlap policy. Workflow-ID conflict means already adopted, not a second owner.
- Temporal workflow code SHALL perform no filesystem, GitHub, network, wall-clock or `.status.yaml` I/O. These operations and CWFT submission SHALL cross activity/child-workflow boundaries. GitOps status writes remain in the existing mutex-protected Argo path.
- Ownership handoff SHALL be explicit: before publishing `shepherd_in_loop=True`, DevLoop cancels and awaits the proposal's fallback owner; fallback re-checks live DevLoop ownership before every tick and exits on takeover.
- CWFT submission SHALL return a typed result. Failed submission writes no success/cooldown marker and retries without incrementing `review_attempts`.
- Cooldown lives in durable workflow state/timers, not direct `.status.yaml` reads. The targeted shepherd re-fetches current head and preserves stale-review filtering, bounded retries and `--match-head-commit`.

## P1 review corrections (authoritative)

- CWFT submission uses a stable logical tick ID derived from fallback workflow ID/run, proposal slug, reviewed head SHA, and durable cycle number. Every activity retry reuses that ID; an Argo `AlreadyExists` response adopts the existing workflow instead of creating a duplicate.
- Transport or response-loss failures that remain plausibly transient retry without consuming the review-fix budget. A classified deterministic submission failure increments a separate bounded `submission_failures` budget. Reaching that cap transitions the proposal to `review-stuck` with the tick ID and failure evidence; no submission failure may retry forever.
- Ownership transfer is not acknowledged while an external fallback Argo tick can still mutate the proposal. On DevLoop takeover, the fallback cancels the pending submission and then aborts, drains, or adopts and awaits the already-created Argo workflow to a terminal state. Only after that barrier may DevLoop publish `shepherd_in_loop=True`.
