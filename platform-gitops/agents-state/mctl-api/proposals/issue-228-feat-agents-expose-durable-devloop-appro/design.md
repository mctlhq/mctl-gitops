# Design: issue-228-feat-agents-expose-durable-devloop-appro

## Current state

- `internal/temporalclient/client.go` wraps the Temporal SDK client with
  exactly the operations `mctl-api` needs against `DevLoopWorkflow`
  (`orchestrator/temporal/workflows/dev_loop.py`, which lives in
  `mctl-agents`): `StartDevLoopWorkflow`, `SignalApprove`,
  `DescribeDevLoop`, `QueryShepherdInLoop`. `SignalApprove` (lines
  125-140) sends the `"approve"` signal
  (`temporalclient.ApproveSignalName`) with an optional
  `{"approver":..., "reason":...}` payload, and translates a Temporal
  `NotFound` service error into something `IsNotFound` can detect.
- `internal/api/handlers_dev_loop.go` exposes three routes, all gated by
  `requireTemporalAdmin` (configured client + authenticated + admin):
  - `POST /api/v1/agents/dev-loop/start` → `StartDevLoopWorkflow` (the
    handler).
  - `POST /api/v1/agents/dev-loop/{workflow_id}/approve` →
    `ApproveDevLoopWorkflow`. Decodes an optional JSON body
    `{approver?, reason?}`, defaults `approver` to the authenticated
    caller (`user.ID`), calls `h.opts.TemporalClient.SignalApprove`, and
    maps `IsNotFound` to 404, everything else to 502, success to
    `200 {"workflow_id":..., "signalled":"approve"}`.
  - `GET /api/v1/agents/dev-loop/{workflow_id}` → `GetDevLoopWorkflow`
    (status + `shepherd_in_loop` liveness read).
  - Routes are registered in `internal/api/router.go` (lines 316-325).
- `internal/api/interfaces.go` defines `DevLoopClient` (lines 75-80) as
  the narrow interface `Handlers` depends on instead of the concrete
  `*temporalclient.Client`, specifically so `handlers_dev_loop_test.go`
  can inject `fakeDevLoopClient` and exercise the auth/status-mapping
  branches without a live Temporal frontend.
- **Audit gap**: `ApproveDevLoopWorkflow` (and `StartDevLoopWorkflow`)
  never call `h.logAudit` — grep across `internal/api` for
  `h.logAudit(` shows every call site is in `handlers_write.go`
  (the generic `operations.Registry`-driven `ExecuteOperation` path used
  by `mctl-agents-approve`, `mctl-agents-investigate`, etc.) and in
  `handlers_platform_skills.go`. The dev-loop handlers were added later
  (plan phase 4) and were never wired into `internal/api/clientmeta.go`'s
  `logAudit` helper, even though `h.opts.AuditLog` (`audit.Log`,
  `internal/audit/logger.go`) is already available on `Handlers` for
  exactly this purpose and already carries `ClientIP`/`UserAgent`/
  `RequestID` from `ClientMetaFromContext`.
- The MCP surface (`internal/mcp/server.go`, `cmd/mcp`) already proxies
  the sibling `start` endpoint: `toolTriggerIssue()` (lines 2488-2534)
  registers `mctl_trigger_issue` with a `use_temporal` boolean; when true
  it calls `s.apiPostJSON(ctx, "/api/v1/agents/dev-loop/start", ...)`
  instead of submitting the `mctl-agents-investigate` operation. This is
  the established pattern for "MCP tool that is a thin proxy over one
  dev-loop REST route" — `apiPostJSON` forwards the caller's bearer token
  (`s.effectiveToken(ctx)`, sourced from `auth.TokenFromContext` in SSE
  mode or `s.apiToken` in stdio mode) via `doRequest`, so the REST
  handler's own `requireTemporalAdmin` check is what actually enforces
  admin-only — the MCP layer does not re-implement authorization.
  Nothing today proxies the `approve` route.
