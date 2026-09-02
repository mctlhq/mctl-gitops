# Design: issue-235-feat-mcp-mctl-agents-reconcile-and-appro

## Current state

`internal/operations/registry.go` is the single source of truth for
platform operations. Each `Operation` (struct at `registry.go:32-51`) has a
`Name`, `WorkflowTemplate`, `RiskLevel`, `AdminOnly`, `HandlerOnly`, and a
`[]ParameterDef` list with `Enum`/`Pattern`/`Default` validation metadata.
`Registry.List()` (`registry.go:83`) and `Registry.Get(name)`
(`registry.go:77`) are the read accessors; `internal/api/handlers_write.go`'s
`ExecuteOperation` (`handlers_write.go:37`) is the generic HTTP handler
mounted at `POST /operations/{name}/execute` (`router.go:315`). It looks the
operation up, rejects it with 405 if `HandlerOnly` is true
(`handlers_write.go:50-53`), enforces `AdminOnly`/tenant-access RBAC
(`handlers_write.go:68-88`), applies a `mctl-agents-approve`-specific
default (`input["approver"] = user.ID` when empty, `handlers_write.go:138-144`),
then calls `Registry.ApplyDefaults` and `Registry.ValidateInput`
(`handlers_write.go:148-149`) before submitting the Argo Workflow.

Two operations in that registry, `mctl-agents-approve` (`registry.go:608-624`)
and `mctl-agents-reconcile` (`registry.go:626-655`), are `AdminOnly: true`,
`HandlerOnly` unset (i.e. `false`) — meaning both are fully reachable through
the generic execute path today, exactly like `mctl-agents-shepherd`. Both
have complete `Parameters` definitions with `Enum`/`Pattern` validation:
`mctl-agents-approve` takes `service` (required, enum of service names),
`slug` (required, pattern-validated), `approver` (optional, default
`"unknown"`, but overridden server-side to the caller's identity per
`handlers_write.go:138-144`); `mctl-agents-reconcile` takes `service`
(optional, same enum, default `""` meaning "sweep everything") and
`dry_run` (optional, `"true"`/`"false"`, default `"false"`).

`internal/mcp/server.go` is the MCP tool surface. `NewMCPServer()`
(`server.go:69`) registers tools in labeled blocks; the "mctl-agents
triggers" block (`server.go:150-158`) currently registers seven tools:
`toolTriggerAgentsRun`, `toolTriggerMentorOnly`, `toolTriggerSingleService`,
`toolTriggerIncidentResponder`, `toolTriggerImplementer`,
`toolTriggerShepherd`, `toolTriggerIssue` — plus `toolApproveDevLoop`
(a different thing, see below) and `toolListRecentAgentRuns`. Every
`toolTrigger*` function (`server.go:2322-2535`) follows the same shape:
build an `mcplib.Tool` with `mcplib.NewTool(name, WithTitleAnnotation(...),
WithDescription(...), WithString(param, ...)...)`, then a handler that runs
`params := extractStringParams(req.GetArguments())` (or an empty map for
no-parameter operations) and `s.apiPost(ctx, "/api/v1/operations/<op>/execute",
params)`, returning `mcplib.NewToolResultError` on failure or
`mcplib.NewToolResultText(string(body))` on success. `toolTriggerShepherd`
(`server.go:2446-2487`) is the closest existing analog to both new tools:
it is `AdminOnly`+`RiskMedium` like `mctl-agents-approve` and
`mctl-agents-reconcile`, and it declares three `WithString` parameters
(`service` with the full service enum, `slug`, `dry_run` with a
`true`/`false` enum) — `mctl-agents-reconcile` needs exactly two of those
three (`service`, `dry_run`), and `mctl-agents-approve` needs `service` plus
`slug` plus a third string (`approver`) instead of `dry_run`.

