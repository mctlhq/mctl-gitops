# Sweep `accepted` proposals that no live DevLoopWorkflow owns

## Context

Today the `mctl-agents-implement` CWFT is submitted from exactly one place:
`DevLoopWorkflow._implement`, the step that runs after the approve flip
(`orchestrator/temporal/workflows/dev_loop.py`, the `atomic_approve` branch).
Flipping `.status.yaml` from `proposed` to `accepted` is a side effect of that
step, never a trigger. Any other approval path — `mctl_trigger_approve`, which
invokes the standalone `mctl-agents-approve` operation, or the incident
responder, which writes `status: accepted` directly
(`orchestrator/run_incident_responder.py`) — produces an `accepted` proposal
with no owner. Nothing promotes it: `ReconcileWorkflow._apply` submits only
`APPLY_OPERATION = "mctl-agents-reconcile"` and its discovery half is
read-only by contract; `detect_orphans` skips every proposal without an open
PR (`if pr is None ... continue` in
`orchestrator/temporal/activities/orphans.py`), so the state is not even
reported; and the Argo `cronworkflow-mctl-agents-implement` that used to sweep
`accepted` every five minutes is recorded as `suspend: true` in
`docs/agent-inventory.yaml`. The sweeper logic itself is intact and working —
`run_implementer.find_accepted_proposals` is called by `main()` on every manual
`mctl_trigger_implementer` run — there is simply no schedule that calls it.

The consequence observed on 2026-09-19 is three proposals (`mctl-api#335`,
`mctl-gitops#1278`, `mctlhq/.github#99`) approved in the same second and sitting
`accepted` with no `attempt:`, no branch, no PR and no `failure:` for two hours,
until a hand-run `mctl_trigger_implementer` picked all three up immediately.
This is worse than a failure: there is no failure to find. This proposal makes
`accepted` an actionable queue again by giving the existing sweeper a Temporal
schedule that is dedup-safe against live DevLoopWorkflows, and by making the
stranded condition visible in logs and in the tick's result even when the sweep
declines to act.

## User stories

- AS a platform operator I WANT a proposal I approve outside a live
  DevLoopWorkflow to be implemented anyway SO THAT approving through
  `mctl_trigger_approve` does not silently mean nothing.
- AS a platform operator I WANT the stranded condition named in logs and in a
  workflow result SO THAT "nothing is happening" is distinguishable from
  "nothing needs to happen".
- AS an on-call engineer I WANT the sweep to refuse to act whenever it cannot
  prove a proposal is unowned SO THAT recovery never causes a second
  implementer run on a proposal a live loop is already driving.
- AS the incident responder I WANT the auto-accepted proposals I write to reach
  the implementer without a human running a CLI SO THAT incident fixes are not
  gated on someone noticing.

## Acceptance criteria (EARS)

- WHEN the implement-sweep schedule fires THE SYSTEM SHALL read every
  proposal's committed status from gitops `main` and select those with
  `status: accepted`.
- WHEN a candidate proposal's derived DevLoopWorkflow id (as computed today by
  `orphans._expected_workflow_id`) is present in the running-DevLoopWorkflow set
  returned by `list_active_dev_loop_ids` THE SYSTEM SHALL skip that proposal.
- IF the `list_active_dev_loop_ids` visibility query fails after its retries
  THEN THE SYSTEM SHALL skip the entire tick, record a `skipped_reason`, and
  submit nothing.
- WHEN a candidate proposal carries an unexpired `attempt` lease THE SYSTEM
  SHALL skip it, because an implementer run already holds it.
- WHEN a candidate proposal carries a `pr:` URL THE SYSTEM SHALL skip it and
  leave it to `detect_orphans` and the shepherd, which own the
  proposal-with-a-PR case.
- IF a candidate proposal is unrunnable as written — `proposal_state.
  unrunnable_reason` returns `approval-missing`, or a `blocked` marker is
  present — THEN THE SYSTEM SHALL skip it and log the reason rather than
  submitting a run that can only refuse.
