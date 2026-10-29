# Design: issue-885-spike-session-aware-execution-affinity-f

## Current state

Everything below comes from reading the clone, unless it is marked "deployed".

**Executors and routing.**
- Temporal worker roles: `orchestrator/temporal/worker.py` builds one `Worker` per plan, and each plan
  sets only `task_queue`, `workflows`, `activities` and slot limits (lines ~815-830).
  `max_cached_workflows` is never set, so Temporal's default sticky workflow cache is on.
- Task queues: `orchestrator/temporal/constants.py` defines `TASK_QUEUE = "mctl-dev-loop"` (control),
  `EXECUTION_TASK_QUEUE = "mctl-dev-loop-exec"` (long `submit_and_wait` polls, ADR-008) and
  `IMPLEMENTATION_TASK_QUEUE = "mctl-dev-loop-implement"` (admission).
- Cross-queue hops: one DevLoopWorkflow already moves between queues and worker processes in a single
  run. Its workflow tasks run on control, and `_run_cwft` in
  `orchestrator/temporal/workflows/dev_loop.py` routes `submit_and_wait` onto exec or implement behind
  `workflow.patched(...)`.
- Where the work runs: the agent work itself runs in short-lived Argo pods (CWFTs such as
  `mctl-agents-investigate` and `mctl-agents-implement`), never inside the worker.

**Logical identities in use** (no new identifier is needed for any of them):
- Temporal workflow id `dev-loop-mctlhq-<repo>-<issue>`, which is idempotent on start
  (`orchestrator/temporal/start.py`), and its run id across `continue_as_new` hops (`dev_loop.py`
  ~4231, the `MergeWatchResume` carry at ~1553).
- WorkItem `wi_` and execution `we_` (`execution_id_for`, `_canonical_execution_id()`, and ADR 011
  `docs/adr/011-work-item-resume-contract.md`). Resume requests are deduplicated through the carried,
  sorted `seen_execution_ids`.
- Approval `aar_` (`orchestrator/action_approvals.py`), delivered by the `approve` signal.
  Refs are bounded by `_MAX_SIGNALLED_REFS`.
- Argo workflow name, kept as `activity.heartbeat(workflow_name, runtime)` in
  `orchestrator/temporal/activities/argo.py`. A retry reads it back from
  `activity.info().heartbeat_details` and resumes polling without re-submitting. The module docstring
  names one acknowledged gap: a crash between the POST and the first heartbeat. That gap does not
  depend on which worker runs the retry.
- `ExecutionContext.context_id` (`orchestrator/execution_identity.py`). It is authoritative in
  mctl-api and is never an authorization input.
- Lifecycle ownership rows (ADR 010, `orchestrator/lifecycle/`). These are server-side, fenced by
  epoch, and keyed by workflow id.
- #757 attention: the `session_or_workitem_ref` / watched-resource key plus one stored digest per
  resource (`docs/spikes/757-duet-sessions.md` Q5/Q6, `docs/spikes/757/attention.py`).

**Process-local state found so far** (the candidate implicit same-executor dependencies):
1. `_blob_cache`: `orchestrator/temporal/activities/gitops_state.py`, an `OrderedDict` bounded by
   `_BLOB_CACHE_MAX = 4096` and keyed by blob SHA. It is content-addressed, so a miss on another
   worker only costs a re-read. Expected to be safe.
2. Implementation admission: `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` is a per-process slot limit,
   so the effective capacity is replicas × N. It is correct only at one replica. Owner: `constants.py`
   / `worker.py`, plus mctl-gitops `services/admins/mctl-agents-worker-implement/values.yaml` and
   `scripts/validate-implement-worker-singleton.py`. The long-term fix belongs to ADR-010 /
   mctl-api#337. This is a capacity invariant, not routing affinity.
3. Usage ledger: `_WORKER` in `orchestrator/usage_ledger.py` is an in-process queue drained by a
   thread and flushed `atexit`. A hard kill may drop records that have not been delivered.
   Durability question, still to be measured.
4. Temporal sticky cache: an optimisation only. On a cache miss the server replays history on any
   worker. Workflow code is deterministic and replay-tested (`tests/test_workflow_replay.py`,
   `tests/replay_scenarios.py`).
