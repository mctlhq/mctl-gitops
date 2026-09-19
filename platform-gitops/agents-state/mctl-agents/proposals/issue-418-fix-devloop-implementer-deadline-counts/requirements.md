# Stop counting mutex wait against the implementer deadline

## Context

`run-implementer` in `cwft-mctl-agents-implement.yaml` (mctl-gitops) carries
`activeDeadlineSeconds: 7200` and is guarded by the capacity-1 Argo mutex
`mctl-agents-proposal-claims`. Argo starts the deadline clock when the node is
**created**, not when the lock is **acquired**, so every implementer queued behind
the lock spends its whole two-hour budget waiting and is killed having executed
nothing. On 2026-09-19, six implementers created between 00:12Z and 00:31Z each
died at creation time plus ~2h00m; the first one held the mutex for the entire
window. The tail of that burst got between zero and nineteen minutes of real work
out of a two-hour allowance.

ADR-008 D7 (`docs/adr/008-worker-queue-split-and-capacity.md`) already moved
admission into Temporal: the implement submit routes to `mctl-dev-loop-implement`,
whose slot limit N is the implementation capacity, and an activity with no free
slot stays `Scheduled` with no Argo workflow created. That is the right shape, and
it is incomplete in exactly two places the issue names. First, N and the Argo mutex
width are set independently — N defaults to 3
(`DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` in
`orchestrator/temporal/constants.py`) while the mutex admits 1, so two of every
three admitted submits still burn deadline inside Argo. ADR-008 D7 states the
relation as an expectation ("the gitops mutex is expected to be at least N",
mirrored in the comment above `PRESTART_REQUEUE_BACKOFF` in
`orchestrator/temporal/workflows/dev_loop.py`) and nothing enforces it. Second,
`implement_outcome.py` classifies a queued kill as `pre_start` but does not say
**why** it never started — "killed while queued on a lock" and "accepted by Argo
and never scheduled" are recorded identically, so downstream recovery cannot tell
a capacity problem from a cluster problem.

## User stories

- AS the dev-loop orchestrator I WANT an implementer's two-hour execution budget to
  begin when it actually starts working SO THAT a burst of approvals cannot kill its
  own tail before any of it runs.
- AS a platform operator I WANT the Temporal admission width and the Argo mutex width
  to be impossible to set independently SO THAT raising N cannot silently reintroduce
  the 2026-09-19 failure.