- `RegisterTools` (`internal/mcp/server.go`, ~lines 83-162) is a flat
  list of `srv.AddTool(s.toolXxx())` calls; there is no dynamic
  discovery. `internal/mcp/server_test.go:168` hardcodes
  `len(result.Result.Tools) != 70` as a regression check (per this
  repo's `CLAUDE.md`: "MCP tool count must match `server_test.go`
  expectation when adding/removing tools").
- `internal/openapi/openapi.yaml` already documents
  `POST /api/v1/agents/dev-loop/{workflow_id}/approve` in full (lines
  1876+), including the admin-only note and the approver/reason body —
  this is REST-facing documentation, not MCP tool documentation, so it
  needs no change for this proposal, but the MCP tool description must
  carry the equivalent distinction the issue asks for (durable DevLoop
  approval vs. proposal-file status mutation).
- The standalone `mctl-agents-approve` operation
  (`internal/operations/registry.go`, ~line 608) is `RiskMedium` and is
  what the issue explicitly says must not be triggered as a side effect
  or fallback of this new tool — it writes `.status.yaml` directly via
  the Argo `mctl-agents-approve` WorkflowTemplate, bypassing whatever a
  live `DevLoopWorkflow` believes about its own state.

## Proposed solution

1. **Add audit logging to `ApproveDevLoopWorkflow`**
   (`internal/api/handlers_dev_loop.go`), following the exact shape
   already used in `handlers_write.go`'s `ExecuteOperation`:
   - On admin-check failure: `requireTemporalAdmin` already returns the
     HTTP error; add a `h.logAudit` call for the not-admin/not-authenticated
     branches is not needed there (matches existing convention — auth
     failures before user resolution are not logged elsewhere either,
     e.g. `requireAgentRegistryAdmin` also logs nothing on 401). Keep this
     consistent: only log once a `user` and `workflow_id` are known.
   - On malformed JSON body / missing `workflow_id`: no audit entry
     (input never reached authorization-relevant state; mirrors how
     `ExecuteOperation` does not log JSON-decode failures upstream of
     it either — those are client bugs, not access decisions).
   - Immediately before calling `SignalApprove`, once `workflowID` and
     the resolved `approver`/`reason` are known, no "submitted" entry is
     needed (`SignalApprove` is synchronous, unlike
     `Executor.Submit`'s async Argo submission) — log once, after the
     call resolves:
     - `SignalApprove` returns `IsNotFound`: `logAudit` with
       `Operation: "dev-loop-approve"`, `WorkflowName: workflowID`,
       `UserID: user.ID`, `Parameters: {"approver":..., "reason":...}`,
       `Status: "failed"`, `RiskLevel: string(operations.RiskMedium)`,
       `Message: "workflow not found"`. Then 404.
     - `SignalApprove` returns any other error: same shape,
       `Status: "failed"`, `Message: "signal failed: " + err.Error()`.
       Then 502.
     - Success: `Status: "succeeded"` (this is a synchronous outcome, not
       a `"submitted"`-then-reconciled one like Argo operations — there
       is no separate close-out step, so it goes straight to a terminal
       status per `audit.IsTerminal`), `Message` empty. Then 200.
   - `h.logAudit` already fills `ClientIP`/`UserAgent`/`RequestID` from
     `ClientMetaFromContext`, so "request ID" in the issue's acceptance
     criteria falls out of the existing helper for free — no new field
     needed on `audit.Entry`.
   - `Operation: "dev-loop-approve"` is a new, distinct string from
     `"mctl-agents-approve"` (the operations-registry name) specifically
     so the two approval paths are trivially distinguishable in an audit
     query — this directly satisfies the issue's "tests prove ... does
     not call standalone mctl-agents-approve" criterion at the audit
     layer, in addition to the handler-call-graph level (see Tests).
   - This is a REST-layer change, so it also benefits the existing
     `curl`/Temporal-CLI callers of the same endpoint, not just the new
     MCP tool — closing a real audit gap, not something invented to
     satisfy the MCP proposal.

2. **Add `mctl_approve_dev_loop` MCP tool**
   (`internal/mcp/server.go`), mirroring `toolTriggerIssue`'s
   `use_temporal` branch exactly:
   - New `func (s *Server) toolApproveDevLoop() (mcplib.Tool,
     server.ToolHandlerFunc)`, placed near `toolTriggerIssue()` in the
     "Agent orchestration" section of the file (same grouping as the
     other `mctl_trigger_*` / `mctl_*_agent*` tools, per the
     `RegisterTools` comment blocks around line 146+).
   - Tool schema: `workflow_id` (required string), `approver` (optional
     string), `reason` (optional string) — matching
     `approveDevLoopRequest` in `handlers_dev_loop.go` field-for-field.
   - Description explicitly states: this signals an *existing*
     `DevLoopWorkflow` via the same Temporal `approve` signal the REST
     endpoint and Temporal CLI use; it does not start a workflow, does
     not edit `.status.yaml`, and is not the same operation as
     `mctl_trigger_implementer` or the standalone `mctl-agents-approve`
     REST operation — reusing almost verbatim the distinction already
     drawn in `toolTriggerIssue`'s own description
     ("the dev-loop approve signal ... flips .status.yaml to
     'accepted'... No PR is opened by this step").
   - Handler body: build `map[string]interface{}{"approver": ...,
     "reason": ...}` from present arguments only (omit empty ones, so
     the REST handler's own defaulting logic — `approver` defaults to
     caller — is unchanged and not shadowed by an MCP-side empty
     string), then
     `s.apiPostJSON(ctx, "/api/v1/agents/dev-loop/"+workflowID+"/approve",
     body)`. Reuse `stringArg` for extraction. On transport/HTTP error
     from `apiPostJSON` (which already surfaces the REST handler's JSON
     `{"error": ...}` body, per `doRequest`'s `resp.StatusCode >= 400`
     branch), return `mcplib.NewToolResultError(...)` — same pattern as
     every other tool in this file. No new authorization logic in the
     MCP layer: the forwarded bearer token plus the REST handler's
     `requireTemporalAdmin` is the single enforcement point, exactly as
     for `mctl_trigger_issue`'s `use_temporal=true` branch today.
   - `workflowID` must be taken from a required argument and passed
     through unchanged into the URL path (`url.PathEscape` it, matching
     how other tools building path-parameterized requests already guard
     against a workflow ID containing `/`; check existing tools like
     `toolGetWorkflowLogs`/`toolReadOpenClawSkill` for the exact idiom
     already used in this file for path-segment args and reuse it,
     rather than introducing a second escaping convention).
   - Register `srv.AddTool(s.toolApproveDevLoop())` in `RegisterTools`,
     directly after `srv.AddTool(s.toolTriggerIssue())` (same functional
     area, keeps the "Agent orchestration" grouping intact).
   - Bump `internal/mcp/server_test.go`'s `len(result.Result.Tools) !=
     70` to `!= 71` — required by this repo's own `CLAUDE.md` note ("MCP
     tool count must match `server_test.go` expectation").

3. **No changes** to `temporalclient.Client`, `DevLoopClient`,
   `router.go`'s route table, `DevLoopWorkflow`'s Python implementation,
   or the standalone `mctl-agents-approve` operation. The REST contract
   (`POST /api/v1/agents/dev-loop/{workflow_id}/approve`) is reused
   as-is; the MCP tool is additive.

## Alternatives

1. **New dedicated Temporal-signal HTTP endpoint just for MCP.** Rejected:
   the issue explicitly asks the MCP tool to "call the same
   handler/service path as the REST endpoint" — a second endpoint would
   duplicate `requireTemporalAdmin`, the approver-defaulting logic, and
   the not-found/error mapping, doubling the surface that needs the audit
   fix in item 1 above, for no behavioral gain.
2. **Call `temporalclient.Client.SignalApprove` directly from the MCP
   server process, bypassing HTTP.** Rejected: `cmd/mcp` and `cmd/api`
   are separate binaries/processes in this repo (see `cmd/api/main.go`
   vs `cmd/mcp`), and the MCP server has no direct dependency on
   `internal/temporalclient` or a live Temporal connection today — it
   only ever talks to `mctl-api` over HTTP with a bearer token
   (`s.apiURL`, `s.doRequest`). Wiring a second Temporal client into the
   MCP process would duplicate connection config/credentials and, worse,
   move authorization enforcement into a second code path
   (`requireTemporalAdmin` lives on `Handlers`, not reusable without
   also duplicating `auth.UserFromContext`/admin-group logic) — exactly
   the kind of drift the issue is trying to prevent by insisting on "same
   handler/service path."
3. **Skip the audit-logging fix and ship the MCP tool as a pure proxy
   over today's `ApproveDevLoopWorkflow`.** Rejected: the issue's
   acceptance criteria are explicit ("Authorization is admin-only and
   uses the existing mctl audit path"; "the audit record includes
   caller, workflow ID, approver, reason, request ID, and outcome").
   Today's handler has no audit path to reuse — grepping confirms
   `handlers_dev_loop.go` never calls `logAudit`. Shipping the MCP tool
   without first closing that gap would satisfy "calls the REST
   endpoint" but fail the audit acceptance criteria outright, and would
   also leave the pre-existing `curl`/CLI approval path unaudited, which
   is a real gap independent of this issue.

## Platform impact

- **Migrations**: none. `audit.Logger`/`audit.PostgresLogger` already
  accept arbitrary `Operation` strings; `"dev-loop-approve"` needs no
  schema change (`internal/audit/postgres.go` — confirm the persistent
  logger has no fixed operation enum before implementation; the
  in-memory `Logger.Log` certainly has none, per `logger.go`).
- **Backward compatibility**: fully additive. The REST contract for
  `POST /api/v1/agents/dev-loop/{workflow_id}/approve` is unchanged from
  the caller's perspective (same request/response shape); it merely
  gains a side effect (an audit row) it should have had already. The
  MCP surface gains one tool; no existing tool's schema or behavior
  changes. `server_test.go`'s hardcoded tool count is the one required
  edit outside of `internal/api` and `internal/mcp`.
- **Resource impact**: negligible — one additional `audit.Log.Log` call
  per approval (a rare, human-gated action, not a hot path), and one
  additional MCP tool definition (in-memory schema, no new dependency).
- **Risks + mitigations**:
  - *Risk*: an admin using `mctl_approve_dev_loop` on a stale or
    misremembered `workflow_id` accidentally signals the wrong proposal's
    workflow. *Mitigation*: this is identical to the existing `curl`/CLI
    risk and is unchanged by this proposal — `workflow_id` is required
    and never derived, per both the issue and this design; the audit
    entry (once added) makes any such mistake traceable after the fact.
  - *Risk*: `SignalApprove` on a `Completed`/`Terminated` workflow may
    surface as a generic Temporal error rather than the `NotFound` case
    `IsNotFound` currently special-cases, degrading it to a 502 instead
    of a clean 404/terminal signal. *Mitigation*: flagged under Open
    Questions in requirements.md as the interpretation this proposal
    takes (preserve current status-mapping exactly); a follow-up that
    adds a `DescribeDevLoop` pre-check to `ApproveDevLoopWorkflow` can
    tighten this later without changing the MCP tool's contract.
  - *Risk*: forgetting to bump `server_test.go`'s tool-count assertion
    breaks CI. *Mitigation*: called out explicitly in tasks.md as its own
    task with its own DoD, per this repo's `CLAUDE.md` instruction.