`toolApproveDevLoop` (`server.go:2537`, name `mctl_approve_dev_loop`) already
exists but is a different mechanism: it POSTs to
`/api/v1/agents/dev-loop/{workflow_id}/approve`, signalling a running
Temporal `DevLoopWorkflow`. It does not touch `operations.Registry` or the
`mctl-agents-approve` operation at all. `toolTriggerIssue`'s description
(`server.go:2500`) already documents that both paths exist ("the dev-loop
approve signal, or the mctl-agents-approve operation, flips .status.yaml to
'accepted'"), which is the wording this proposal's new
`mctl_trigger_approve` tool description should echo from the other
direction.

`internal/mcp/server_test.go` has two existing parity guards scoped to a
single operation each: `TestToolDeployService_ExposesEveryOperationParameter`
(`server_test.go:100`) and `TestToolCreateTenant_ExposesEveryOperationParameter`
(`server_test.go:310`). Both fetch one `operations.Operation` via
`reg.Get(name)` and assert every `ParameterDef.Name` (minus a small,
commented-and-justified internal-only exception set) is a key in
`tool.InputSchema.Properties`. Neither test enumerates operations — they are
both hardcoded to one operation name and one tool getter. There is no test
today that walks `Registry.List()` and confirms an MCP tool exists at all
for each entry; that is the exact gap the issue's "systemic half" describes.
`TestNewMCPServer_ToolCount` (`server_test.go:58`) is a placeholder — despite
`CLAUDE.md`'s "MCP tool count must match server_test.go expectation" note,
the test body only asserts `NewMCPServer()` doesn't return nil and doesn't
actually count or compare anything (comment: "We can't easily count tools
without reflection").

## Proposed solution

1. **Add `toolTriggerReconcile` in `internal/mcp/server.go`**, placed
   immediately after `toolTriggerShepherd` (before `toolTriggerIssue`, to
   keep the block's ordering roughly registry-order). It follows the exact
   `toolTriggerShepherd` shape: `mcplib.NewTool("mctl_trigger_reconcile",
   WithTitleAnnotation("Run mctl-agents reconcile sweep"),
   WithDestructiveHintAnnotation(true), WithDescription(...))` with two
   `WithString` parameters — `service` (optional, same enum list as
   `toolTriggerShepherd`'s `service` parameter, copied verbatim from
   `registry.go:648-649`) and `dry_run` (optional, `Enum("true", "false")`,
   copied from `registry.go:650`). The description is adapted directly from
   the registry's `Description` field for `mctl-agents-reconcile`
   (`registry.go:642`) plus the Cost/Duration/Result convention every
   sibling tool uses (`registry.go` comment already gives "Cost: none (no
   model). Duration: ~3-5 min for a full sweep."). The handler:
   `params := extractStringParams(req.GetArguments())`; `s.apiPost(ctx,
   "/api/v1/operations/mctl-agents-reconcile/execute", params)`; error ->
   `mcplib.NewToolResultError`; success -> `mcplib.NewToolResultText`.
   `WithDestructiveHintAnnotation(true)` because, per the registry comment
   at `registry.go:629-635`, reconcile can open a PR for an already-pushed
   branch — not purely read-only, matching why `toolTriggerShepherd` and
   `toolTriggerImplementer` both set this hint.

2. **Add `toolTriggerApprove` in `internal/mcp/server.go`**, placed
   immediately after `toolTriggerReconcile`. Same shape:
   `mcplib.NewTool("mctl_trigger_approve", WithTitleAnnotation("Approve
   mctl-agents proposal"), WithDestructiveHintAnnotation(true),
   WithDescription(...))` with three `WithString` parameters: `service`
   (required, same enum, from `registry.go:621`), `slug` (required, no enum
   — free-form pattern-validated server-side), `approver` (optional — the
   description notes the server defaults it to the authenticated caller's
   identity per `handlers_write.go:138-144`, so callers do not need to pass
   it explicitly). The description explicitly distinguishes this tool from
   `mctl_approve_dev_loop`, in both directions: state that this flips
   `.status.yaml` directly via GitOps and is the wrong choice for a
   proposal with a live `DevLoopWorkflow` (use `mctl_approve_dev_loop`
   instead, which signals the workflow that itself calls this operation).
   Handler: identical `extractStringParams` -> `apiPost(ctx,
   "/api/v1/operations/mctl-agents-approve/execute", params)` shape.
   `WithDestructiveHintAnnotation(true)` because approving authorizes the
   Tier 2 implementer to spend a model attempt and open a PR — an
   `AdminOnly`+`RiskMedium` operation server-side, same class as
   `toolTriggerImplementer` and `toolTriggerShepherd` which both set this
   hint.

3. **Register both in `NewMCPServer()`**: add `srv.AddTool(s.toolTriggerReconcile())`
   and `srv.AddTool(s.toolTriggerApprove())` to the "mctl-agents triggers"
   block at `server.go:150-158`, positioned after
   `srv.AddTool(s.toolTriggerShepherd())` and before
   `srv.AddTool(s.toolTriggerIssue())` — mirroring the two new functions'
   placement in the file and keeping `toolApproveDevLoop` /
   `toolListRecentAgentRuns` as the block's tail, unchanged.

4. **Add a registry-to-MCP parity test** in `internal/mcp/server_test.go`,
   `TestMCPToolsCoverEveryNonHandlerOnlyOperation`. It builds
   `reg := operations.NewRegistry()`, calls `srv.NewMCPServer()`, and reads
   the live tool set the same way `TestAllToolsHaveTitleAnnotation`
   (`server_test.go:142-176`) already does: send a raw `tools/list` JSON-RPC
   request through `mcpSrv.HandleMessage(ctx, req)` and unmarshal the
   `result.tools[].name` list. That existing test is itself the count-based
   guard `CLAUDE.md` refers to ("MCP tool count must match server_test.go
   expectation") — it hardcodes `len(result.Result.Tools) != 71` — so adding
   two tools also means bumping that literal from 71 to 73 (task 5 below);
   otherwise `TestAllToolsHaveTitleAnnotation` itself goes red first, before
   the new parity test even runs. For every `op := range reg.List()`
   with `op.HandlerOnly == false`, the test looks up `op.Name` in a
   small fixture map:
   ```go
   var operationToTool = map[string]string{
       "mctl-agents-run":            "mctl_trigger_agents_run",
       "mctl-agents-mentor-only":    "mctl_trigger_mentor_only",
       "mctl-agents-single-service": "mctl_trigger_single_service",
       "mctl-agents-incidents":      "mctl_trigger_incident_responder",
       "mctl-agents-implement":      "mctl_trigger_implementer",
       "mctl-agents-shepherd":       "mctl_trigger_shepherd",
       "mctl-agents-investigate":    "mctl_trigger_issue",
       "mctl-agents-approve":        "mctl_trigger_approve",
       "mctl-agents-reconcile":      "mctl_trigger_reconcile",
       "deploy-service":             "mctl_deploy_service",
       "create-tenant":              "mctl_create_tenant",
       // ... one entry per non-HandlerOnly registry.go operation
   }
   ```
   and fails with `t.Errorf("registry operation %q has no MCP tool mapping in operationToTool (and/or no matching tool registered)", op.Name)`
   if the name is missing from the map, or if the mapped tool name is not
   present in the live tool set from `NewMCPServer()`. This makes the test
   fail two different ways an operation can go dark: a maintainer forgets to
   extend the fixture map (test fails immediately, cheap to fix, forces
   them to look up the real tool name), or the fixture map is right but the
   tool got removed/renamed in `server.go` (test fails against the live
   tool set, which is exactly the issue's "delete either new tool and the
   parity test must go red" acceptance check). The map is the explicit
   opt-out mechanism the issue asks for, applied in the affirmative
   (list what must exist) rather than as a skip-list, because
   `operations.Operation.HandlerOnly` already is that skip-list for the
   operations meant to bypass this surface — a second, separate opt-out
   list would just be another place for the same drift to hide.

5. No changes to `registry.go`, `handlers_write.go`, or any
   `ClusterWorkflowTemplate` — both operations already work correctly per
   the issue.

## Alternatives

- **Reflection/codegen: auto-derive MCP tools from `operations.Registry`
  entries.** Rejected. It would remove the per-operation hand-tuning that
  every existing `toolTrigger*` needs (differentiated descriptions,
  Cost/Duration copy, `WithDestructiveHintAnnotation`, parameter subsets
  like `mctl-agents-run`'s locked-`mode` enum that a generic tool must not
  expose as a free string). The issue also explicitly frames the ask as "a
  registry↔MCP parity test", i.e. a guard on a manual process, not a
  replacement of that process. Introducing codegen here would be a much
  larger, riskier change than the two straightforward tool additions the
  issue actually needs.
- **Parity test as a bare count comparison** (`len(reg.List()) - len(handlerOnlyOps) == len(mcpTools)`).
  Rejected. A count match can pass by coincidence (e.g. one operation
  missing its tool while an unrelated extra tool exists) and gives no
  actionable error message pointing at which operation is uncovered — the
  exact failure mode the issue's "silent" framing warns about. The
  name-to-name fixture map catches this and names the missing operation in
  the failure message.
- **Fold `mctl-agents-approve` into `toolApproveDevLoop` as a fallback mode**
  (e.g. `mctl_approve_dev_loop` POSTs to the DevLoop signal if a
  `workflow_id` is given, else falls back to the GitOps operation).
  Rejected. The issue's "Related #228" section is explicit that these are
  two different mechanisms with different ownership semantics that must
  stay independently visible and documented, not merged behind one tool's
  branching logic — merging them would make the "which one am I calling"
  ambiguity worse, not better, especially for the exact conflict case the
  issue flags (a proposal with a live DevLoopWorkflow).

## Platform impact

- **Migrations**: none. No database, GitOps schema, or CWFT changes.
- **Backward compatibility**: additive only — two new MCP tool names, two
  new `srv.AddTool` calls, one new test function. No existing tool's name,
  parameters, or behavior changes. `operations.Registry` entries for
  `mctl-agents-approve` and `mctl-agents-reconcile` are unchanged.
- **Resource impact**: negligible. Both new tools reuse the existing
  `apiPost` HTTP client and the existing `mctl-agents-approve` /
  `mctl-agents-reconcile` Argo submission path already exercised by the
  `curl` workaround described in the issue; no new infrastructure.
- **Risks + mitigations**:
  - *Risk*: a caller uses `mctl_trigger_approve` on a proposal actively
    owned by a running `DevLoopWorkflow`, racing the workflow's own eventual
    approve-signal call to the same operation. *Mitigation*: the operation
    is documented as idempotent on already-accepted proposals
    (`registry.go:612`, "Idempotent: approving an already-accepted proposal
    is a successful no-op"), and the new tool's description calls out the
    DevLoop case explicitly so an MCP client (human or agent) is warned
    before calling it — same mitigation shape the issue itself proposes
    ("the tool descriptions must make the choice obvious").
  - *Risk*: the parity test's fixture map goes stale the same way the tool
    registration did (a new operation added to `registry.go` without a
    matching map entry). *Mitigation*: that is precisely the failure mode
    the test is built to catch — a missing map entry is a test failure, not
    a silent gap, which is the whole point of the issue's ask. This shifts
    the failure from "silent, discovered by an operator hitting a missing
    tool" to "loud, caught by CI on the PR that adds the operation."
  - *Risk*: `RiskMedium`/`AdminOnly` operations becoming easier to trigger
    via a friendlier MCP surface could increase accidental invocation.
    *Mitigation*: both operations are already `AdminOnly` (admin group
    membership enforced server-side in `ExecuteOperation`,
    `handlers_write.go:68-79`) and already reachable via the documented
    `curl` path per the issue — the MCP tool adds parameter validation and
    a documented interface on top of an already-admin-gated capability, it
    does not lower the access bar.