- WHILE a candidate proposal's `updated_at` is newer than the stranding grace
  period THE SYSTEM SHALL leave it alone, so a DevLoopWorkflow between its
  approve flip and its implement submit is never raced.
- WHEN one or more proposals survive every filter THE SYSTEM SHALL submit
  `mctl-agents-implement` scoped with both `service` and `slug`, routed to
  `IMPLEMENTATION_TASK_QUEUE` so the admission capacity in ADR-008 D7 governs
  how many implementer runs exist at once.
- WHILE a swept implement run for a given `(service, slug)` is still running
  THE SYSTEM SHALL NOT start a second one for the same pair.
- WHEN more proposals qualify in one tick than the per-tick submit cap allows
  THE SYSTEM SHALL submit up to the cap, log every candidate it did not submit,
  and report the count in the tick's result.
- WHEN the tick finishes THE SYSTEM SHALL log one `STRANDED service=... slug=...
  reason=...` line per candidate and return the candidate, submitted and skipped
  counts in the workflow result.
- WHILE the implement-sweep schedule is registered THE SYSTEM SHALL NOT fire on
  a minute already used by another Temporal schedule or by a `mctl-gitops`
  CronWorkflow that takes the `mctl-gitops-main-writes` mutex (the invariant
  asserted by `tests/test_worker_schedules.py`).
- IF an operator pauses the implement-sweep schedule THEN THE SYSTEM SHALL keep
  it paused across worker restarts and redeploys (`_ensure_schedule` converges
  spec and overlap policy only, never `state`).

## Out of scope

- The guard half of the issue's suggested fix (1): making
  `mctl_trigger_approve` / the `mctl-agents-approve` operation refuse or warn
  when no live DevLoopWorkflow exists. That code is in `mctl-api` (and the CWFT
  in `mctl-gitops`), which the Tier 2 implementer cannot change from this
  repository. It stays worth doing and is recorded as a follow-up; this
  proposal makes it an ergonomic improvement rather than a correctness
  requirement.
- Un-suspending `cronworkflow-mctl-agents-implement` in `mctl-gitops`. It must
  stay suspended — see `design.md`, Alternatives.
- Any change to `run_implementer.py`'s selection, claim, lease or
  `--max-proposals` policy. The sweep submits the same operation with the same
  scoping DevLoopWorkflow already uses.
- Recovery out of `needs-triage` (#300) and adoption of proposal-less PRs
  (#334). Different states, different owners.
- Migrating the shepherd to Temporal (ADR-006 phase 6, #217).

## Open questions

- **Grace period value.** 20 minutes is chosen because it exceeds
  `dev_loop.APPROVE_STEP_TIMEOUT` (15 min), so a loop that flipped but has not
  yet submitted implement is covered even if the visibility query is stale.
  Proceeding with 20 minutes, env-tunable.
- **Per-tick submit cap.** 5, matching the issue poller's and the incident
  responder's per-run caps. The real concurrency bound is the admission queue's
  `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` (default 3); the cap only limits
  how many children one tick may mint after a long outage. Proceeding with 5,
  env-tunable.
- **Whether the schedule ships paused.** The incidents schedule was created
  paused pending a manual verification run (#179). Doing that here would
  reproduce the exact defect this proposal fixes — a sweeper that exists and is
  never called — so it ships enabled, with the per-tick cap and the admission
  queue as the safety bound, and pausing as the documented rollback.
- **Repeat sweeps of a proposal that keeps coming back `accepted`.** Today a
  failed implement run lands in `needs-triage` (#300) and a refusal hands the
  proposal back to `accepted`, so a pathological proposal could be re-swept
  every tick. Proceeding with per-candidate logging so the repetition is
  visible; a durable backoff is deferred to the lifecycle ownership store
  (ADR-010) rather than invented here.
