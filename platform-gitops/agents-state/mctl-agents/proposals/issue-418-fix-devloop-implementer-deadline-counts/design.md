# Design: issue-418-fix-devloop-implementer-deadline-counts

## Current state

**Where the deadline lives.** The implement step graph is a
ClusterWorkflowTemplate in the *other* repository:
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`
in mctl-gitops. This repo names it in
`agents/_manifests/implementer/agent.yaml`
(`execution.sandbox.clusterWorkflowTemplate: mctl-agents-implement`) and reads
the CWFT directory in CI via
`orchestrator/validate_manifest.py::GITOPS_CWFT_DIR`
(`GITOPS_ROOT / "argo-workflows" / "cluster-templates"`), where
`_check_cluster_workflow_template` already opens every `cwft-*.yaml` and
`yaml.safe_load`s it. `GITOPS_ROOT` resolves from `MCTL_GITOPS_ROOT`, which
`.github/workflows/pr-validation.yml` sets to `_gitops/platform-gitops` after
checking mctl-gitops out (mctl-agents#277). So mctl-agents CI *can* read and
assert on the CWFT today; nothing currently asserts anything about its
`synchronization` or `activeDeadlineSeconds`.

The step names are already pinned in this repo by
`orchestrator/temporal/implement_outcome.py`:
`IMPLEMENTER_TEMPLATE = "run-implementer"` and
`FINALIZATION_TEMPLATES = {"commit-and-push", "assert-attempt"}`.

**Where admission lives.** ADR-008 D7 added a third Temporal queue.
`orchestrator/temporal/constants.py` declares
`IMPLEMENTATION_TASK_QUEUE = "mctl-dev-loop-implement"`,
`IMPLEMENTATION_OPERATION = "mctl-agents-implement"`, and reads N from
`IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` via
`implementation_max_concurrent_activities()`, defaulting to 3.
`orchestrator/temporal/worker.py::worker_plans` builds the `implementation`
plan lazily so a bad N is a startup refusal only for the role that serves that
queue. `orchestrator/temporal/workflows/dev_loop.py::_run_cwft` routes the
implement submit there behind `workflow.patched("implement-queue")`, with no
`schedule_to_start_timeout` — the queue wait *is* the admission queue.

The coupling between N and the Argo mutex width exists only as prose. The
comment above `PRESTART_REQUEUE_BACKOFF` in `dev_loop.py` says it plainly:
"if the CWFT's `synchronization` mutex is narrower than N, the surplus queues
inside Argo against its own deadline and comes back pre_start ... ADR-008 D7
records that the gitops mutex is expected to be at least N." Nothing checks it.
N default 3 against mutex width 1 means two of every three admitted submits
still burn deadline in Argo — the exact 2026-09-19 shape, just smaller.

**Where the classification lives.** `implement_outcome.py` (#395) reads Argo's
node graph and answers `success | pre_start | execution | finalization`.
`_pod_ran` deliberately refuses `startedAt` as evidence ("Argo stamps it when
the node is created, which for a node blocked on a synchronization lock is
while it is Pending with no pod at all"), and an unreadable graph is `None`,
never `False`. `activities/argo.py::submit_and_wait` folds observations across
polls through `_merge_observations` (`ran=True` is sticky, unknown never
outranks a definite answer) and publishes `admitted -> submitted -> running`
as a heartbeat projection (#389). `dev_loop.py::_implement` requeues
`pre_start` up to `MAX_PRESTART_REQUEUES` behind `workflow.patched("implement-outcome")`,
and otherwise raises a typed `ApplicationError` (`ImplementationNotStarted` /
`ImplementationFailed` / `ImplementationFinalizationFailed`).

What is missing is the *reason*. `ImplementerObservation` has no field for it,
so "killed while queued on the mutex" and "Argo accepted the workflow and never
scheduled the pod" collapse into one `pre_start`. The durable record —
`activities/state.py::ExecutionRecord`, posted to
`POST /api/v1/agents/executions` — carries only `phase` ("Succeeded | Failed |
Error"), so neither the outcome class nor the reason survives at all.

**Per-proposal safety does not come from this mutex.** `mctl-agents-proposal-claims`
is a single global capacity-1 lock, not a per-proposal key. Duplicate-attempt
safety comes from the deterministic `feat/agents-<slug>` branch and canonical-PR
reconciliation in `orchestrator/run_implementer.py`, plus the ADR-010 phase-2
`ExecutionClaim` and its `--force-with-lease=<branch>:<sha>` push fence
(`_push_followup`, pinned by `tests/test_run_implementer_claims.py`). That is
what makes moving the mutex off the timed step safe rather than reckless.

## Proposed solution

Four changes, three in this repository, one cross-repo, in a fail-closed order.
The first two stop the bleeding without needing the gitops PR to land.

### 1. Bind admission width to the mutex, as code, in `constants.py`

Mirror the three facts about the CWFT's lock that admission depends on, next to
N, and derive a ceiling from them:

```python
ARGO_IMPLEMENT_MUTEX_NAME = "mctl-agents-proposal-claims"
ARGO_IMPLEMENT_MUTEX_TEMPLATE = "run-implementer"   # flips to "commit-and-push"
ARGO_IMPLEMENT_MUTEX_WIDTH = 1

