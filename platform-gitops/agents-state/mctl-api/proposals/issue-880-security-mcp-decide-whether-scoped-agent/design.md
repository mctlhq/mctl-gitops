# Design: issue-880-security-mcp-decide-whether-scoped-agent

## Current state
- `internal/auth/agent_scope.go`
  - `readVerbs = {"get_", "list_", "read_", "search_", "describe_"}`. `IsReadTool` admits any `mctl_list_*` name.
  - The `investigate` scope sets `Tool: IsReadTool` and `ReadAllTenants: true`.
  - Its only work-item route is `AgentScopeRoute{Method: GET, BindWorkItem: true, Pattern: ^/api/v1/work-items/([^/]+)(/.*)?$}`. That covers `/work-items/{own}/intents` and `/intents/{intent_id}` today.
  - The `support` scope's `Tool` is `IsReadTool(n) && supportTools[...]`. `supportTools` does not include `list_work_item_intents`, so support runs are already refused.
- `internal/mcp/workitems.go` `toolListWorkItemIntents` sends `GET /api/v1/work-items/{id}/intents` through `workItemCall`. That call carries the caller's token, so the REST scope gate checks it again.
- `internal/mcp/agent_scope.go` `agentScopeMiddleware` refuses tools outside the scope with `agent_scope_denied`. `internal/api/agent_scope_gate.go` `agentScopeGate` does the same for REST routes, using `scope.Allows` with the token's `WorkItemID`/`ExecutionID`, and writes an `OperationAgentScopeDenied` audit row.
- `internal/api/handlers_work_item_intents.go`:
  - `ListWorkItemIntents` and `GetWorkItemIntent` use `visibleWorkItem` → `canSeeWorkItem` (`internal/api/handlers_work_items.go`). With `ReadAllTenants`, `HasTenantAccess` is true for every tenant.
  - Private items stay hidden: `OwnerPrincipal == principalOf(u)` never matches a run token.
  - The handlers do not check the run's own work item. They rely only on the gate.
- Precedent: `sealsOwnExecution` in `internal/api/handlers_work_item_snapshots.go` checks the scope binding again in the handler "so the handler does not lean on the gate".
- Tests:
  - `internal/auth/agent_scope_test.go` `TestInvestigateScope_Routes` covers `/work-items/wi_a` and the snapshot route, but has no intents case.
  - `internal/mcp/agent_scope_test.go` `TestReadToolsAreRecordedReadOnly` ties `IsReadTool` to the annotations. `internal/mcp/annotations_test.go` records `mctl_list_work_item_intents` as `readOnly: true`.
- Docs:
  - `docs/portal-allowlist.json` has `mctl_list_work_item_intents` at `enabled: false`.
  - `docs/work-context-contract.md` "MCP surface (mctl-api#341)" lists the tool but says nothing about agent scopes.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/`: no `mctl-api` service directory is present (the listed tenants are admins, labs, karabu, namax66, ...). mctl-api's deployed values, for example whether scopes are enforced or shadowed, could not be observed here. This proposal changes only code, tests and docs, and asserts nothing about deployed config.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/issue-investigator-default/profile.yaml`: references the `mcp__mctl__*` tools and `policyRef: scoped-proposal-authoring`. It does not show whether production runs use scoped run tokens.
- mctl MCP tools were not called. The question concerns code-level authorization, and no runtime fact changes the design.

## Proposed solution
Option 1, accept bounded to the run's own WorkItem, written down and fixed by tests:

1. **No change to scope membership.** `investigate` keeps admitting the tool through `IsReadTool` and the REST read through its `BindWorkItem` route. `support` keeps refusing it.
2. **Second check in the handler.** In `internal/api/handlers_work_item_intents.go`, after `visibleWorkItem`, refuse with the same 404 as an invisible item when `user.IsAgent() && user.AgentScopeName() != "" && item.ID != user.WorkItemID()`. Put this in a small helper, `scopedRunMayReadIntents(user, item)`, that both `ListWorkItemIntents` and `GetWorkItemIntent` call. This follows the `sealsOwnExecution` precedent and keeps the bound even if a future scope route forgets `BindWorkItem`.
3. **Structural guard test** in `internal/auth/agent_scope_test.go`. For every scope in `AgentScopeNames()`, any route whose pattern matches `/api/v1/work-items/wi_x/intents` must have `BindWorkItem: true`. A route that admits another item's intents fails the build.
4. **Doc.** Add an "Agent run scopes" paragraph under "MCP surface" in `docs/work-context-contract.md`, stating:
   - a scoped `investigate` run may read the intents of its own WorkItem only (MCP tool and REST);
   - `support` runs may not;
   - intent text is untrusted user input to the agent, not an instruction to the platform;
   - the shared-portal switch stays disabled (#237).

   Append a short "agent run tokens: own WorkItem only (mctl-api#880)" note to the `reason` of `mctl_list_work_item_intents` in `docs/portal-allowlist.json`, and keep `enabled: false`.

Why this option: the intents are the investigator's input. The REST route already exposes them to the run for its own item. The cross-item exposure that would make intents more sensitive than snapshots is impossible under the bound. Snapshot reads, which the portal already enables, have the same bound.

## Alternatives
- **Option 2 as written, excluding only the MCP tool** (an exclusion set used by `investigate.Tool`). Dropped. `workItemCall` is not the only path: the `investigate` scope's REST route `^/api/v1/work-items/([^/]+)(/.*)?$` still admits `GET .../intents`, so the scoped token could read the same data directly. The control would look closed while the data stayed reachable.
- **Option 2 done fully**: exclude the tool, and narrow the `investigate` work-item route to refuse `/intents` (for example split it into explicit GET routes for `/`, `/executions...`, `/snapshots...`, `/execution-requests...`), with tests that a scoped token gets `agent_scope_denied` on both paths. This is consistent, but it takes from the investigator the input it exists to read, and adds route-list churn. Keep it ready if the owner picks option 2. tasks.md says what would change.
- **Change `IsReadTool` to stop treating `list_` as a read for some tools.** Dropped. It would break parity with the mctl-agents policy checkpoint (`_READ_VERBS`) that `readVerbs` mirrors, and it would affect every scope, not only this tool.

## Platform impact
- No migrations, config or env changes. No new MCP tools, so the `server_test.go` tool count is unchanged.
- Backward compatible. The scoped investigate run keeps every read it has today. The new handler check refuses only a cross-item read, which the gate already refuses.
- Risk: the handler check could refuse a legitimate admin or human read. Mitigation: it applies only when `user.IsAgent()` and the scope name is non-empty. Tests cover a human member and an unscoped run token (unchanged behaviour).
- Risk: intent text is a prompt-injection vector into the investigator. It carries the same untrusted-input class as the issue body, and the doc says so. Handling it is mctl-agents' job (out of scope).
- Resource impact: none.
