# Design: issue-505-feat-usage-devloopworkflow-passes-tempor

## Current state

### The one submit funnel

`DevLoopWorkflow` makes every CWFT submit through one helper,
`_run_cwft(operation, params, *, step_timeout=...)` at
`orchestrator/temporal/workflows/dev_loop.py:949-1001`. It takes an opaque
`params: dict[str, str]`, wraps it in
`SubmitAndWaitInput(operation=operation, params=params)`
(`orchestrator/temporal/activities/argo.py:68`) and schedules the
`submit_and_wait` activity on one of three queues depending on
`workflow.patched("implement-queue")` and `workflow.patched("exec-queue")`.
It never inspects or augments `params`.

There are five call sites:

| line | operation | params variable |
| --- | --- | --- |
| 2648 | `mctl-agents-investigate` | `investigate_params` |
| 2747 | `mctl-agents-investigate` (human-input continuation) | `continuation_params` |
| 2936 | `mctl-agents-approve` | inline |
| 3366 | `IMPLEMENTATION_OPERATION` (`mctl-agents-implement`) | `params`, passed into `_implement` |
| 3694 | `mctl-agents-shepherd` | `tick_params` |

### What investigate already does

`dev_loop.py:2615-2645`:

```python
investigate_params = {"issue_url": issue.issue_url}
if investigator_release and investigator_release.image_ref:
    investigate_params["agent_image"] = investigator_release.image_ref
    investigate_params["agent_version"] = f"issue-investigator@{investigator_release.version}"
...
loop_info = workflow.info()
investigate_params["temporal_workflow_id"] = loop_info.workflow_id
investigate_params["temporal_run_id"] = loop_info.run_id
if dispatched is not None:
    investigate_params["work_item_id"] = self._work_item_id
    investigate_params["execution_id"] = dispatched.execution_id
    investigate_params["execution_request_id"] = str(issue.execution_request_id)
```

The comment above it is the precedent that governs this issue:

