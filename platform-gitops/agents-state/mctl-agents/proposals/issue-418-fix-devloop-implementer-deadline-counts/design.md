# Design: issue-418-fix-devloop-implementer-deadline-counts

## Current state

**The Argo template (sibling repo, read at
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`).**
The workflow spec carries `activeDeadlineSeconds: 28800`, described in its own
comment as "a RUNAWAY GUARD, not the work budget", and records that it used to
be 7200 at spec level, which ran from submit and killed everything queued
behind the mutex. The work budget now sits on the `run-implementer` template
(`activeDeadlineSeconds: 7200`), which Argo applies to the pod, so it starts
when the pod starts - after `synchronization.mutex: mctl-agents-proposal-claims`
is acquired. `commit-and-push` carries its own `activeDeadlineSeconds: 900`,
`retryStrategy.limit: 3` and the separate `mctl-gitops-main-writes` mutex.
`assert-attempt` receives only `{{steps.implement.status}}` and
`{{steps.implement-fallback.status}}`, so "Failed because a pod ran and failed"
and "Failed because the node was killed while Pending on the mutex" reach it as
the same two strings. That template's own comment says the remaining work -
"narrowing the mutex to the discovery+claim critical section" - is tracked
separately. This issue is that tracking.

**Admission (this repo).** `orchestrator/temporal/constants.py` defines
`IMPLEMENTATION_TASK_QUEUE = "mctl-dev-loop-implement"`,
`IMPLEMENTATION_OPERATION = "mctl-agents-implement"`,
`DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES = 3` and
`implementation_max_concurrent_activities()` reading
`IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`. `orchestrator/temporal/worker.py`'s
`implementation_plan()` (role `implementation`, `ROLES` at line 360) passes that
number as `max_concurrent_activities`. `dev_loop._run_cwft` routes only the
implement operation there, behind `workflow.patched("implement-queue")`, with
`start_to_close_timeout` and deliberately no `schedule_to_start_timeout` - the
queue wait is the admission queue and must not be a failure. Production sets
`IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES: "3"` in
`services/admins/mctl-agents-worker-implement/values.yaml`. Nothing anywhere
compares that 3 with the Argo mutex's width of 1: the coupling exists only as
prose, in `dev_loop.py`'s comment above `PRESTART_REQUEUE_BACKOFF` and in
ADR-008 D7.

The consequence is the issue's gap 1, stated precisely: three activities are
admitted, three Argo workflows are created, one runs and two sit Pending on the
mutex. They no longer burn the 7200s pod budget, but they do burn the 28800s
spec guard, they hold two of three admission slots while achieving nothing, and
the queue-age metric the alerts in
`infra-components/observability/vm-rules/mctl-agents-worker-alerts.yaml` read is
blind to them, because from Temporal's side those activities are Started.

**Outcome classification (this repo).**
`orchestrator/temporal/implement_outcome.py` reads Argo's node graph and
answers `pre_start | execution | finalization | success`. `_pod_ran` is careful
in exactly the way this issue needs - it reads `hostNodeName`, an exit code or
a Succeeded phase, and explicitly not `startedAt`, "which Argo stamps at node
creation while the node may still be Pending on a mutex". `observe_implementer`
fails closed to unknown on a missing/renamed graph.
`orchestrator/temporal/activities/argo.py` carries the observation on
`WorkflowResult` (`implementer_ran`, `implementer_phase`,
`implementer_started_at`, `finalization_phase`) and publishes
`admitted -> submitted -> running` as heartbeat details.
`dev_loop._implement` requeues `pre_start` up to `MAX_PRESTART_REQUEUES = 3`
with `PRESTART_REQUEUE_BACKOFF = 2min`, and surfaces
`ImplementationNotStarted`. `ImplementExecutionState` (the `implement_execution`
query) carries `queued_at`, `prestart_requeues` and `outcome`.

But all of that is runtime state. The only durable write for a step is
`record_execution` in `orchestrator/temporal/activities/state.py`, whose POST
body is `{temporal_workflow_id, agent, environment, version, image_ref,
target_repo, argo_workflow_name, phase}` - `phase` being Argo's `Failed`, which
is precisely the word the issue says cannot distinguish the two cases. So
`mctl_list_agent_executions` shows six identical `Failed` rows for the
2026-09-19 burst, and the failed workflow's `onExit` posts an incident with
fingerprint `workflow_failed:implement:<svc>:<slug>` and `status: analyzing`,
which the incident responder turns into an auto-accepted proposal - recovery
acting on work that never started.

**Tests.** `tests/test_dev_loop_workflow.py::TestImplementationAdmission` has
`test_a_burst_of_approvals_is_admitted_n_at_a_time`, written as "the 2026-09-19
incident as a regression test (#395 DoD)". It asserts `n == 3` and that exactly
three submits run at once. Its submit fake has no Argo-side serialization at
all, so it is green today while production serialises those three at one. It
proves admission works; it cannot prove the admitted work can actually run.

**Cross-repo CI.** `.github/workflows/pr-validation.yml` checks
`mctlhq/mctl-gitops` out to `_gitops` and runs pytest with
`MCTL_GITOPS_ROOT=${{ github.workspace }}/_gitops/platform-gitops`.
`orchestrator/validate_manifest.py` resolves `GITOPS_ROOT` from that variable
(falling back to the sibling layout) and `_gitops_missing()` errors under CI
and warns locally. Note the trap: `tests/test_agent_inventory.py` hardcodes the
sibling path and therefore *skips* in CI - a new check must use the
`MCTL_GITOPS_ROOT`-aware resolver or it will silently not run where it matters.

## Proposed solution

Three changes, all inside `mctlhq/mctl-agents`, plus one precisely specified
companion change in mctl-gitops.

### 1. One width, declared once: effective admission capacity

Add to `orchestrator/temporal/constants.py`:

```python
ARGO_IMPLEMENT_WIDTH_ENV = "ARGO_IMPLEMENT_SERIALIZATION_WIDTH"
DEFAULT_ARGO_IMPLEMENT_WIDTH = 1          # the checked-in mutex is capacity 1

def argo_implement_serialization_width() -> int: ...
def effective_implementation_capacity() -> tuple[int, int, int]:
    """(configured N, declared Argo width, effective capacity = min of the two)."""
```

`worker.py::implementation_plan()` polls with the effective capacity and logs
one line naming all three numbers. `implementation_max_concurrent_activities()`
is left alone as the raw reader, so the env contract and every existing test of
it are unchanged.

Clamping, not refusing. A `SystemExit` on `N > width` is the louder option and
was considered (see Alternatives); it turns one bad value in a values file into
zero implementation capacity, which is a worse failure than the one being
fixed. Clamping can never admit work Argo cannot run, is visible in the startup
log, and the drift that produced it is caught at PR time by check 3 below
rather than at runtime. The width defaults to 1 and is read from the
environment, so the day the mutex becomes a ConfigMap-backed semaphore of 3,
the same gitops change that widens Argo sets
`ARGO_IMPLEMENT_SERIALIZATION_WIDTH: "3"` on the implement worker and the two
move in one commit.

The immediate production effect is that effective capacity becomes 1. That is
not a throughput reduction - throughput is already 1, enforced by the mutex.
What changes is where the other two wait: Scheduled in Temporal, where the wait
is free, unbounded, carries no Argo deadline and is exactly what the
schedule-to-start alerts already measure, instead of Pending in Argo against
the 28800s spec guard. That is acceptance criterion 1 of the issue.

### 2. A pre-start has a reason, and the reason is durable

`implement_outcome.py` gains:

```python
PreStartReason = Literal["queued", "unscheduled", "unknown"]
def pre_start_reason(status_block: dict[str, Any]) -> PreStartReason: ...
```

derived from the same node graph `observe_implementer` already reads: a
`run-implementer` node that never ran and whose `message` names a
synchronization lock (`Waiting for argo-workflows/Mutex/...`) or whose phase
stayed `Pending` is `queued`; a node that never ran with no such evidence is
`unscheduled`; an unreadable graph is `unknown`. The function is pure over the
status block, like everything else in that module, and follows the module's
existing fail-closed rule - it never invents `queued` from `startedAt`.

The reason rides on `WorkflowResult` (`pre_start_reason`), is carried into
`ImplementExecutionState`, is named in the `ImplementationNotStarted` message
together with the requeue count, and - the durable half - is added to
`ExecutionRecord` and the `/api/v1/agents/executions` body as `outcome` and
`pre_start_reason`. `_record` in `dev_loop.py` already tolerates a failing
record as best-effort; `record_execution` additionally retries once with the
pre-existing body shape if the extended one is rejected with a 4xx, so an
mctl-api that does not yet know the fields still gets its row. After this, the
six rows of a 2026-09-19 burst read `outcome=pre_start reason=queued` and a
genuine failure reads `outcome=execution` - the distinction the issue's third
acceptance bullet asks for, in the durable store
`mctl_list_agent_executions` reads.

Behind `workflow.patched("implement-prestart-reason")`, for the same reason
every other dev-loop behaviour change is: a loop mid-flight when this deploys
must keep scheduling the commands its history recorded.

### 3. The gitops invariants become a CI check here

New `tests/test_implement_cwft_contract.py`, resolving the CWFT through the
`MCTL_GITOPS_ROOT`-aware path (reuse `validate_manifest.GITOPS_CWFT_DIR`, do
not copy `test_agent_inventory.py`'s sibling-only constant), asserting on
`cwft-mctl-agents-implement.yaml`:

1. the `run-implementer` template declares its own `activeDeadlineSeconds` -
   the property that makes the budget pod-scoped, i.e. started at lock
   acquisition and not at node creation. This is issue acceptance bullet 2:
   the behaviour already holds, and this is what stops it regressing;
2. the workflow-spec `activeDeadlineSeconds` is at least
   `width x (run-implementer deadline + commit-and-push deadline x retry limit)`
   - today `1 x (7200 + 7200 + 2700) = 17100 <= 28800`, so the check codifies
   the sizing already chosen rather than demanding a change;
3. the declared serialization on `run-implementer` implies a width
   (`mutex` -> 1, `semaphore` -> its declared limit) that is at least
   `DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES`, failing with a message
   naming both files and both knobs.

Check 3 is the one that forces this proposal's own second half: with the mutex
at width 1, the checked-in default N must become 1, and production's values
file follows. Raising either one alone is a red PR in the repository whose CI
can see both - which is the only place in the system where that comparison is
possible at all.

### Companion change in mctl-gitops (specified here, not made here)

`assert-attempt` still cannot tell a queue-kill from a failed attempt, and the
direct `mctl_trigger_implementer` path never reaches Temporal, so the Argo side
needs its own signal. The shape that matches this template's existing idiom:
`run-implementer` writes a tiny start marker as its first action and declares it
as an `optional: true` output artifact at a literal, parameter-keyed S3 key
(`{{workflow.name}}/attempt-{{inputs.parameters.is-fallback}}.tgz`), exactly as
`changes` is declared today; `assert-attempt` mounts both keys as optional
inputs. A pod that never ran uploads nothing, so absent marker + non-Succeeded
status is "never started" - reported with its own message and its own exit code
so `notify-telegram`'s fingerprint becomes
`workflow_never_started:implement:<svc>:<slug>` and the incident responder stops
manufacturing proposals for work that was only queued. Tracked as a companion
mctl-gitops issue; check 1 above is what keeps this repository honest about the
half it depends on.

## Alternatives

**Move the mutex off `run-implementer` onto a short claim step (the issue's own
first suggestion).** Dropped for now, not rejected. The critical section the
mutex protects is discovery plus claim, and both happen inside
`run_implementer.py` in the same long-lived process (`_acquire_claim`,
`implement_one`) - there is no short Argo step to move the lock onto without
first splitting discovery into its own pod, which is a much larger change than
this issue's evidence justifies. ADR-010 already has the real replacement: a
server-side `ExecutionClaim` at `enforce` (mctl-api#337), after which the mutex
can widen into a semaphore and `ARGO_IMPLEMENT_SERIALIZATION_WIDTH` follows it
in the same commit. This design is deliberately the step that makes that
widening safe rather than the widening itself.

**Fail the worker (`SystemExit`) when N exceeds the width.** Matches
`constants._int_env`'s existing "a bad value is a configuration error" stance
and is maximally loud. Dropped: the implement worker is pinned to one replica
by gitops CI, so refusing to start means zero implementations until a human
notices, and a values-file typo would take the platform from "loses the tail of
a burst" to "implements nothing". Clamp plus a PR-time CI failure gets the same
protection without a self-inflicted outage. Recorded here because if the clamp
is ever observed hiding a real misconfiguration in production, this is the
upgrade path.

**Add a `schedule_to_start_timeout` to the implement submit so a long queue
fails fast instead of waiting.** Explicitly refused by ADR-008 D7 and by the
comment above `SDK_STEP_TIMEOUT`: it turns a capacity wait into a failure,
which is the shape of the very bug being fixed one layer down. Not taken.

**Put the pre-start marker in `.status.yaml` instead of the execution record.**
Rejected: ADR-008 and ADR-010 both keep git as durable *lifecycle* state with
no in-progress marker pushed mid-attempt, and a pre-start kill is by definition
a run that never reached `commit-and-push`, so it has no writer there at all.
The execution row is the durable surface that already exists for "what did this
step do".

## Platform impact

- **Migrations.** None. No schema, no data rewrite. `ExecutionRecord` gains two
  optional fields with empty defaults; the POST retries once on the old body if
  mctl-api refuses the new one. The workflow change is patch-guarded, so
  in-flight loops keep their recorded command stream.
- **Backward compatibility.** `implementation_max_concurrent_activities()` and
  `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` keep their meaning; only the
  worker's effective capacity is derived. A deployment that sets no
  `ARGO_IMPLEMENT_SERIALIZATION_WIDTH` gets width 1, which is what the
  checked-in template declares - fail-closed, and identical to today's real
  throughput.
- **Resource impact.** Two fewer idle Argo workflows per burst and two fewer
  occupied admission slots; Temporal holds the surplus as Scheduled activities,
  which cost nothing. Expect the schedule-to-start latency on
  `mctl-dev-loop-implement` to rise visibly - that is the queue becoming
  honest, not a regression, and the existing queue-age alerts in
  `mctl-agents-worker-alerts.yaml` already name
  `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` as the remedy. Their thresholds
  should be re-read once the first real burst lands.
- **Risk: a real capacity cut.** If the mutex were ever wider than 1 in
  production without the env var being set, the clamp would cut real
  throughput. Mitigated by check 3 (a PR that widens Argo without the matching
  worker setting fails CI here) and by the startup log line.
- **Risk: the CI check reads a template it cannot see.** A missing gitops
  checkout must error under CI and warn locally, following
  `validate_manifest._gitops_missing`; using `test_agent_inventory.py`'s
  sibling-only path instead would produce a check that skips in exactly the
  environment that gates the merge - the failure mode mctl-agents#277 already
  paid for once.
- **Risk: `pre_start_reason` over-claiming `queued`.** The classifier must
  never infer `queued` from `startedAt`, for the reason `_pod_ran` documents.
  Unknown stays `unknown`, and `unknown` changes no behaviour - the requeue is
  driven by `classify`, which is untouched.
- **Rollout.** Ordinary release of mctl-agents; no gitops change is required
  for it to take effect, because the width default matches the checked-in
  template. The companion gitops PR (start-marker artifact) and the mctl-api
  persistence of `outcome`/`pre_start_reason` are independently releasable in
  either order.
