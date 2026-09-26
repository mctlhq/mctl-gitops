# DevLoopWorkflow passes Temporal and work-item correlation to the implement and shepherd CWFTs

## Context

Usage records produced under ADR-012 (`orchestrator/usage_ledger.py`) are
meant to say which piece of work spent the tokens. Today only the investigate
submit carries the loop's identity: `DevLoopWorkflow` stamps
`temporal_workflow_id` / `temporal_run_id` (and, on the dispatched path,
`work_item_id` / `execution_id`) onto `investigate_params` at
`orchestrator/temporal/workflows/dev_loop.py:2631-2645`. The implement submit
(`implement_params`, built at `dev_loop.py:2992-2997`, submitted through
`_implement` -> `_run_cwft(IMPLEMENTATION_OPERATION, params)` at
`dev_loop.py:3366`) and the in-loop shepherd tick (`tick_params`, built and
submitted at `dev_loop.py:3690-3694`) pass none of it. A DevLoop-launched
implementer or shepherd therefore emits usage rows that cannot be joined back
to the loop that paid for them, which is owner decision 4 on
mctlhq/.github#50.

Investigation of the clone turned up two facts that the issue body states
differently, and both change what "done" has to mean. First,
`_CORRELATION_ENV` at `orchestrator/usage_ledger.py:137-142` reads exactly
three environment variables — `WORKFLOW_TEMPORAL_WORKFLOW_ID`,
`WORKFLOW_NAME`, `WORKFLOW_WORK_ITEM_ID`. There is no
`WORKFLOW_TEMPORAL_RUN_ID` and no `WORKFLOW_EXECUTION_ID` anywhere in the
repository (verified by grep across `orchestrator/`, `tests/`, `config/`,
`tools/`, `entrypoint.sh`). Passing a `temporal_run_id` CWFT parameter alone
can therefore never make `temporal_run_id` appear on a usage record: the
producer would have to read it. Second, the issue says an undeclared CWFT
parameter is rejected; this repo's own notes say mctl-api **strips** it with a
warning today (`StripUndeclared` in `internal/api/handlers_write.go`, cited in
`docs/observability/execution-traces.md:205-208` and
`orchestrator/tracing.py:58-61`) and only *intends* to tighten that to a
rejection. So the mctl-gitops#1408 dependency is an ordering requirement for
the feature to have any effect, and a hard safety requirement only once
mctl-api tightens.

## User stories

- AS a platform owner reconciling ADR-012 spend I WANT every DevLoop-launched
  implementer and shepherd usage record to name the Temporal workflow and run
  that launched it SO THAT I can attribute cost to a single dev loop instead
  of to an unattributed pool of agent runs.
- AS an operator debugging a runaway loop I WANT `work_item_id` on implementer
  and shepherd usage rows SO THAT I can total the spend of one work item
  across all three tiers without joining through Argo workflow names.
- AS a Temporal operator I WANT this change to leave already-running dev loops
  on their recorded behaviour SO THAT a deploy landing before
  mctl-gitops#1408 cannot change what a mid-flight 14-day merge watch submits.
- AS a maintainer of the cron sweep and the manual trigger I WANT submits made
  outside a `DevLoopWorkflow` to be byte-identical SO THAT this change cannot
  regress `ImplementSweepWorkflow` or `mctl_trigger_implementer`.

## Acceptance criteria (EARS)

- WHEN `DevLoopWorkflow` submits the implement CWFT
  (`_run_cwft(IMPLEMENTATION_OPERATION, ...)`, `dev_loop.py:3366`) THE SYSTEM
  SHALL include `temporal_workflow_id` and `temporal_run_id` in the submitted
  params, taken from `workflow.info().workflow_id` and
  `workflow.info().run_id`.
- WHEN `DevLoopWorkflow` submits the in-loop shepherd tick
  (`_run_cwft("mctl-agents-shepherd", ...)`, `dev_loop.py:3694`) THE SYSTEM
  SHALL include the same two parameters with the same values.
- IF the loop holds a non-empty `self._work_item_id` at the moment of either
  submit THEN THE SYSTEM SHALL also include `work_item_id` with that value.
- IF `self._work_item_id` is empty THEN THE SYSTEM SHALL omit the
  `work_item_id` key entirely rather than sending an empty string, so the
  producer's `env.get(name, "").strip()` truthiness check in
  `usage_ledger.py:375` and mctl-api's `validateCorrelation` never see a blank
  correlation field.
- WHILE a `DevLoopWorkflow` execution's history lacks the new patch marker THE
  SYSTEM SHALL submit implement and shepherd params exactly as recorded, with
  no correlation keys added, for the remaining life of that execution
  (`workflow.patched` memoises per id — see `tests/test_patch_memoization.py`).
- WHEN the implement submit is retried by `_implement`'s pre-start requeue
  loop (`dev_loop.py:3350-3366`, `MAX_PRESTART_REQUEUES`) THE SYSTEM SHALL
  send the same correlation values on every attempt, so requeued attempts of
  one loop group together.
- WHEN a usage record is built inside a pod whose environment carries
  `WORKFLOW_TEMPORAL_RUN_ID` THE SYSTEM SHALL populate the record's
  `temporal_run_id` field from it, via a new entry in
  `usage_ledger._CORRELATION_ENV`.
- WHILE `WORKFLOW_TEMPORAL_RUN_ID` is absent from a pod's environment THE
  SYSTEM SHALL emit the record with `temporal_run_id` omitted and SHALL NOT
  fail, warn, or drop the record — every runner outside a DevLoop must keep
  recording usage unchanged.
