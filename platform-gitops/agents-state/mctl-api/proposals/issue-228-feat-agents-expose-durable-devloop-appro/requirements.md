# Expose durable DevLoop approval through MCP

## Context

`mctl-api` already runs a durable DevLoop control plane on Temporal
(`internal/temporalclient`, plan phase 4): `POST
/api/v1/agents/dev-loop/start` starts a `DevLoopWorkflow`, and `POST
/api/v1/agents/dev-loop/{workflow_id}/approve`
(`internal/api/handlers_dev_loop.go`, `Handlers.ApproveDevLoopWorkflow`)
sends the workflow's `approve` Temporal signal — the durable equivalent of
flipping a proposal's `.status.yaml` to `accepted`. The mctl MCP server
(`internal/mcp/server.go`) already proxies the sibling `start` endpoint
through `mctl_trigger_issue`'s `use_temporal=true` branch, but no MCP tool
calls the `approve` endpoint. An MCP client (Claude, Codex, or a human
using either through mctl) can start a DevLoop and observe it
(`mctl_get_workflow_status` reads Argo state; nothing today reads the
DevLoopWorkflow itself), but cannot complete the human-approval gate
without an operator running `curl` or a human invoking the Temporal CLI
out-of-band. In the concrete incident cited in the issue,
`mctl-agents#239`'s workflow `dev-loop-mctlhq-mctl-agents-239` is
reviewed and its contract merged, but stuck at `proposed` because the
connected MCP client has no way to signal it — and the standalone
`mctl-agents-approve` operation or a direct `.status.yaml` edit would
bypass DevLoop's own ownership of that proposal's lifecycle (it would
race the workflow, which still believes it owns the transition).

This proposal adds `mctl_approve_dev_loop`, a thin MCP tool that calls the
exact same REST handler the `curl`/Temporal-CLI paths already use, so the
approval gate becomes reachable from an MCP client without introducing a
second way to accept a proposal.

## User stories

- AS an admin operator using an MCP client (Claude/Codex) I WANT to
  approve a running DevLoopWorkflow by its workflow ID SO THAT I do not
  have to leave the chat/agent session to run `curl` or the Temporal CLI.
- AS the mctl platform I WANT the MCP approval path and the REST approval
  path to share one handler and one audit trail SO THAT there is exactly
  one way to durably approve a DevLoop proposal, and every approval —
  regardless of caller — is auditable the same way.
- AS an admin operator I WANT a mistaken double-approval or a stale
  workflow ID to fail safely SO THAT I never accidentally trigger a
  second implementer run or silently no-op against the wrong workflow.

## Acceptance criteria (EARS)

- WHEN an admin-authorized MCP client calls `mctl_approve_dev_loop` with
  a `workflow_id` THE SYSTEM SHALL send the Temporal `approve` signal to
  that exact workflow via the existing `DevLoopClient.SignalApprove` path
  (`internal/temporalclient/client.go`), through the same
  `POST /api/v1/agents/dev-loop/{workflow_id}/approve` handler the REST
  API and Temporal CLI already use.
- THE SYSTEM SHALL require `workflow_id` as an explicit, non-empty
  argument; IF `workflow_id` is omitted or empty THEN THE SYSTEM SHALL
  reject the call with a 400-equivalent error and SHALL NOT derive,
  guess, or start a different workflow.
- WHEN `approver` is omitted THE SYSTEM SHALL default it to the
  authenticated caller's identity, matching the REST contract
  (`approveDevLoopRequest.Approver` defaults to `user.ID` in
  `ApproveDevLoopWorkflow`).
- WHEN `reason` is supplied THE SYSTEM SHALL pass it through unchanged in
  the signal payload, matching the REST contract.
- IF the caller is not authenticated THEN THE SYSTEM SHALL reject with an
  authentication-required error.
- IF the caller is authenticated but not an admin THEN THE SYSTEM SHALL
  reject with an admin-only error, mirroring `requireTemporalAdmin`.
- WHEN the underlying REST call records an audit entry THE SYSTEM SHALL
  capture at minimum: the calling user ID, the target `workflow_id`, the
  resolved `approver`, the `reason` (if any), the request ID, and the
  outcome (denied / not-found / signal-failed / signalled).