5. claude-remote operator session (#757 path): transcript in emptyDir, persisted to R2 by a sidecar,
   with managed session rotation, and a single replica. Its continuity is pod-local by design and
   belongs to #760.

**Existing test leverage.** `tests/temporal_harness.py` already runs a control worker plus execution
and implementation workers, mirroring `worker_plans("all")`. Workflow tests drive DevLoopWorkflow
against fake activities (`tests/test_dev_loop_workflow.py`, `tests/test_execution_request_resume.py`).
Spike conventions follow #757 and #881: a report at `docs/spikes/<n>-<slug>.md`, fixtures under
`docs/spikes/<n>/` or `experiments/`, and a collector `tests/test_spike_<n>_*.py` that runs the
fixture in the default pytest collection.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `replicaCount: 1`, command
  `orchestrator.temporal.worker --role control`, `TEMPORAL_NAMESPACE: mctl-agents`.
- `services/admins/mctl-agents-worker-exec/values.yaml`: `replicaCount: 1`, `--role execution`.
- `services/admins/mctl-agents-worker-implement/values.yaml`: `replicaCount: 1`, documented as an
  architectural invariant; `Recreate` strategy; `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES: "3"`.
- `services/labs/claude-remote/values.yaml`: `replicaCount: 0`, single-replica `Recreate`, Valkey
  events URL, workspace in emptyDir persisted to R2.
- `mctl_get_service_status(admins, mctl-agents-worker)`: Healthy, Synced, image 1.110.0.
- Not observed: live Temporal sticky-queue hit rates and worker identities per task. No read-only tool
  exposes them. Recorded under Open questions in requirements.md as unknown.

## Proposed solution

A research-only spike in three parts. No `orchestrator/` module changes, no gitops change.

**1. Current-state map** (`docs/spikes/885-execution-affinity.md`): a table of identity -> durable
state -> routing for the two tested paths, plus the dependency list above, each item with a verdict
(safe / gap / unknown) and an owner.

**2. Two-executor fixture** (`docs/spikes/885/`, collected by
`tests/test_spike_885_affinity.py`):

- Environment: the Temporal test server (`WorkflowEnvironment`, as the existing workflow tests use).
- Two instances: two `Worker`s, A and B, on the same queues, each with a distinct `identity`.
  Both use `max_cached_workflows=0`, so no sticky cache exists and every workflow task can land on
  either worker. Activity fakes record `activity.info()` worker identity, attempt and
  heartbeat details into a shared, append-only trace list.
- Forcing instance changes: the fixture shuts A down at chosen points. It also uses a per-instance
  fake that raises once on instance A after heartbeating. Together these make consecutive steps land
  on B.
- DevLoop path, scenario D1: investigate `submit_and_wait` heartbeats a workflow name on A. The
  attempt fails, and attempt 2 on B must resume with zero additional submits.
- DevLoop path, scenario D2: the workflow parks at approval with A as the last worker. A is stopped,
  the `approve` signal arrives, and B replays and implements.
- DevLoop path, scenario D3: a merge watch on A hops through `continue_as_new`, and B continues with
  `MergeWatchResume` and `seen_execution_ids` intact. A duplicate resume request is rejected on B
  exactly as it would be on A.
- Baseline: each scenario also runs single-worker (sticky cache on), and outcomes, activity call
  counts and the final `WorkContextState` are compared field by field.
- Agent/session path, scenario S1: `docs/spikes/757/attention.py` `decide_wake_cycle` runs on two
  "instances" that share a digest store, then on two instances with separate per-instance stores.
  The report records which variant is correct. The expected result is that only the shared store is
  correct, which the existing durable digest already gives.
- Process-local probes: P1 runs `_blob_cache` cold on B and compares results. P2 hard-kills a
  subprocess before `usage_ledger.flush` and counts lost records. P3 is the implementation admission
  check: two implement workers at N=3 record that up to 6 are admitted, documenting the singleton
  invariant. P3 changes nothing.
- Output: each run emits JSON lines (`scenario`, `instances_seen`, `result` in
  `pass|fail|unknown`, `submits`, `diff`). A small `collect.py` (run as `python -I`) builds a
  scorecard. Any step with no recorded instance identity is `unknown`.

**3. Decision.** The quick-win rule from the issue applies. If D1-D3 and S1 (shared store) are correct
across instances, the outcome is `NO_AFFINITY_NEEDED`. P2 and P3 then become focused follow-up issues,
filed only if they are proven, and only as durability or capacity work. If a correctness gap is
proven, the fixture repeats with the smallest binding built on an existing key: the `we_`
`execution_id` or the workflow id. The report then states key, owner, TTL (equal to the lifetime of
the execution, released when the execution reaches a terminal state), failover (rebuilt from durable
state on executor loss, never authoritative) and integration point. It also states whether the result
is `ADD_EXECUTION_AFFINITY_KEY` or `ADD_SESSION_ROUTING_BINDING`.

## Alternatives

- **Analysis only, no fixture.** The code already suggests every resume key is durable. Dropped
  because the issue explicitly requires a forced cross-executor experiment, and unknown is not
  success.
- **A real two-replica deployment in the cluster.** This tests the real network, but it changes
  production routing, violates the implement-worker singleton invariant and the spike's no-production
  rule, and costs model quota. Dropped. The Temporal test server with sticky caching off exercises
  the same server-side replay semantics.
- **Sticky task queues or pod affinity as the fix.** Temporal sticky queues already exist and are
  explicitly not a correctness mechanism. Pod affinity is a non-goal in the issue. Dropped.

## Platform impact

- No migration, no runtime change, no change to deployed configuration. New files only, under
  `docs/spikes/885*` and `tests/test_spike_885_affinity.py`.
- CI cost: a few extra seconds of Temporal test server time. The fixture must use the time-skipping
  environment and fakes, never real Argo, GitHub or model calls.
- Risk: a fixture that is flaky because of worker shutdown timing. Mitigation: deterministic forcing
  through per-instance fakes and explicit `await worker.shutdown()`, never sleeps.
- Risk: the fixture drifts from production worker plans. Mitigation: build both instances from
  `tests/temporal_harness.py` / `worker_plans` rather than hand-listing activities.
- Risk: the spike is read as authorising affinity. Mitigation: the report states that any binding is
  advisory routing state, never an identity, policy or approval input.
