# Tasks: issue-880-security-mcp-decide-whether-scoped-agent

- [ ] 1. Add `scopedRunMayReadIntents(user *auth.User, item *workitems.WorkItem) bool` in `internal/api/handlers_work_item_intents.go`. It returns false when `user.IsAgent() && user.AgentScopeName() != "" && item.ID != user.WorkItemID()`. Call it in `ListWorkItemIntents` and `GetWorkItemIntent` right after `visibleWorkItem`, and answer through `writeWorkItemError(w, workitems.ErrNotFound)`. — DoD: both handlers return 404 `work_item_not_found` for a scoped run reading another item. Human, admin and unscoped-token behaviour is unchanged. `go vet` and `golangci-lint` are clean.
- [ ] 2. Add intents cases to `TestInvestigateScope_Routes` in `internal/auth/agent_scope_test.go`: GET `/work-items/wi_a/intents` and `/work-items/wi_a/intents/1` bound to `wi_a` → true; `/work-items/wi_b/intents` bound to `wi_a` → false; any bound item with empty work item → false; POST `/work-items/wi_a/intents` → false. — DoD: the test passes, and a pattern change that drops `BindWorkItem` makes it fail.
- [ ] 3. Add `TestAgentScopes_IntentRoutesAreWorkItemBound` in `internal/auth/agent_scope_test.go`. For every scope in `AgentScopeNames()`, each route whose `Pattern` matches `/api/v1/work-items/wi_x/intents` must have `BindWorkItem`. Also assert that the `support` scope does not `AllowsTool("mctl_list_work_item_intents")`. — DoD: the test passes, and fails if either guard is removed.
- [ ] 4. (depends on 1) Extend `internal/mcp/agent_scope_test.go`. A scoped `investigate` token runs `mctl_list_work_item_intents`. A `support` token bound to a tenant is refused with `agent_scope_denied` and the handler does not run. — DoD: both assertions pass.
- [ ] 5. Update `docs/work-context-contract.md` ("MCP surface (mctl-api#341)") with an "Agent run scopes" paragraph recording the decision (mctl-api#880). Append to the `reason` of `mctl_list_work_item_intents` in `docs/portal-allowlist.json`, keeping `enabled: false`. — DoD: the docs match the tests. The allowlist JSON stays valid and the tool stays disabled.
- [ ] 6. Run `go fmt ./... && go vet ./... && go test ./...`. — DoD: all green.

If the owner chooses option 2 instead, replace tasks 1-5 with the following, keeping task 6:
1. Set `investigate.Tool` to `IsReadTool(n) && !agentScopeExcludedTools[bare(n)]`, where `agentScopeExcludedTools = {"list_work_item_intents"}`.
2. Split the `investigate` work-item route so that `/intents(/...)` is not admitted.
3. Add tests that a scoped token gets `agent_scope_denied` on the MCP tool and a 403 on the REST route. Each test must fail if its exclusion is removed.

## Tests
- [ ] T1. `TestInvestigateScope_Routes`: own-item intents allowed, other-item and write refused (task 2).
- [ ] T2. `TestAgentScopes_IntentRoutesAreWorkItemBound`: structural guard over all scopes, and the support tool exclusion (task 3).
- [ ] T3. `internal/api/handlers_work_item_intents_test.go`: a scoped `investigate` run token bound to `wi_a` gets 200 for `wi_a` intents and 404 `work_item_not_found` for a visible tenant item `wi_b`, on both list and single-intent routes. A human tenant member and an admin still get 200 for `wi_b`. A private item is still 404 for the run token.
- [ ] T4. `internal/mcp/agent_scope_test.go`: the investigate token is allowed the tool, and the support token is refused with `agent_scope_denied` (task 4).
- [ ] T5. Existing `TestReadToolsAreRecordedReadOnly` and the annotations tests still pass with no change to the tool count in `server_test.go`.

## Rollback
Revert the PR. Only one runtime behaviour changes: the handler refuses a cross-item read by a scoped run token, and the scope gate already refuses that request. Reverting therefore restores today's behaviour exactly. There is no data, schema or config to unwind, and `docs/portal-allowlist.json` keeps `enabled: false` either way.