- WHEN a submit is made by `ImplementSweepWorkflow`
  (`orchestrator/temporal/workflows/implement_sweep.py:168-170`), by the cron
  sweep, or by the manual `mctl_trigger_implementer` path THE SYSTEM SHALL
  submit the identical parameter set it submits today.
- WHEN the investigate submit runs THE SYSTEM SHALL keep its current
  parameters and semantics unchanged, including the continuation submit's
  deliberate `pop` of `work_item_id` / `execution_id`
  (`dev_loop.py:2738-2746`).
- WHEN the approve CWFT is submitted (`dev_loop.py:2936`) THE SYSTEM SHALL NOT
  add correlation parameters, because that operation runs no agent and
  produces no usage record.

## Out of scope

- Changing the mctl-gitops workflow templates. `cwft-mctl-agents-implement.yaml`
  and `cwft-mctl-agents-shepherd.yaml` must declare the optional parameters and
  map them to pod env / CLI flags; that is mctl-gitops#1408 and it must deploy
  first.
- Adding `--temporal-workflow-id` / `--temporal-run-id` CLI arguments to
  `orchestrator/run_implementer.py` or `orchestrator/run_shepherd.py`. The
  producer reads correlation from the pod environment
  (`usage_ledger._CORRELATION_ENV`), not from argv, so no runner argparse
  change is required for this feature. Their argparse blocks
  (`run_implementer.py:4651-4693`, `run_shepherd.py:3753-3796`) stay as they
  are.
- Forwarding `execution_id` to the implement and shepherd submits. See Open
  questions; the loop's dispatched `we_` names the investigator invocation, and
  the issue's own acceptance criteria name only `temporal_workflow_id` and
  `temporal_run_id`.
- Adding `WORKFLOW_EXECUTION_ID` to `_CORRELATION_ENV`. `execution_id` reaches
  a record through the runner's `correlate` scope
  (`usage_ledger.py:53-62`, `209-210`), not through the environment, and
  giving it a second source would let the two disagree.
- Backfilling correlation onto usage records already ingested by mctl-api.
- Any change to the approve CWFT, to `_record`, to the agent registry resolve,
  or to queue routing.

## Open questions

- The issue's Scope asks for `execution_id` on the implement and shepherd
  submits. This proposal deliberately omits it. The loop's `dispatched.execution_id`
  is the work-context `we_` of the *investigator* run — `dev_loop.py:2660`
  says "The dispatched execution IS this investigator run", and
  `dev_loop.py:2738-2746` already strips `execution_id` from the investigate
  *continuation* submit precisely because "a continuation is a different
  context, which the store would refuse as a divergence under the same
  execution". An implementer or shepherd is likewise a different invocation,
  and `usage_ledger.py:59-62` defines `execution_id` as naming the runner
  invocation. Reusing the investigator's `we_` would make three invocations
  share one execution id and misattribute spend. `work_item_id` already
  provides the loop-level grouping that owner decision 4 wants. Proceeding
  without `execution_id`; if the owner wants it anyway, it is a one-line
  addition inside the same helper and the same patch gate.
- The issue cites `orchestrator/usage_ledger.py:138-142` as reading four env
  vars. It reads three, and `WORKFLOW_TEMPORAL_RUN_ID` does not exist in the
  repo. This proposal adds it. If mctl-gitops#1408 chose a different env var
  name for the pod side, the name here must match it exactly, and that is the
  one cross-repo string this change cannot verify from inside mctl-agents.
- `temporal_run_id` is not a declared ADR-012 field.
  `docs/adr/012-model-usage-cost-attribution-contract.md:143-153` lists the
  correlation block without it, and lines 188-192 name `temporal_workflow_id`
  as the join key to `agent_executions` with `argo_workflow_name`
  disambiguating the Argo run inside it. Adding `temporal_run_id` to a usage
  record is therefore an amendment to that contract and needs mctl-api's ingest
  to accept the field first. This proposal treats the ADR amendment and the
  mctl-api side as prerequisites for the producer half, and sequences tasks
  accordingly. The reviewer should decide whether the run id is wanted at all,
  or whether `temporal_workflow_id` + `argo_workflow_name` already answer owner
  decision 4 — in which case this reduces to passing
  `temporal_workflow_id` / `work_item_id` and nothing in `usage_ledger.py`
  changes.
- Whether mctl-api's `validateCorrelation` (`internal/usage/types.go`)
  constrains `temporal_run_id`'s shape. `usage_ledger.py:152-155` warns that a
  looser check on this side lets a record through that "costs its whole
  batch". The three env-sourced fields are currently free text there; the
  assumption is that a fourth is too. Worth confirming against mctl-api before
  merge.
- The issue asks for "replay of a pre-change history" as coverage.
  `tests/test_workflow_replay.py:15-46` measured, on temporalio 1.31.0, that
  "an extra argument added to an existing activity" is **invisible** to
  `Replayer`. Replay therefore cannot verify this change either way. The patch
  gate is still worth having — see design.md — but its value must be asserted
  from recorded history *content*, the way the `exec-queue` flip is, not from
  a green replay. Proceeding on that basis.
- Whether mctl-api has tightened `StripUndeclared` into a rejection by the
  time this merges. If it has, the mctl-gitops#1408 ordering is load-bearing
  for correctness rather than merely for effect.
