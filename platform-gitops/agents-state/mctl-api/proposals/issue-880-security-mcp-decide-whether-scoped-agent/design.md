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
Owner decision: fail closed, with an explicit capability, plus the own-WorkItem bound.

1. **Capability on the scope (`internal/auth/agent_scope.go`).** Add a server-defined field to `AgentScope`:
   `ReadRawIntents bool // capability workitem:intents:read_raw: scoped runs see intent text`.
   Add `func (u *User) MayReadRawIntents() bool` that returns true for every non-agent caller and for unscoped tokens (today's behaviour), and, for a scoped run token, returns the scope's `ReadRawIntents`. No scope sets it in this change, `investigate` and `support` included. The capability is defined by the server per scope, never taken from a token claim, header or request argument.
2. **Withhold in the REST handlers (`internal/api/handlers_work_item_intents.go`).** After the visibility and bound checks, when `!user.MayReadRawIntents()`, set `Text = ""` and `TextWithheld = true` on each returned intent (list and single). Do it on a copy of the response, never on the stored row, and never touch `TextRedacted`. Because the MCP tool calls this REST route with the caller's token, the MCP path inherits the behaviour with no MCP change.
3. **New response field (`internal/workitems/types.go`).** ``TextWithheld bool `json:"text_withheld"` ``, always present, `false` unless withheld by scope. Document in the type comment that it is distinct from `TextRedacted` (retention) and that a withheld intent's text still exists and may be returned to a caller with the capability.
4. **Second check in the handler (own WorkItem).** As the investigation proposed: `scopedRunMayReadIntents(user, item)` returns false when `user.IsAgent() && user.AgentScopeName() != "" && item.ID != user.WorkItemID()`, called in `ListWorkItemIntents` and `GetWorkItemIntent` right after `visibleWorkItem`, answering 404 `work_item_not_found`. This follows the `sealsOwnExecution` precedent.
5. **Structural guard tests (`internal/auth/agent_scope_test.go`).**
   - For every scope in `AgentScopeNames()`, any route whose pattern matches `/api/v1/work-items/wi_x/intents` must have `BindWorkItem: true`.
   - `support` does not `AllowsTool("mctl_list_work_item_intents")`.
   - No scope has `ReadRawIntents: true` unless its name is in `rawIntentScopes` declared in the test (empty). Granting it later therefore needs an explicit, reviewed test change.
6. **MCP description (`internal/mcp/workitems.go`).** Extend the `mctl_list_work_item_intents` description: `text_withheld: true` means the caller's scope may not read intent text; the text exists but is not shown, and clients must not treat it as empty or as removed.
7. **Docs.** In `docs/work-context-contract.md` ("MCP surface (mctl-api#341)") add an "Agent run scopes" paragraph: scoped runs read only their own WorkItem's intents; their text is withheld (`text_withheld`) unless the scope grants `workitem:intents:read_raw`, which no scope does today; `support` may not call the tool; intent text is untrusted input to an agent; the shared-portal switch stays disabled (#237). Document `text_withheld` next to `text_redacted` in the intents schema. Append "agent run tokens: own WorkItem only, text withheld without workitem:intents:read_raw (mctl-api#880)" to the `reason` of `mctl_list_work_item_intents` in `docs/portal-allowlist.json`, keeping `enabled: false`.

Why this shape: the REST handler is the single place both paths pass through, so withholding there closes MCP and REST together (the investigation showed that excluding only the tool would leave REST open). Returning the intent metadata with the text withheld keeps the run able to see that intents exist, who wrote them and when, without exposing human-written instructions to a run nobody granted them to.

## Alternatives
- **Option 1, accept bounded to the run's own WorkItem** (the investigation's original proposal). Not chosen by the owner: any scoped run on a WorkItem would receive human-written instructions without an explicit decision. Its own-WorkItem bound and guard tests are kept (items 4 and 5).
- **Refuse the read entirely for scoped runs** (exclude the tool and split the `investigate` route so `/intents` is not admitted). Dropped: it hides that intents exist at all and adds route-list churn, while the withheld projection gives the same protection for the text.
- **Reuse `text_redacted` for scope withholding.** Dropped: `text_redacted` means retention removed the text permanently. Conflating the two would make a client treat withheld text as gone.
- **Capability as a token claim.** Dropped: scopes are server-defined; a claim minted per token would make the grant a mint-time input instead of a reviewed scope property.
- **Change `IsReadTool` to stop treating `list_` as a read for some tools.** Dropped: it breaks parity with the mctl-agents policy checkpoint (`_READ_VERBS`) and affects every scope.

## Platform impact
- No migrations, config or env changes. No new MCP tools, so the `server_test.go` tool count is unchanged.
- Additive response field `text_withheld` on intents (`workitem/v1`), always present. Human, admin and unscoped callers see no other change.
- Behaviour change for scoped runs only: a scoped `investigate` run now receives intent metadata with the text withheld. No deployed agent flow reads intents today (they were added in #868, 4.143.0), so nothing that works today stops working. The cross-item handler check refuses only a read the gate already refuses.
- Risk: the handler check could refuse a legitimate admin or human read. Mitigation: it applies only when `user.IsAgent()` and the scope name is non-empty. Tests cover a human member and an unscoped run token (unchanged behaviour).
- Risk: a withheld intent is misread as empty or removed. Mitigation: a separate `text_withheld` field, the MCP description, and the contract doc.
- Risk: the capability is granted later without review. Mitigation: the structural test's empty `rawIntentScopes` allowlist.
- Risk: intent text is a prompt-injection vector into an agent once a scope is granted it. It is the same untrusted-input class as the issue body; handling it is mctl-agents' job (out of scope).
- Resource impact: none.