- AS the recovery plane (#353, mctl-api#294) I WANT a deadline kill suffered while
  queued on a lock recorded with a distinct reason SO THAT I do not retry work that
  never started as though the agent had tried and produced nothing.
- AS a reviewer of this repository I WANT a regression test that replays the
  00:12-00:31Z burst shape SO THAT a future change to capacity, routing or the CWFT
  cannot re-open the hole without CI going red.

## Acceptance criteria (EARS)

- WHEN a burst of N approvals well past the Argo mutex width is approved, THE SYSTEM
  SHALL complete every item, holding the surplus as `Scheduled` activities on
  `mctl-dev-loop-implement` rather than as Argo workflows burning
  `activeDeadlineSeconds`.
- WHILE the `mctl-agents-proposal-claims` mutex guards the long-timed
  `run-implementer` template, THE SYSTEM SHALL refuse to start an `implementation`
  role worker whose configured N exceeds the mirrored mutex width, with a startup
  error naming both numbers.
- WHEN the mutex guards only a short step (`commit-and-push`) that does not carry the
  implementer's execution budget, THE SYSTEM SHALL allow N above the mutex width,
  because lock waiting then happens outside the timed work.
- IF the mirrored declaration in `orchestrator/temporal/constants.py`
  (`ARGO_IMPLEMENT_MUTEX_NAME`, `ARGO_IMPLEMENT_MUTEX_TEMPLATE`,
  `ARGO_IMPLEMENT_MUTEX_WIDTH`) disagrees with
  `cwft-mctl-agents-implement.yaml` in the mctl-gitops checkout, THEN THE SYSTEM
  SHALL fail the mctl-agents PR-validation run with a message naming the file and
  both values.
- IF the mctl-gitops checkout is absent while running under CI, THEN THE SYSTEM SHALL
  report that as an error, not a skip, following
  `orchestrator/validate_manifest.py::_gitops_missing`.
- WHEN `submit_and_wait` observes an implement node waiting on a synchronization
  lock (Argo's `synchronizationStatus` on the node, or a node message of the
  "Waiting for argo-workflows/Mutex/... Lock status: 0/1" shape), THE SYSTEM SHALL
  remember that observation across polls, so a terminal poll that has lost the
  message still reports it.
- WHEN an implement submit is classified `pre_start`, THE SYSTEM SHALL carry a
  `pre_start_reason` of `lock_wait`, `unscheduled` or `unknown` into the workflow
  result, into the `implement_execution` query state, into the durable execution
  record, and into the `ImplementationNotStarted` error message.
- WHILE `pre_start_reason` is unreadable, THE SYSTEM SHALL report `unknown` and MUST
  NOT report `unscheduled` — an unreadable node graph is not evidence about the
  cluster.
- WHEN an implementer pod is observed to have executed, THE SYSTEM SHALL NOT report
  any `pre_start_reason`, preserving today's rule that `startedAt` on a node Pending
  on a mutex is never the attempt's start (`implement_outcome._pod_ran`).
- WHEN the regression suite replays the 2026-09-19 00:12-00:31Z burst against a fake
  Argo that enforces mutex width 1, THE SYSTEM SHALL assert that no run is killed
  before it has executed and that every loop reaches a successful implement.

## Out of scope

- Removing `mctl-agents-proposal-claims` entirely. ADR-008 D7 and ADR-010's Non-goals
  both record that it stays until the server-side claim is at `enforce`
  (mctl-api#337), because the admin-only direct `mctl_trigger_implementer` bypasses
  Temporal admission.
- Making the direct `mctl_trigger_implementer` operation consult admission. That is an
  mctl-api change (operations registry), tracked separately; this proposal only makes
  that path stop being self-destructive by taking the lock wait off the timed step.
- Per-service capacity `M` and any distributed semaphore (ADR-010 / mctl-api#337).
- Adding `schedule_to_start_timeout` to the implement submit — ADR-008 D7 explicitly
  refuses it, and it would turn a capacity wait back into a failure.
- Lowering `EXECUTION_MAX_CONCURRENT_ACTIVITIES` from 40.
- Changing `MAX_PRESTART_REQUEUES` or the requeue mechanism itself.

## Open questions

- Does `commit-and-push` in `cwft-mctl-agents-implement.yaml` genuinely need
  `mctl-agents-proposal-claims` at all? Per-proposal duplicate-attempt safety already
  comes from the deterministic `feat/agents-<slug>` branch, canonical-PR
  reconciliation, and the ADR-010 `ExecutionClaim` push fence
  (`orchestrator/run_implementer.py::_push_followup` with
  `--force-with-lease=<branch>:<sha>`, pinned by
  `tests/test_run_implementer_claims.py`). Proceeding with the issue's smallest
  option — move the mutex onto `commit-and-push` alongside the existing
  `mctl-gitops-main-writes` — rather than dropping it, which would be a larger
  claim to defend in the same change.
- Does mctl-api's `POST /api/v1/agents/executions` tolerate the two additional fields
  (`outcome`, `pre_start_reason`)? Not answerable from this repository. Proceeding by
  sending them only when non-empty; `_record` in `dev_loop.py` is already best-effort
  and swallows a failed write, so the worst case is a missing audit field, not a
  broken loop. Task 8 verifies against mctl-api and files the follow-up if needed.
- Should the mirrored mutex width be read live from gitops at worker startup instead
  of mirrored in `constants.py`? Proceeding with the mirror, following the precedent
  in `orchestrator/resolver.py` (its `COMPAT_RE` / `parse_version` mirror of
  mctl-gitops' `validate-agent-platform.py`, pinned by a test that loads that script)
  — the worker pod has no gitops checkout, only the implement CWFT does.
- Should a `lock_wait` requeue back off longer than `PRESTART_REQUEUE_BACKOFF`
  (2 minutes)? With N bound to the mutex width a `lock_wait` should become rare;
  keeping one backoff constant until the metric says otherwise.