def argo_admission_width() -> int | None:
    """None once the lock no longer guards timed work."""
    if ARGO_IMPLEMENT_MUTEX_TEMPLATE == implement_outcome.IMPLEMENTER_TEMPLATE:
        return ARGO_IMPLEMENT_MUTEX_WIDTH
    return None
```

`implementation_max_concurrent_activities()` then clamps — or rather refuses,
because a silent clamp is a capacity number that lies:

```python
n = _int_env(IMPLEMENTATION_CAPACITY_ENV, DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES)
ceiling = argo_admission_width()
if ceiling is not None and n > ceiling:
    raise SystemExit(
        f"{IMPLEMENTATION_CAPACITY_ENV}={n} exceeds the Argo mutex width "
        f"{ARGO_IMPLEMENT_MUTEX_NAME}={ceiling}, which still guards "
        f"{ARGO_IMPLEMENT_MUTEX_TEMPLATE} — the surplus would queue inside Argo "
        f"against its own activeDeadlineSeconds (mctl-agents#418)"
    )
```

`SystemExit` matches `_int_env`'s existing contract and `worker.py`'s lazy
`implementation_plan()` keeps the refusal confined to the `implementation`
role — a control or execution worker with a stray env var stays healthy.

`DEFAULT_IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` drops from 3 to
`ARGO_IMPLEMENT_MUTEX_WIDTH` (1) while the mirror says `run-implementer`, and is
restored to 3 in the same one-line commit that flips the mirror to
`commit-and-push` after the gitops PR lands. The two numbers now move together
because they are read from one place.

### 2. Make the mirror non-decorative: a CI check against the real CWFT

New `check_implement_admission_is_safe()` in `orchestrator/validate_manifest.py`,
beside `_check_cluster_workflow_template`, reusing `GITOPS_CWFT_DIR` and
`_gitops_missing` (error under `CI`, printed warning locally). It loads
`cwft-mctl-agents-implement.yaml`, walks `spec.templates`, and reports an error
when any of these disagree:

- the template actually carrying `synchronization.mutex.name ==
  ARGO_IMPLEMENT_MUTEX_NAME` (also accepting Argo 3.6's `synchronization.mutexes[]`
  list form) is not `ARGO_IMPLEMENT_MUTEX_TEMPLATE`;
- the mutex is absent from the file entirely while the mirror still names a
  template for it;
- the guarded template carries an `activeDeadlineSeconds` above a small budget
  (`MAX_LOCKED_STEP_DEADLINE_SECONDS`, proposed 1800) — that is the #418 shape
  restated structurally: a long deadline and a lock on the same node;
- `run-implementer` has no `activeDeadlineSeconds` at all, which would mean this
  check is asserting against a file that has been restructured underneath it.

Wired into `validate()`/`main()` and into `tests/test_manifest.py` with the exact
CI-conditional skip that `test_catalog_profiles_match_builders` documents — an
unconditional `pytest.skip` would intercept `_gitops_missing` and turn a failed
checkout into a green build.

### 3. Record *why* a run never started

`implement_outcome.py`:

```python
PreStartReason = Literal["lock_wait", "unscheduled", "unknown"]
```

- `ImplementerObservation` gains `pre_start_reason: PreStartReason | None`.
- A new `_lock_waiting(node)` reads the two marks Argo leaves on a node blocked
  on a lock: `node["synchronizationStatus"]["waiting"]` (the structured form),
  and a `node["message"]` matching `Mutex/` or `Lock status:` — the message shape
  the issue quotes verbatim ("Waiting for argo-workflows/Mutex/mctl-agents-proposal-claims.
  Lock status: 0/1").
- `observe_implementer` sets the reason only when `ran` is definitely `False`:
  `lock_wait` if any implementer node shows a lock mark, else `unscheduled`. An
  unreadable or empty node graph leaves it `None`, which `pre_start_reason()`
  renders as `unknown` — never `unscheduled`, because absence of evidence about
  the cluster is not evidence about the cluster.

`activities/argo.py`: `_merge_observations` makes `lock_wait` sticky the same way
`ran=True` is sticky. This matters because Argo's terminal status can drop the
node message: the poll that *sees* "Lock status: 0/1" is mid-flight, and the poll
that sees `Failed` is the one the result is built from. `WorkflowResult` gains
`pre_start_reason: str | None = None`, additive with a default exactly like the
#395 fields, so an in-flight activity's older payload still deserializes.

`workflows/dev_loop.py`: `ImplementExecutionState` gains `pre_start_reason`, so
the `implement_execution` query (#389) shows it live; the requeue log line and the
`ImplementationNotStarted` message both name it. The error *type* stays
`ImplementationNotStarted` — recovery keys on the type, and splitting it would be
a breaking change to a contract this proposal does not need to touch.

`activities/state.py`: `ExecutionRecord` gains `outcome: str = ""` and
`pre_start_reason: str = ""`, posted only when non-empty. This is the durable half
of the acceptance criterion; `_record` is already best-effort, so an mctl-api that
rejects unknown fields costs an audit field, not a loop.

### 4. Cross-repo: move the mutex in mctl-gitops

A mctl-gitops PR moves `synchronization.mutex: mctl-agents-proposal-claims` off
`run-implementer` and onto `commit-and-push`, which already carries
`mctl-gitops-main-writes`. Waiting then happens on a step measured in seconds,
outside the implementer's two-hour budget, and the direct
`mctl_trigger_implementer` path keeps the serialization ADR-008 D7 says it needs.
Once it merges, the one-line mirror flip in `constants.py` plus restoring N to 3
lands here, and the CI check from part 2 is what proves the two repos agree.

### Order (fail-closed)

1. This repo: parts 1-3. N becomes 1; the burst is safe immediately because the
   surplus stays `Scheduled` in Temporal with no Argo workflow created at all.
2. mctl-gitops: part 4. CI in *this* repo goes red the moment it merges, because
   the mirror still says `run-implementer` — which is the intended signal, not a
   surprise.
3. This repo: flip the mirror, restore N to 3. CI green again.

Each step is releasable alone and step 1 is the whole fix for the reported
failure; steps 2-3 are what let capacity rise above 1.

## Alternatives

**Add `schedule_to_start_timeout` to the implement submit.** Rejected, and ADR-008
D7 rejects it by name: "A schedule-to-start timeout would turn a capacity wait
into a failure, which is the shape of the bug being fixed one layer earlier." It
would convert queue depth into red workflows.

**Have `submit_and_wait` detect the lock wait and terminate/resubmit the Argo
workflow.** Rejected. It puts the orchestrator in the business of killing runs it
cannot prove are idle — a workflow that acquires the lock between the poll and the
terminate is a real implementer deleted mid-work — and it treats the symptom while
leaving the deadline semantics wrong. Detection is still built (part 3), but only
to *record*, never to act.

**Read the mutex width live from gitops at worker startup instead of mirroring
it.** Rejected: the worker deployment has no gitops checkout (only the implement
CWFT mounts `/workdir/mctl-gitops`, see `orchestrator/run_implementer.py`'s
`AGENTS_STATE` note), so this would add a network read to a startup path and fail
the worker on a gitops outage. The mirror-plus-CI-check pattern is already how
`orchestrator/resolver.py` handles the identical cross-repo problem for
`validate-agent-platform.py`'s `COMPAT_RE`.

**Raise `activeDeadlineSeconds` well above 7200 so queued runs survive.**
Rejected: it makes the window larger, not correct, and it makes a genuinely wedged
implementer hold a worker slot and a lock for longer. The issue is the clock's
start point, not its length.

**Remove `mctl-agents-proposal-claims` outright now that Temporal admits.**
Rejected for this slice: ADR-008 D7 and ADR-010's 2026-09-19 amendment both record
that it stays until the server-side claim is at `enforce` (mctl-api#337), because
`mctl_trigger_implementer` submits straight to Argo with no admission at all.

## Platform impact

**Migrations.** None in data. `WorkflowResult`, `ImplementerObservation`,
`ImplementExecutionState` and `ExecutionRecord` all gain optional fields with
defaults, so an in-flight activity result recorded by an older worker still
deserializes as "unknown" — the same additive shape #395 used.

**Backward compatibility / replay.** No new `workflow.patched()` marker is
proposed: `_implement` schedules the same commands in the same order, and the
added fields are activity *payload*, not command shape. That claim must be
verified, not asserted — `tests/test_workflow_replay.py` replays recorded
pre-patch histories and is the check that decides it (task T7). If it goes red,
the `_record` payload change gets gated behind
`workflow.patched("implement-prestart-reason")` and the pre-patch fixtures stay
un-regenerated, per `tests/replay_scenarios.py`'s stated rule.

**Resource impact.** Capacity drops from a nominal 3 to a real 1 until the gitops
PR lands. That is not a throughput loss: the real capacity behind a width-1 mutex
was already 1, with the surplus converting into deadline-killed runs and pre-start
requeues. Queue depth moves onto `mctl-dev-loop-implement`'s schedule-to-start
latency, which is exactly the metric ADR-008 D5/D7 say to read capacity against
and which the SDK exporter already publishes on `METRICS_PORT`.

**Risks and mitigations.**

- *A stricter startup refusal turns a bad env var into a crash-looping
  implementation worker.* Mitigated by `worker.py`'s existing lazy
  `implementation_plan()` — control and execution roles are untouched — and by the
  error message naming both numbers and the issue. Break-glass is a values edit,
  the same rollback ADR-008 already documents.
- *The CI check asserts against a file in another repo that can be restructured.*
  Mitigated by failing loudly on every disagreement, including "the mutex is gone
  entirely" and "`run-implementer` has no deadline", rather than treating a
  no-match as a pass. This is the silent-no-op failure `_gitops_missing` and
  `test_a_missing_gitops_checkout_fails_under_ci` exist to prevent, and it is the
  one to get right here.
- *Lock-wait detection depends on an Argo message string.* Mitigated by reading
  the structured `synchronizationStatus` first and treating the message only as a
  fallback, and by the reason being advisory: an undetected `lock_wait` degrades
  to `unknown`, which changes nothing about `classify`'s verdict or the requeue.
- *Moving the mutex to `commit-and-push` allows two implementers to execute
  concurrently.* That is the intent, and it is bounded by N. Per-proposal safety
  is unchanged: deterministic branch, canonical-PR reconciliation, and the
  ADR-010 `ExecutionClaim` fence at the push site.
- *The direct `mctl_trigger_implementer` path stays outside admission.* Unchanged
  by this proposal, and strictly improved: after part 4 an operator-driven burst
  queues on a seconds-long step instead of burning two-hour budgets.

**Documentation.** ADR-008 D7 gains an in-place amendment blockquote
(`> **Amended <date> (mctlhq/mctl-agents#418).**`), following the amendment
convention D4/D7 and ADR-010's Non-goals already use. No new ADR: this sharpens
D7's existing decision rather than replacing it.
