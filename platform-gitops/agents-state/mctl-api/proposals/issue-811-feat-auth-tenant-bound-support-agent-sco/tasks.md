# Tasks: issue-811-feat-auth-tenant-bound-support-agent-sco

- [ ] 1. Extend the scope model in `internal/auth/agent_scope.go`. Add `AgentScope.BoundTenant`, `MintByTenantMember`, `DefaultTTL` and `MaxTTL`, plus `AgentScopeRoute.BindTenant` and `RequireTenantQuery`. Add `AgentScopeRequest`, `(*AgentScope).Allows` (keep `AllowsRoute` as a wrapper), `tenantQueryKeys` and `AllowsToolCall`. — DoD: the `investigate` tests pass unchanged, and `go vet` and `golangci-lint` are clean.
- [ ] 2. Define the `support` scope (depends on 1). Add `AgentScopeSupport`, the route list from design.md section 1 and the `supportTools` set. The agent is `mctl-support`, the default TTL 10m and the maximum TTL 1h. — DoD: `AgentScopeNames()` returns `investigate, support`.
- [ ] 3. Bind the tenant on the principal (depends on 1). Add `AgentRun.Tenant` and `RequestedBy`, copy them in `NewAgentUser`, and add `User.BoundTenant()` and `User.AgentRunRequestedBy()`. Change `HasTenantAccess` so that a bound scope admits only the exact bound tenant and never "" (`internal/auth/agent.go`, `internal/auth/oidc.go`). — DoD: the unit tests in T4 pass.
- [ ] 4. Store the binding (depends on 3). Add the `tenant` and `via_principal_id` columns to `agentRunTokenSchema` and carry them through `MintAgentRunTokenInput`, `AgentRunToken`, the INSERT and the resolver SELECT in `internal/workitems/agent_run_tokens.go`. — DoD: a store test mints with a tenant and resolves it back. Pre-existing rows resolve with an empty tenant.
- [ ] 5. Mint path (depends on 2, 4). In `internal/api/handlers_agent_run_tokens.go`, add `Tenant` to the body and the human-caller rule for `MintByTenantMember` scopes: membership via `user.Groups`, admin override audited, tenant existence checked. Refuse a tenant on non-bound scopes, apply the scope TTL defaults and cap, and add `tenant`, `via_principal_id` and `admin_override` to the audit and the response. In `issueAgentRunToken`, refuse a `BoundTenant` scope with no tenant, which also covers the exchange. — DoD: tests T6-T9 pass.
- [ ] 6. REST gate (depends on 1, 3). In `internal/api/agent_scope_gate.go`, call `scope.Allows` with the query and the bound tenant, and add `bound_tenant` to the denial audit. In shadow mode, count a `BoundTenant` scope as `shadow_unbound_tenant`. — DoD: T10-T13 pass.
- [ ] 7. Data-derived tenant handlers (depends on 3). In `GetWorkflow`, refuse a bound principal when the team is missing, empty or different. In `ListWorkflows`, skip rows with an empty team for a bound principal (`internal/api/handlers_read.go`). — DoD: T14 passes.
- [ ] 8. MCP enforcement (depends on 1, 3). In `internal/mcp/agent_scope.go`, use `AllowsToolCall` with the request arguments for bound scopes. — DoD: T15-T16 pass. The tool count in `server_test.go` is unchanged, since no tool is added.
- [ ] 9. Mutation verification (depends on 5-8). For each refusal test, remove its guarding check locally and confirm the test fails, then restore it. Record the check/test pairs in the PR description. — DoD: the PR lists every pair with its observed failure.
- [ ] 10. Docs. Add a support-scope section to `docs/` beside the existing agent-scope documentation, covering the mint body, the caller rule and the refusal codes. Add a `CHANGELOG.md` entry through the usual release-please flow. — DoD: the docs show a mint example for a tenant member and an admin.
- 11. (Deferred, no checkbox) Live probe: deferred to S1a (mctlhq/.github#245), not part of this PR. Minting needs the registered `mctl-support` agent definition and a WorkItemExecution, which S1a introduces. S1a mints a support token for `namax66` as a member, expects 200 from `GET /api/v1/status/namax66/<svc>` and 403 `agent_scope_denied` from another tenant, and repeats both through MCP `mctl_get_service_status`. — DoD for this PR: none; S0a is done when T1-T17 pass and task 9 is recorded.

## Tests

- [ ] T1. `agent_scope_test.go`: `support` has `ReadAllTenants == false` and `BoundTenant == true`. No scope sets both.
- [ ] T2. Every name in `supportTools` satisfies `IsReadTool` and is registered in the MCP server. A write tool (`mctl_deploy_service`, `mctl_resolve_incident`) and a read outside the list (`mctl_list_tenants`, `mctl_get_dev_loop`) are refused by `AllowsTool`.
- [ ] T3. `Allows` table test. The bound tenant's path routes are allowed. Another tenant's path is refused. A case-different or suffixed tenant (`Labs`, `labs2`) is refused. An empty bound tenant refuses everything. A duplicate `?team=a&team=b` is refused. A non-allowlisted GET (`/api/v1/tenants`, `/api/v1/previews`, `/api/v1/agent-runs`) is refused. Any POST, PUT or DELETE other than `/mcp` is refused.
- [ ] T4. `HasTenantAccess` for a bound agent: true for the bound tenant only, false for "", for another tenant and for a group the token does not have. `investigate` is unchanged (true for all).
- [ ] T5. Store round trip of `tenant` and `via_principal_id`.
- [ ] T6. Mint: a member mints for their own tenant and gets 200 with `tenant` and a 10m TTL. A relayed member through a surface gets 200.
- [ ] T7. Mint: a non-member is refused with 403 `agent_scope_tenant_forbidden` plus one audit row, and no row is created.
- [ ] T8. Mint: an admin mints for any tenant and gets 200 with `admin_override=true` in the audit. A missing tenant gives 400. An unknown tenant gives 404. A `ttl_seconds` above 3600 gives 400 `invalid_ttl`.
- [ ] T9. Mint: an agent token, a delegated agent request or the direct service principal asking for `support` is refused with 403. A tenant on the `investigate` scope gives 400 `agent_scope_tenant_unexpected`. The exchange with a `support` binding is refused.
- [ ] T10. Gate: a support token reading `/api/v1/status/<other>/x` gets 403 `agent_scope_denied`, the deny counter increments and the audit row has `bound_tenant`.
- [ ] T11. Gate: `/api/v1/services`, `/api/v1/workflows`, `/api/v1/domains` and `/api/v1/incidents` without the tenant filter get 403. With the bound tenant they pass. With another tenant they get 403.
- [ ] T12. Gate: a write route (for example `POST /api/v1/operations/deploy-service/execute`) and a route outside the allowlist get 403. Self-revoke still works.
- [ ] T13. Gate shadow: `X-Mctl-Agent-Scope-Shadow: support` counts `shadow_unbound_tenant` and does not change the outcome.
- [ ] T14. Handlers: with a bound token, `GetWorkflow` for another tenant's workflow, an empty-team workflow and a cron workflow gets 403. `GetIncident` for another tenant gets 403. `IncidentSummary` counts only the bound tenant. `ListWorkflows` drops empty-team rows.
- [ ] T15. MCP: `mctl_get_service_status{team: other}` and `mctl_list_services{}` (no team) are refused with `agent_scope_denied`. `mctl_list_incidents{team: bound}` is allowed. A write tool is refused.
- [ ] T16. MCP: a tool call with `team_name` or `tenant` set to another tenant is refused.
- [ ] T17. Mutation check (task 9): each of T3, T4, T7, T10, T11, T12, T14 and T15 fails when its guarding check is removed.

## Rollback

- No data migration needs reverting. The new columns are additive with `DEFAULT ''`, and older binaries ignore them.
- To disable support tokens without a code revert: remove `AgentScopeSupport` from `agentScopes` and redeploy. Already-minted support tokens then resolve to an undefined scope, which admits nothing (`AllowsRoute`/`AllowsTool` closed on `!ok`). New mints get 400 `agent_scope_unknown`. Outstanding tokens can also be revoked through self-revoke, or they expire within their TTL (max 1h).
- Full rollback: revert the PR. `investigate` behaviour does not depend on any of the new fields, so reverting cannot widen any existing token.