- IF `workflow_id` does not correspond to any known Temporal workflow
  (never started, past retention) THEN THE SYSTEM SHALL surface a
  not-found result and SHALL NOT fall back to the standalone
  `mctl-agents-approve` operation, a direct `.status.yaml` write, or the
  Tier 2 implementer trigger.
- IF `workflow_id` corresponds to a workflow that is closed, failed, or
  is not a `DevLoopWorkflow` execution THEN THE SYSTEM SHALL surface the
  Temporal-reported failure (not-found or signal error) and SHALL NOT
  fall back to a direct Argo operation.
- WHILE a `DevLoopWorkflow` is still `Running` and has not yet consumed
  the `approve` signal, repeated `mctl_approve_dev_loop` calls with the
  same `workflow_id` THE SYSTEM SHALL either succeed idempotently (the
  workflow's own `approve()` handler is defensive per
  `SignalApprove`'s doc comment) or return a stable, explicit
  already-approved/terminal-style result — SHALL NOT error in a way that
  looks like a transport failure.
- THE SYSTEM SHALL NOT start a new `DevLoopWorkflow` as a side effect of
  `mctl_approve_dev_loop` under any input.
- THE SYSTEM SHALL document, in the MCP tool description, that this is
  the durable Temporal-signal approval for an existing `DevLoopWorkflow`
  execution, as distinct from the standalone `mctl-agents-approve`
  operation (`internal/operations/registry.go`), which directly mutates
  a proposal's `.status.yaml` outside of any DevLoop ownership.

## Out of scope

- Changing `StartDevLoopWorkflow` / `mctl_trigger_issue`'s existing
  `use_temporal` branch.
- Adding an MCP tool for `GET /api/v1/agents/dev-loop/{workflow_id}`
  (workflow status read) — useful, but not requested by this issue and
  not required to unblock the approval gate.
- Changing `DevLoopWorkflow`'s own Python-side `approve()` semantics
  (`orchestrator/temporal/workflows/dev_loop.py`) — that code lives in
  `mctl-agents`, not `mctl-api`.
- Deprecating or removing the standalone `mctl-agents-approve` operation;
  it remains the correct path for proposals with no live DevLoop
  execution.
- Adding a persistent, queryable "approval history" API beyond what the
  existing audit log already records.

## Open questions

- The issue's acceptance criteria call for "idempotent or explicit
  stable already-approved/terminal result," but neither
  `DevLoopClient.SignalApprove` nor the REST handler currently
  distinguishes "signal delivered to a workflow that already processed
  approve" from "signal delivered for the first time" — Temporal signals
  are fire-and-forget from the client's perspective, and this repo has no
  visibility into the Python workflow's internal state beyond
  `DescribeDevLoop`'s status string and the `shepherd_in_loop` query.
  This proposal's most reasonable interpretation: preserve today's
  behavior exactly (a second signal to a still-`Running` workflow returns
  the same 200/`signalled: approve` response the first one did, since the
  workflow's own handler is documented as idempotent) and treat a signal
  to a `Completed`/`Terminated`/`Failed` workflow as the existing
  not-found/error path — not as a special new "already approved" status
  code. If a distinct terminal-state response is wanted later, it needs a
  `DescribeDevLoop` call added to `ApproveDevLoopWorkflow` first (a
  `mctl-agents`/Python-side change to expose approval state via query is
  a bigger follow-up, tracked here only as a note, not blocking this
  proposal).
- Whether the audit entry's `Operation` field should be a new constant
  (e.g. `"dev-loop-approve"`) distinct from `"mctl-agents-approve"` (the
  standalone operation's registry name) — proceeding with a distinct name
  so the two approval paths are trivially distinguishable in audit
  queries.
- Whether a companion `mctl_get_dev_loop` (wrapping `GET
  /api/v1/agents/dev-loop/{workflow_id}`) should ship alongside this so
  an MCP client can confirm a workflow is `Running` before approving it —
  left out of scope per above, but flagged since the validation scenario
  in the issue implies an operator will want to check status first
  (today only reachable via `curl` or `mctl_get_workflow_status`, which
  reads Argo, not Temporal).
