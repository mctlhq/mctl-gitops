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

## Cancellation race closure (authoritative)

- A negative pre-create lookup is not a handoff barrier. When takeover races an in-flight submission activity, the fallback SHALL first wait until that activity reaches a terminal result or cancellation acknowledgement that proves no remote create can still complete.
- After the submission activity is terminal, the fallback SHALL reconcile the stable tick ID against Argo. If a run exists, it SHALL cancel/adopt and await the run's terminal state; only a terminal activity followed by an absent run, or a terminal run, permits ownership acknowledgement.
- DevLoop SHALL remain blocked from publishing `shepherd_in_loop=True` throughout this protocol. Tests SHALL cover cancellation before request send, during response loss, and after remote create.

## Ownership arbitration and terminal status corrections

- Fallback creation and DevLoop takeover SHALL be serialized by one durable proposal-scoped ownership arbiter. DevLoop first records a `takeover_pending` claim/epoch in that arbiter; only then may it look up and drain a fallback. Reconcile SHALL acquire a fallback grant from the same arbiter before starting or submitting work, and SHALL be denied once takeover is pending.
- Every fallback submission SHALL carry the arbiter epoch and revalidate that grant immediately before remote create. A stale grant cannot create or mutate state.
- When deterministic submission failures exhaust their bounded budget without creating an Argo tick, a dedicated idempotent Temporal activity SHALL persist `review-stuck` and evidence through the same repository mutex/serialized GitOps transaction used by existing status writers. Temporal workflow code performs no direct I/O, and the terminal write does not depend on a shepherd CWFT existing.

## Claim recovery and fenced terminal-write corrections

- A `takeover_pending` claim SHALL identify the owning DevLoop workflow ID and run ID and SHALL be renewable. The arbiter SHALL reclaim it only after an activity confirms that exact Temporal execution is terminal (completed, failed, terminated, or cancelled). Visibility/query failure is fail-closed and does not revoke a live claim.
- DevLoop SHALL release or finalize its claim in normal completion/cancellation handlers; Reconcile SHALL periodically request recovery for claims whose owner is confirmed terminal, so a crashed DevLoop cannot orphan the proposal indefinitely.
- The submission-exhaustion status activity SHALL use compare-and-set preconditions under the repository mutex: expected proposal status, expected PR head SHA, expected ownership epoch, and open/unmerged PR state. Any mismatch SHALL produce a recorded `superseded/no-op`, never overwrite newer state.

## External-state repair and transient-outage corrections

- A terminal status write based on GitHub state SHALL be provisional until a post-commit GitHub revalidation confirms the same PR head and open/unmerged state. If the external state changed, the activity SHALL immediately execute an idempotent compensating GitOps transaction that removes/supersedes the stale `review-stuck` evidence and projects the newer head or terminal merged/closed state.
- Reconcile SHALL always give externally observed merged/closed/new-head state precedence over a provisional or stale submission-exhaustion status, so an external change after revalidation is repaired on the next event/cycle.
- Exhausting bounded activity retries for a transient submission error SHALL keep the same logical tick ID and durable cycle state, schedule a workflow-level exponential-backoff timer, and retry after the timer. A separate bounded `transient_outage_windows` budget SHALL prevent endless outage loops; exhaustion uses the fenced terminal status path with operational evidence and does not increment `review_attempts`.

## Terminal-writer ownership fencing correction

- The arbiter SHALL register a terminal status activity as in-flight fallback work. DevLoop takeover SHALL drain that activity together with CWFT submission/ticks before ownership publication.
- After committing provisional terminal status, the activity SHALL revalidate both GitHub state and the arbiter epoch/claim. If either changed, it SHALL execute the same idempotent compensating GitOps repair before reporting completion.
- DevLoop SHALL not publish ownership until the registered terminal writer and any required compensation are terminal. A stale fallback epoch can therefore never leave authoritative `review-stuck` state after takeover.

## Observable decisions and coordinated rollback corrections

- Every fallback decision — submitted or skipped for cooldown, takeover, transient failure, stale head, or exhausted budget — SHALL be projected through an idempotent serialized activity into operator-visible audit/status state. The projection SHALL include proposal, owner/epoch, PR/head SHA, decision and reason, review/submission counters, last tick, and next eligible tick. Durable workflow state remains replay-safe and is not the sole observability surface.
- Rollback SHALL first stop new fallback grants, mark the arbiter draining, and await/cancel all registered fallback ticks, submitters, and terminal writers. Only after the drain barrier may deployment consistently disable/revert Reconcile fallback creation, DevLoop handoff integration, arbiter, and status projection together. Mixed old/new ownership components are forbidden.

## Bounded drain and projection-writer corrections

- Takeover drain SHALL use bounded retries and an observation deadline. Exhaustion SHALL enter an operator-visible `takeover_drain_stuck` state that preserves the no-overlap fence; it SHALL NOT grant fallback ownership or publish DevLoop ownership.
- Recovery from `takeover_drain_stuck` SHALL be an explicit idempotent operation that resumes the same drain or advances only after all registered external work is independently proven terminal. Timeout alone is never proof of termination.
- Decision-projection idempotency SHALL include reason and durable occurrence/attempt, or use an equivalent compare-and-update transaction, so repeated same-cycle skips/failures retain current counters and next-tick evidence.
- The arbiter SHALL register decision-projection writers as in-flight work. Takeover and rollback SHALL drain them together with ticks, submitters, and terminal writers before ownership publication or coordinated component removal.

## Compensating-write CAS correction

- A compensating GitOps transaction SHALL re-acquire the repository mutex and compare the original provisional transaction ID, provisional status revision, expected head, and arbiter epoch before writing.
- If an intervening writer advanced proposal state, compensation SHALL no-op with superseded evidence or recompute from the newer snapshot; it SHALL NOT overwrite the newer state.
- Compensation idempotency SHALL bind the original transaction and expected provisional revision. Tests SHALL cover an unrelated serialized status write between provisional commit and compensation.

## Provisional-transaction retry resumption correction

- The terminal status activity SHALL persist or reconstruct its phase from the provisional transaction record. On activity retry, if repository state already contains the exact activity-owned provisional transaction ID, provisional revision, expected head, and arbiter epoch, it SHALL skip the initial write and resume mandatory post-commit GitHub/arbiter revalidation and any compensation.
- A CAS mismatch is 'superseded/no-op' only when state does not match either the expected pre-write snapshot or this activity's own exact provisional record. Retrying after a successful provisional commit can therefore never silently omit revalidation.
- Tests SHALL crash the worker immediately after the provisional commit and before revalidation, then retry and prove that merge/head/takeover changes are revalidated and repaired exactly once.
