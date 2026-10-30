# Design: issue-758-fix-directives-reinvestigate-submits-inv

## Current state

- `orchestrator/run_issue_directive_poller.py`
  - `scan()` -> `_handle_directive()` is the decision table: unauthorized, unrecognised, no-proposal, ambiguous, not-overwritable, dispatched, dispatch-failed, dispatch-ambiguous, policy-refused, dry-run.
  - `submit_investigate(issue_url, slug, requested_by)` builds `params = {"issue_url": issue_url}`, runs `policy_checkpoint.require(...)` and POSTs `/api/v1/operations/mctl-agents-investigate/execute`. It never sends `work_item_id` or `execution_id`.
  - The module docstring states that it "never starts or signals a DevLoopWorkflow".
- The poller runs inside the Temporal worker: `orchestrator/temporal/activities/issue_poll.py` `directive_scan_activity` calls `scan()`, and it is registered in `orchestrator/temporal/worker.py`. A Temporal client is therefore available through `temporalio.activity.client()` (temporalio 1.31.0 in `uv.lock`). Outside an activity (the `python -m` CLI), `orchestrator/temporal/start.py` `connect()` provides one.
- `orchestrator/temporal/workflows/dev_loop.py` `DevLoopWorkflow`:
  - A canonical loop resolves its WorkItem and attaches its own run as `Running` (`_ensure_canonical_execution` -> activity `canonical_execution.ensure_issue_execution`, engine ref `issue_ref.run_engine_ref(...)`).
  - Its investigate step forwards `work_item_id` and `execution_id = self._canonical_execution_id()`, plus `temporal_workflow_id` / `temporal_run_id`, to `_run_cwft("mctl-agents-investigate", ...)`. The code comment there reads: "A canonical loop's own `we_` is handed over the same way: it is Running, so an investigator attaching its own Argo run would meet `execution_active`."
  - The `@workflow.query work_context()` returns `WorkContextState(work_item_id, execution_id, execution_sequence, ...)`, where `execution_id` is the latest `ExecutionRef`. For a canonical loop that is the store `we_`. For a pre-#636 loop with `issue.work_item_id` it is a seed hash from `execution_id_for`.
  - The grant-freshness patch (module docstring, mctl-agents#701) already notices that `@MCTL reinvestigate` rewrote the proposal, supersedes the stale `aar_`, and asks for a new grant on the same `we_`.
  - No signal or Update re-runs investigate. `accept_execution_request` / `_deliver` (resume) only re-arm approval.
- `orchestrator/temporal/issue_ref.py` `workflow_id_for(issue_url)` derives `dev-loop-mctlhq-<repo>-<n>`.
- `orchestrator/run_issue_investigator.py` `_resolve_work_context_ref`: a `we_` passed as `--execution-id` is used as-is ("nothing is attached, and its owner advances its phase"). Without one, the investigator self-attaches its Argo run, but only after the pod has started. The run-token exchange in `orchestrator/run_token.py` happens at start and depends on the Workflow's submitted `execution_id` argument, so self-attach comes too late for enforce.
- `orchestrator/work_context/snapshots.py` `is_store_execution(execution_id)` checks for the `we_` prefix.
- `orchestrator/run_shepherd.py` (around line 259) already does a liveness read through mctl-api `GET /api/v1/agents/dev-loop/{id}`. That route returns only status, not `work_context`, so it cannot supply the execution id.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`:
  - Declares `work_item_id`, `execution_id`, `temporal_workflow_id`, `temporal_run_id` and `execution_request_id` as optional parameters (omitted when empty) and forwards them as investigator flags.
  - The container env currently sets `MCTL_RUN_TOKEN_MODE: observe`, with a comment that enforce was reverted because "investigate runs submitted without an execution_id cannot be bound to a run token" (mctlhq/mctl-agents#752). So the checkout shows observe, not the enforce that the issue describes from mctl-gitops#2078. Possibly this is a later revert; recorded under Open questions in requirements.md.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the worker has `TEMPORAL_ADDRESS=temporal-frontend.temporal.svc.cluster.local:7233` and `TEMPORAL_NAMESPACE=mctl-agents`, which confirms the poller's host can reach Temporal.
- mctl MCP tools were not called. The audit row and the failed run `mctl-agents-investigate-b478e8fa` cited in the issue were not re-observed. The diagnosis relies on the issue text plus the code above.

## Proposed solution

Add an execution-identity resolution step in front of `submit_investigate`, and make submission conditional on it.

1. New module `orchestrator/directive_execution.py`, kept separate so `run_issue_directive_poller` stays light:
   - `@dataclass(frozen=True) class LoopExecution`: `work_item_id`, `execution_id`, `workflow_id`, `run_id`.
   - `class NoExecution(Exception)` carries a definite reason (`no-live-loop`, `loop-not-canonical`, `no-work-item`). This is an answer, not a transient failure.
   - `class ExecutionLookupUnavailable(Exception)` covers the case where Temporal could not answer. It is transient.
   - `async def resolve_loop_execution(issue_url, client=None) -> LoopExecution`:
     1. Compute `workflow_id_for(issue_url)`.
     2. Get the handle and call `describe()`. A not-found error -> `NoExecution("no-live-loop")`. Status other than RUNNING -> `NoExecution("no-live-loop")`. Any other RPC error -> `ExecutionLookupUnavailable`.
     3. Query `work_context` with a short RPC timeout. A query failure -> `ExecutionLookupUnavailable`.
     4. Empty `work_item_id` -> `NoExecution("no-work-item")`. `not is_store_execution(execution_id)` -> `NoExecution("loop-not-canonical")`.
     5. Return the ids, with `run_id` from the describe so the query and the params name the same run.
   - Client: `temporalio.activity.client()` when `activity.in_activity()`, else `await orchestrator.temporal.start.connect()`.
2. `submit_investigate(issue_url, slug, requested_by, execution: LoopExecution)`: the identity becomes a required argument, so no caller can submit without one. `params` gains `work_item_id`, `execution_id`, `temporal_workflow_id` and `temporal_run_id`. The policy checkpoint metadata gains `execution_id`. Add an assertion guard that raises `ValueError` before the checkpoint if `execution_id` is not a store execution (defence in depth).
3. `_handle_directive`, recognised path (before dispatch):
   - Call `resolve_loop_execution`.
   - On `NoExecution`: post an acked reply `_reply_no_execution(author, comment_id, reason)` and return `"no-execution"`. The reply names the reason and the supported path: start or let the DevLoop run via the `agents:intake` label or `mctl_trigger_issue use_temporal=true`, then reinvestigate. Reinvestigation can run only inside a live loop because investigate runs need an execution identity under run-token enforce.
   - On `ExecutionLookupUnavailable`: go through the existing generic `except Exception` branch (unacked, `fail_trailer`, `MAX_DISPATCH_ATTEMPTS`). This keeps one retry/give-up policy.
   - `--dry-run` logs the resolved ids and returns `"dry-run"`.
   - `_reply_dispatched` mentions that the run is bound to the DevLoop's execution `we_...`.
4. Update the module docstring: the poller now reads (describe + query) the issue's DevLoop but still never starts, signals or updates it. Also update the `submit_investigate` docstring's parameter paragraph. Add `"no-execution"` to the `_handle_directive` outcome list and to `DirectiveScanResult` counting, if it counts outcomes by name.

Why this way:
- It reuses the exact identity the loop already gives its own investigate run, so the binder sees a shape it already accepts (the DevLoop-submitted observe run `mctl-agents-investigate-3b5674e6` exchanged).
- The loop keeps ownership of the `we_` lifecycle. The grant-freshness mechanism that already exists supersedes the approval after the rewrite, which keeps "the proposal rewrite and the grant supersede inside the loop that owns the proposal" in substance, without a workflow change.
- Nothing is minted, so nothing can be leaked as a non-terminal execution that blocks the item.

## Alternatives

1. Mint a fresh WorkItem execution in the poller (the issue's first expectation, using `canonical_execution.ensure_issue_execution`). Dropped as the primary path:
   - With a live canonical loop, the item already has a `Running` execution, so attach answers `execution_active` and the mint fails exactly where the acceptance case lives.
   - Without a loop, the minted `we_` has no owner to end it. The investigator does not advance a handed-in `we_`, and the poller does not wait for Argo. That would block later DevLoops for the issue.
   - `ensure_issue_execution` also rejects any engine ref that is not a `#run_` loop ref.
2. Add a `reinvestigate` signal or Update to `DevLoopWorkflow` so the loop resubmits investigate itself (the issue's "Better"). This is architecturally the cleanest, but it needs a new `workflow.patched` marker and changes to the parked-approval wait loop (re-enter investigate from the approval park and reset `_signalled_refs`). Replay tests are also needed, which is a larger and riskier change than the incident warrants. Kept as a follow-up. The proposed solution is forward compatible: the poller's lookup is the same lookup a future signal path would use.
3. Route the directive through an mctl-api execution request (`kind=resume`). Dropped: on a live loop, `accept_execution_request` / `_deliver` only re-arms approval and never re-runs investigate, so the proposal would not be rewritten.
4. Flip investigate back to observe. Explicitly rejected by the issue.

## Platform impact

- No migration and no gitops change. The CWFT already declares the parameters, and mctl-api already forwards them (the DevLoop uses them).
- Backward compatibility:
  - Issues whose proposal came from the legacy direct-Argo path, or from pre-#636 loops, now get a `no-execution` reply instead of a run. Under enforce those runs failed anyway. Under observe they used to run without an identity, so this is a deliberate narrowing. It is documented in the reply.
  - The poller now requires Temporal reachability. The worker has it.
- Resources: one describe and one query per dispatched directive, capped by `DEFAULT_MAX_DIRECTIVES = 3` per tick. Negligible.
- Risks and mitigations:
  - Two Argo runs under one `we_` (see Open questions in requirements.md). Mitigation: this is the identity the loop already hands out, and the investigator does not advance it. If mctl-api objects, the follow-up is alternative 2.
  - Race: the loop leaves approval (implement starts) between the query and the POST. The existing `_OVERWRITABLE_STATUSES` check, plus the investigator's own `resolve_slug` refusal for a non-proposed status, still bound this.
  - A `work_context` query on a very old loop history without the query: this is a query failure. Classify the "query not found" or unknown-query error as `NoExecution("loop-not-canonical")`, not as unavailable, so it does not retry forever.
