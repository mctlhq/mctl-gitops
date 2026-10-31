# Tasks: issue-880-security-mcp-decide-whether-scoped-agent

- [ ] 1. Deploy prerequisite (mctl-gitops, not this repo; owner decision
  hir-6053c71d87283c69): `argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
  must set `WORK_ITEM_INTENT_SOURCE: "off"` (today `"on"`), with the comment
  citing mctl-api#880. Newly sealed snapshots then carry no intents, which
  is accepted. This lands before the mctl-api release carrying task 2 is
  deployed. — DoD: the mctl-api PR description names this prerequisite and
  links the merged gitops PR. The mctl-api PR is not released while the
  template still says `"on"`.
- [ ] 2. In `internal/auth/agent_scope.go`, add `Deny []AgentScopeRoute` to
  `AgentScope`. In `Allows`, refuse any request whose method matches (an
  empty Method matches all) and whose path matches a `Deny` pattern, before
  the `Routes` loop. — DoD: `go build ./...` passes, and `Allows` returns
  false for a Deny match even when an allow route also matches.
- [ ] 3. (depends on 2) In the same file, add `agentDeniedTools`
  (`list_work_item_intents`) and `agentDeniedRoutes`
  (`^/api/v1/work-items/[^/]+/intents(/.*)?$`), with a comment citing
  mctl-api#880. Make `AllowsTool` refuse `agentDeniedTools` before consulting
  `Tool`. Set `Deny: agentDeniedRoutes` on the `investigate` and `support`
  scopes. — DoD: the investigate scope refuses the tool, with and without the
  `mctl_` prefix, and refuses the REST intents paths for its own work item.
  Every other existing allow is unchanged.
- [ ] 4. (depends on 3) Update `docs/work-context-contract.md`: the
  `WorkItemIntent` bullet and the "MCP surface" section must say scoped agent
  run tokens are refused intent reads on MCP and REST, own work item
  included, with `agent_scope_denied`, and that the investigator's intent
  source therefore stays `off` and its snapshots omit intents. Keep `mctl_list_work_item_intents` at
  `"enabled": false` in `docs/portal-allowlist.json`, and extend its `reason`
  to cite mctl-api#880 only if no test pins that text. — DoD: the docs match
  the behaviour, and the allowlist still validates in its existing tests.
- [ ] 5. Run `go fmt ./...`, `go vet ./...` and `golangci-lint run`, then
  `go test ./...`. The MCP tool count in `server_test.go` does not change
  (no tool added or removed). — DoD: all pass.

## Tests

- [ ] T1. `internal/auth/agent_scope_test.go`, `TestInvestigateScope_Routes`:
  add cases.
  - Refused with own work item `wi_a`: `GET /api/v1/work-items/wi_a/intents`,
    `GET /api/v1/work-items/wi_a/intents/1`,
    `GET /api/v1/work-items/wi_a/intents/`,
    `HEAD /api/v1/work-items/wi_a/intents`.
  - Still allowed: `GET /api/v1/work-items/wi_a/snapshots` and
    `GET /api/v1/work-items/wi_a/execution-requests`.
- [ ] T2. New `TestAgentScopes_RefuseWorkItemIntents` in
  `internal/auth/agent_scope_test.go`. For every name in `AgentScopeNames()`:
  `AllowsTool("mctl_list_work_item_intents")` and
  `AllowsTool("list_work_item_intents")` are false. In the same test, assert
  `IsReadTool("mctl_list_work_item_intents")` is true, so the refusal comes
  from the exclusion and not from naming. If the `agentDeniedTools` entry is
  removed, the investigate case fails.
- [ ] T3. New `TestInvestigateScope_DenyIsLoadBearing`. Copy the investigate
  scope, set the copy's `Deny` to nil, and assert the copy would allow
  `GET /api/v1/work-items/wi_a/intents` for `wi_a`. Assert the real scope
  refuses it. This proves the deny entry, not a missing allow route, is what
  closes the path, so removing it fails T1.
- [ ] T4. `internal/mcp/agent_scope_test.go`,
  `TestAgentScopeMiddleware_ScopedRunCallsOnlyItsTools`: add
  `mctl_list_work_item_intents` to the refused list (handler not run, error
  text contains `agent_scope_denied`). Assert `mctl_list_work_item_snapshots`
  and `mctl_get_work_item` still run.
- [ ] T5. `internal/api/agent_scope_gate_test.go`,
  `TestAgentScopeGate_ScopedRunReachesOnlyItsScope`: add
  `GET /api/v1/work-items/wi_own/intents` and
  `GET /api/v1/work-items/wi_own/intents/7`, each expecting 403 with code
  `agent_scope_denied`. Raise the expected `agent_scope.denied` row count from
  6 to 8.
- [ ] T6. `TestAgentScopeGate_ShadowCountsAndNeverRefuses` (or a sibling
  test): a direct service request with shadow header `investigate` to
  `/api/v1/work-items/wi_x/intents` is served (not 403) and counted
  `verdict="deny"`.
- [ ] T7. Regression: `TestAgentScopeGate_UnscopedRunTokenIsUnchanged` and
  the existing intents handler tests still pass. A non-agent principal and an
  unscoped run token still reach the intents handlers.

## Rollback

Revert the mctl-api commit and release. The change is code-only, with no
schema, data or config migration, so a revert restores the previous
behaviour at once. The gitops `WORK_ITEM_INTENT_SOURCE` flag can be set back
to `"on"` independently, but only after the revert is deployed. Otherwise
investigate runs that reference an intent fail with `intent-unresolved`.