> Inert until mctl-api declares them (mctl-api#372 strips undeclared params).
> Replay-safe without a marker: activity input is not compared on replay
> (tests/test_workflow_replay.py, "an extra argument added to an existing
> activity"), and `workflow.info()` schedules no command.

### What implement and shepherd do

`dev_loop.py:2991-2996`, submitted via `self._implement(...)` at
`dev_loop.py:3017`:

```python
implement_params: dict[str, str] = {"service": target_repo}
if slug:
    implement_params["slug"] = slug
if implementer_release and implementer_release.image_ref:
    implement_params["agent_image"] = implementer_release.image_ref
    implement_params["agent_version"] = f"implementer@{implementer_release.version}"
```

`dev_loop.py:3690-3694`, inside `_shepherd_tick(self, service, slug)`:

```python
shepherd_release = _require_release("shepherd", await _resolve("shepherd"))
tick_params = {"service": service, "slug": slug}
if shepherd_release and shepherd_release.image_ref:
    tick_params["agent_image"] = shepherd_release.image_ref
    tick_params["agent_version"] = f"shepherd@{shepherd_release.version}"
tick_result = await _run_cwft("mctl-agents-shepherd", tick_params)
```

Neither carries the loop's identity. `implement_params` is built once and
handed to `_implement`, whose `while True` requeue loop (`dev_loop.py:3359-3366`)
resubmits the *same* dict on a `pre_start` outcome, up to `MAX_PRESTART_REQUEUES`
(`dev_loop.py:178`), so any correlation added at construction time is
automatically stable across requeues.

Neither `"mctl-agents-shepherd"` nor `"mctl-agents-investigate"` has an
operation constant; only implement does
(`orchestrator/temporal/constants.py:73`). The approve dict is built inline at
`dev_loop.py:2936-2943` and carries no agent image, because no agent runs.

### The consumer side

`orchestrator/usage_ledger.py:137-142` is the whole environment-sourced
correlation surface:

```python
# Correlation read from the runner pod's environment (the CWFTs set these).
_CORRELATION_ENV = (
    ("WORKFLOW_TEMPORAL_WORKFLOW_ID", "temporal_workflow_id"),
    ("WORKFLOW_NAME", "argo_workflow_name"),
    ("WORKFLOW_WORK_ITEM_ID", "work_item_id"),
)
```

read at `usage_ledger.py:371-375`:

```python
env = os.environ if environ is None else environ
found = {field: env.get(name, "").strip() for name, field in _CORRELATION_ENV}
```

There is no `WORKFLOW_TEMPORAL_RUN_ID` and no `WORKFLOW_EXECUTION_ID` in this
repository. `execution_id` arrives by a different route entirely — the runner's
`correlate` scope (`usage_ledger.py:53-62`, `work_correlation` at
`usage_ledger.py:169-210`), a `contextvars` dict the runner opens around its
SDK session. `run_implementer.py` and `run_shepherd.py` have no correlation
CLI arguments (`run_implementer.py:4651-4693`,
`run_shepherd.py:3753-3796`), and they do not need any: the producer reads env.

### What replay can and cannot see

`tests/test_workflow_replay.py:15-46` records a measurement, not an
assumption, against temporalio 1.31.0:

| change | replay |
| --- | --- |
| activity added / removed / reordered | NondeterminismError |
| `task_queue=` added | invisible |
| `start_to_close_timeout` changed | invisible |
| **an extra argument added to an existing activity** | **invisible** |
| divergence in the LAST recorded workflow task | invisible |

`tests/test_patch_memoization.py` establishes the other half: `patched()`
memoises per id, so an execution whose history lacks a marker gets `False` from
that call forever, "including calls made long after replay has finished".
Migration is by attrition.

## Proposed solution

Three surgical changes, in the order they must land.

### 1. A correlation helper on `DevLoopWorkflow`, gated by one new patch id

Add a module-level constant next to the existing patch-id constants
(`dev_loop.py:284-321` holds the pattern, e.g. `DISPATCHED_NOT_RUN_FAILS_PATCH`):

```python
#: Guards the correlation params added to the implement and shepherd submits
#: (mctlhq/mctl-agents#505, owner decision 4 on mctlhq/.github#50). Depends on
#: mctl-gitops#1408 declaring them on cwft-mctl-agents-implement.yaml and
#: cwft-mctl-agents-shepherd.yaml.
LAUNCH_CORRELATION_PATCH = "launch-correlation"
```

and one private method:

```python
def _launch_correlation(self) -> dict[str, str]:
    """This loop's ids, for a CWFT that declares them (#505).

    Empty for an execution whose history predates the marker: `patched()`
    memoises (tests/test_patch_memoization.py), so such a loop keeps
    submitting exactly the params it recorded for the rest of its life,
    including a merge watch that outlives the deploy by up to
    MERGE_WATCH_DEADLINE.

    `workflow.info()` schedules no command, so this adds nothing to history
    beyond the marker itself.
    """
    if not workflow.patched(LAUNCH_CORRELATION_PATCH):
        return {}
    info = workflow.info()
    correlation = {
        "temporal_workflow_id": info.workflow_id,
        "temporal_run_id": info.run_id,
    }
    if self._work_item_id:
        correlation["work_item_id"] = self._work_item_id
    return correlation
```

Apply it at exactly the two sites in scope:

- `dev_loop.py:2997`, immediately after `implement_params` is built and
  *before* `_implement` is called, so the same values ride every pre-start
  requeue: `implement_params.update(self._launch_correlation())`.
- `dev_loop.py:3693`, inside `_shepherd_tick`, before the submit:
  `tick_params.update(self._launch_correlation())`.

`work_item_id` is included only when non-empty. `self._work_item_id` is `""`
for every loop that was not dispatched (`dev_loop.py:1439`, set from
`issue.work_item_id` at `2390`/`2588` and from a resume at `3103`), and both
`usage_ledger.py:375`'s `.strip()` truthiness and mctl-api's
`validateCorrelation` treat a blank as absent — so omitting the key is the
same outcome with less noise across the wire.

`execution_id` is deliberately not forwarded. See requirements.md Open
questions: `dispatched.execution_id` names the *investigator* invocation
(`dev_loop.py:2660`), and `dev_loop.py:2738-2746` already strips it from the
continuation submit for exactly this reason. The issue's acceptance criteria
name only `temporal_workflow_id` and `temporal_run_id`.

### 2. Teach the producer to read the run id

`orchestrator/usage_ledger.py:138-142` gains one entry:

```python
_CORRELATION_ENV = (
    ("WORKFLOW_TEMPORAL_WORKFLOW_ID", "temporal_workflow_id"),
    ("WORKFLOW_TEMPORAL_RUN_ID", "temporal_run_id"),
    ("WORKFLOW_NAME", "argo_workflow_name"),
    ("WORKFLOW_WORK_ITEM_ID", "work_item_id"),
)
```

Without this, change 1 is unobservable and the issue's acceptance criterion
cannot be met by any amount of CWFT plumbing.

This is a **contract addition, not just a code change**, and that is the
finding most likely to change the shape of the work.
`docs/adr/012-model-usage-cost-attribution-contract.md:143-153` enumerates the
correlation block — `temporal_workflow_id`, `argo_workflow_name`, `agent`,
`devloop_stage`, `target_repo`, `issue_number`, `pr_number`, `work_item_id`,
`execution_id`, `trace_id`/`span_id` — and `temporal_run_id` is not in it.
Lines 188-192 of the same ADR name `temporal_workflow_id` as "the join key" to
`agent_executions`, with `argo_workflow_name` disambiguating the Argo run
within it. So ADR-012 currently answers the attribution question with the
workflow id plus the Argo name, and the run id is new surface that mctl-api's
ingest must accept before it can be stored. The ADR needs a matching
amendment, and `_CORRELATION_ENV` should not grow the entry until mctl-api
accepts the field — otherwise every DevLoop pod sends a key the ingest may
reject, and `usage_ledger.py:152-155` warns a rejected field "costs its whole
batch".

The read path at
`usage_ledger.py:371-375` already handles absence by producing `""`, which the
existing filter drops, so a pod without the variable — every non-DevLoop run,
and every run before mctl-gitops#1408 deploys — behaves exactly as today. The
module docstring at `usage_ledger.py:51-52` must be updated to list four
env-sourced fields instead of three.

### 3. Record the cross-repo contract in-repo

The `service`-parameter comment at `dev_loop.py:2979-2991` is the house style
for a dependency mctl-agents CI cannot check out: it names the sibling file, the
parameter, the step, and the silent-revert failure mode. Mirror it for the new
parameters, naming `cwft-mctl-agents-implement.yaml`,
`cwft-mctl-agents-shepherd.yaml` and mctl-gitops#1408, and stating the env var
names the templates must set (`WORKFLOW_TEMPORAL_WORKFLOW_ID`,
`WORKFLOW_TEMPORAL_RUN_ID`, `WORKFLOW_WORK_ITEM_ID`) so the two repos agree on
the one string neither side can validate.

### Why the patch gate, given that replay cannot see this

Honest answer, because the issue's stated reason does not hold: adding a
parameter is invisible to `Replayer` (measured, above), and the investigate
site already carries correlation *without* a marker and says so. The gate
earns its keep for a different reason — deploy ordering. `patched()` memoises,
so a gate confines the new parameters to executions started after this deploy.
Dev loops already mid-flight when it lands — potentially for the full
`MERGE_WATCH_DEADLINE`, ticking the shepherd all the while — keep submitting
their recorded parameter set. That bounds the blast radius if mctl-gitops#1408
is not yet deployed, or is rolled back, to loops started in that window, and it
makes the rollout reversible by redeploying without the marker rather than by
reasoning about which long-lived loops have already changed behaviour.

The gate also costs something, and it should be stated: `workflow.patched()`
writes a marker command into history, so this *does* add a command where the
unmarked investigate approach adds none. That is the standard, supported
shape — an unmarked history returning `False` is what `patched()` is for — but
it means the new marker must be asserted from recorded fixture *content*, the
way `exec-queue` is (`tests/test_workflow_replay.py:299-338`), not from replay
alone.

## Alternatives

1. **Inject correlation inside `_run_cwft` for all operations.** Tempting: one
   funnel, one edit, and every future submit inherits it. Dropped because it
   changes two call sites that must not change. The approve CWFT
   (`dev_loop.py:2936`) runs no agent and produces no usage record, so it would
   gain parameters for nothing; and the investigate continuation
   (`dev_loop.py:2738-2746`) deliberately *removes* identity keys, which a
   funnel that adds them back would silently defeat. A helper called at the two
   sites in scope keeps the blast radius equal to the issue's scope.

2. **No patch gate, matching the investigate precedent verbatim.** Defensible,
   and strictly simpler: the code comment at `dev_loop.py:2628-2631` already
   argues that a parameter addition needs no marker, and it is correct about
   replay. The file argues against speculative markers even more directly at
   `dev_loop.py:4818-4826`, explaining why there is deliberately no
   `lifecycle-claims` marker: "A `workflow.patched` call writes a marker into
   EVERY new execution's history and can only be retired through
   `deprecate_patch` plus a second deploy — a cost with no branch to pay for."
   That objection has real force here, because the branch this gate buys is
   `{}` versus three keys. Dropped because it makes the behaviour of mid-flight loops depend on
   when mctl-gitops#1408 deployed relative to this — a merge watch running for
   days would start sending undeclared parameters the moment the worker
   restarts, which is the one case mctl-api's planned tightening of
   `StripUndeclared` into a rejection turns into a failed submit. It also
   contradicts the issue's explicit instruction. If the reviewer prefers the
   lighter change, deleting the gate is a two-line revert and the tests for
   the patched branch stay valid.

3. **Add `--temporal-workflow-id` / `--temporal-run-id` CLI flags to
   `run_implementer.py` and `run_shepherd.py` and scope them through
   `usage_ledger.correlate`, the way `execution_id` travels.** Dropped: the
   producer already has an environment path for exactly these fields
   (`_CORRELATION_ENV`), the investigator's CLI flags exist for work-context
   *sealing* rather than usage, and a second source for one field invites the
   two to disagree. Extending `_CORRELATION_ENV` by one tuple entry is a
   smaller change than two argparse surfaces plus two `correlate` call sites.

4. **Wait for mctl-api to expose a Temporal-native correlation channel instead
   of CWFT parameters.** Dropped: no such channel exists or is planned, and
   owner decision 4 is scoped to the parameter path the investigate submit
   already uses.

## Platform impact

**Migrations.** None. No schema, no stored state, no gitops file in this repo.
Usage records gain an optional field; mctl-api's ingest already tolerates
absent correlation fields (`usage_ledger.py:250-252` shows the per-field drop
pattern for a malformed one).

**Backward compatibility.** Additive on both sides. A pod without
`WORKFLOW_TEMPORAL_RUN_ID` records exactly what it records today. A CWFT that
does not declare `temporal_run_id` has the parameter stripped by mctl-api with
a warning (`StripUndeclared`, per `docs/observability/execution-traces.md:205-208`)
— so even out-of-order deployment degrades to today's behaviour rather than
failing, *until* mctl-api tightens that to a rejection. `ImplementSweepWorkflow`
(`implement_sweep.py:168-170`) builds its own `SubmitAndWaitInput` and never
calls `_run_cwft`, so the cron sweep and the manual trigger are untouched by
construction, not by care.

**Resource impact.** Negligible: two short strings per submit, plus one marker
event per `DevLoopWorkflow` execution.

**Risks and mitigations.**

- *Env var name mismatch across repos.* The single highest risk, and the one
  mctl-agents CI cannot catch — `mctl-gitops` is a sibling repo. Mitigation:
  name the exact variables in the code comment (change 3), confirm against
  mctl-gitops#1408 before merge, and verify after deploy by reading one
  DevLoop-launched implementer's usage record.
- *Deploy ordering.* Merging before mctl-gitops#1408 makes the feature inert
  today and a failed submit once mctl-api tightens. Mitigation: the patch gate
  confines the new parameters to loops started after deploy, and rollback is a
  redeploy without the marker.
- *Silent no-op.* Because a stripped parameter produces only a warning on the
  mctl-api side, this change can ship, pass CI, and do nothing. Mitigation:
  the post-deploy verification in tasks.md is a check of an actual ingested
  record, not of a green test run.
- *A record whose `temporal_run_id` mctl-api rejects on shape.* Would cost the
  whole batch (`usage_ledger.py:152-155`). Mitigation: confirm
  `validateCorrelation` treats it as free text like the other env-sourced
  fields; if not, add the matching regex guard beside `_EXECUTION_ID_RE`.
- *Fixture regeneration.* `tests/replay_scenarios.py:28-38` warns that
  re-recording a `*.prepatch.json` silently destroys the only coverage of an
  unpatched branch while every test still passes. Mitigation: do not
  re-record `dev_loop_full.prepatch.json`; add the new marker to the
  content assertions on the `*.patched.json` side only.
