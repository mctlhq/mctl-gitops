# Design: issue-811-feat-auth-tenant-bound-support-agent-sco

## Current state

Scopes (`internal/auth/agent_scope.go`)
- `AgentScope{Name, Agents, ReadAllTenants, Routes, Tool}` and `AgentScopeRoute{Method, Pattern, BindWorkItem, BindExecution}`. There is one scope, `investigate`, with `ReadAllTenants: true`, `Tool: IsReadTool`, a GET route list and one bound POST (the snapshot seal).
- `AllowsRoute(method, path, workItemID, executionID)` matches the path only. It never reads the query string, and it has no notion of a tenant.
- `mcpRoutes` admits `/mcp`. What a tool may do is decided per tool, and the REST calls the tool makes come back through the gate with the same token.

Principal (`internal/auth/agent.go`, `internal/auth/oidc.go`)
- `AgentRun{Agent, ExecutionID, WorkItemID, RunID, Permissions, Scope}`. `NewAgentUser` copies it onto `User` (`agent`, `execID`, `workItemID`, `runID`, `agentPermissions`, `agentScope`).
- `User.HasTenantAccess`: admin, then `ReadAllTenants`, then group equality. An agent user has no groups, so an agent token without `ReadAllTenants` currently reads no tenant at all.
- The middleware resolves an `art_` bearer through `AgentRunResolver` (`oidc.go` ~L995).

Mint and exchange (`internal/api/handlers_agent_run_tokens.go`, `handlers_agent_run_token_exchange.go`)
- `MintAgentRunToken` (POST `/api/v1/agent-run-tokens`, router.go ~L810, its own 120/min rate-limit group) admits only `isDirectService(user)`. The TTL defaults to 1h (`workitems.DefaultAgentRunTokenTTL`) with a 24h cap.
- `issueAgentRunToken` validates the agent against the registry, then `LookupAgentScope` and `AdmitsAgent`. It attaches the agent principal, calls `WorkItems.MintAgentRunToken` and audits.
- `ExchangeAgentRunToken` mints from a k8s pod binding (agent, execution, scope, deadline). It carries no tenant.

Storage (`internal/workitems/agent_run_tokens.go`)
- The `agent_run_tokens` table is created and evolved with `CREATE TABLE IF NOT EXISTS` plus `ALTER TABLE ... ADD COLUMN IF NOT EXISTS scope`. The resolver SELECT joins `work_item_executions`, so a token stops resolving when its execution is terminal.

Enforcement
- REST: `agentScopeGate` (`internal/api/agent_scope_gate.go`, mounted at router.go L503 ahead of `agentPrincipalGate`). For a scoped agent it calls `scope.AllowsRoute`, counts the decision in `mctl_agent_scope_decisions_total`, audits `agent_scope.denied` and returns 403 `agent_scope_denied`. Self-revoke is always allowed. It also contains shadow-mode logic.
- MCP: `agentScopeMiddleware` (`internal/mcp/agent_scope.go`) refuses tools where `!scope.AllowsTool(tool)`. It does not inspect arguments.

Tenant-bearing handlers that matter for a bound tenant
- Path tenant: `GetService` / `GetServiceStatus` / `GetServiceLogs` (`{team}`) and `GetResourceUsage` (`{tenant}`) in `handlers_read.go`.
- Query tenant: `ListServices` (`team`, handlers_read.go L169), `ListWorkflows` (`team`, L362), `ListDomains` (`team`, handlers_domains.go L196), `ListIncidents` (`tenant`, handlers_alerts.go).
- Tenant read from the data: `GetWorkflow` takes the team from the audit row. It deliberately tolerates an empty team for non-admins (handlers_read.go L404+), so for a bound principal it needs an explicit check. `GetWorkflowLogs` is already admin-or-team only. `GetIncident` checks `HasTenantAccess(a.Tenant)`. `IncidentSummary` post-filters on `HasTenantAccess`. `ListWorkflows` skips rows the caller cannot access, but lets `team == ""` rows through for non-admins.
- MCP tool arguments name the tenant as `team` (15 tools), `team_name` (7) or `tenant` (2) (`internal/mcp/server.go`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/`: tenants `admins`, `karabu`, `labs`, `namax66`. mctl-api itself has no `services/*/mctl-api/values.yaml` there, so its deployed env (for example whether the agent registry or the run-token exchange is configured) could not be observed from gitops.
- `$MCTL_GITOPS_ROOT/tenants/`: `admins`, `commerce-proof`, `erpact`, `karabu`, `labs`, `mctl`, `namax66`. None of these files names a support pilot tenant.
- `mctl_list_tenants`: refused, "listing all tenants requires admin access". So the tenant list and the pilot tenant could not be confirmed live (recorded under Open questions in requirements.md).

## Proposed solution

### 1. Scope model (`internal/auth/agent_scope.go`)

- Add `AgentScopeSupport = "support"`.
- Extend `AgentScope`:
  - `BoundTenant bool`: a token with this scope must be minted with a tenant, and every check below compares against it. It is mutually exclusive with `ReadAllTenants`. A unit test asserts this for every scope in `agentScopes`.
  - `DefaultTTL, MaxTTL time.Duration`: zero means the existing workitems defaults. `support` uses 10m and 1h.
  - `MintByTenantMember bool`: the scope is minted by a human tenant member, not by the service principal (see section 3).
- Extend `AgentScopeRoute`:
  - `BindTenant bool`: the named submatch `tenant` (`(?P<tenant>[^/]+)`) must equal the bound tenant.
  - `RequireTenantQuery string`: a list route must carry this query key, and it must equal the bound tenant. Examples: `team` for services, workflows and domains; `tenant` for incidents.
- Introduce a request value and keep the old method as a thin wrapper, so `investigate` callers and tests are untouched:

```go
type AgentScopeRequest struct {
    Method, Path string
    Query        url.Values
    WorkItemID, ExecutionID, Tenant string
}
func (s *AgentScope) Allows(req AgentScopeRequest) bool
func (s *AgentScope) AllowsRoute(method, path, wi, ex string) bool // = Allows{...} with nil Query
```

  `Allows` behaves the same for non-bound scopes. For a `BoundTenant` scope it:
  1. refuses when `req.Tenant == ""`;
  2. refuses when any of `tenantQueryKeys = {team, tenant, team_name, namespace}` appears with more than one value, or with a value other than `req.Tenant`. This applies on every route, so a filter added to a handler later cannot widen the scope;
  3. on a matching route, refuses when `BindTenant` is set and the `tenant` submatch is not exactly `req.Tenant`, or when `RequireTenantQuery` is set and the key is absent.
- Add `AllowsToolCall(name string, args map[string]any, tenant string) bool`. For a bound scope, it applies the tool predicate and then requires every present `team` / `team_name` / `tenant` argument to equal `tenant`. Tools in `supportTenantTools`, the tools that take a tenant, must carry one. The MCP list tools whose tenant argument is optional (`mctl_list_services`, `mctl_list_workflows`, `mctl_list_incidents`, `mctl_list_domains`) therefore must name it.
- `support` scope:

```go
AgentScopeSupport: {
    Name: AgentScopeSupport, Agents: []string{"mctl-support"},
    BoundTenant: true, MintByTenantMember: true,
    DefaultTTL: 10 * time.Minute, MaxTTL: time.Hour,
    Tool: func(n string) bool { return IsReadTool(n) && supportTools[strings.TrimPrefix(n, "mctl_")] },
    Routes: append(append([]AgentScopeRoute(nil), mcpRoutes...),
        getRoute(`^/api/v1/whoami$`),
        tenantRoute(`^/api/v1/status/(?P<tenant>[^/]+)/[^/]+$`),
        tenantRoute(`^/api/v1/services/(?P<tenant>[^/]+)/[^/]+$`),
        tenantRoute(`^/api/v1/logs/(?P<tenant>[^/]+)/[^/]+$`),
        tenantRoute(`^/api/v1/resources/(?P<tenant>[^/]+)$`),
        listRoute(`^/api/v1/services$`, "team"),
        listRoute(`^/api/v1/workflows$`, "team"),
        listRoute(`^/api/v1/domains$`, "team"),
        listRoute(`^/api/v1/incidents$`, "tenant"),
        getRoute(`^/api/v1/workflows/[^/]+(/logs)?$`),   // tenant checked in handler
        getRoute(`^/api/v1/incidents/(summary|[^/]+)$`),  // tenant checked in handler
        getRoute(`^/api/v1/operations(/[^/]+)?$`),        // static catalog
        getRoute(`^/api/v1/platform-skills(/[^/]+)?$`),   // HasTenantAccess-filtered
    ),
},
```

  `supportTools` = whoami, get_service_status, list_services, get_service_logs, get_service_config, list_workflows, get_workflow_status, get_workflow_logs, get_resource_usage, list_incidents, get_incident, incident_summary, list_operations, get_operation, list_domains, list_platform_skills, read_platform_skill. A unit test asserts that every entry is `IsReadTool` and is a registered tool name.

### 2. Principal (`internal/auth/agent.go`, `oidc.go`)

- `AgentRun` gains `Tenant string` and `RequestedBy string` (the caller principal id). `NewAgentUser` copies them into new private fields `boundTenant` and `runRequestedBy`.
- `User.BoundTenant() (string, bool)` returns true only for an agent whose scope has `BoundTenant` and a non-empty tenant. `User.AgentRunRequestedBy() string` returns the caller principal id.
- `HasTenantAccess`: after the admin check, if `u.AgentScope()` has `BoundTenant`, return `tenant != "" && tenant == u.boundTenant`, and never fall through to groups. A scope that requires a tenant but resolves with an empty one admits nothing.

### 3. Mint (`internal/api/handlers_agent_run_tokens.go`)

- `agentRunTokenBody` gains `Tenant string json:"tenant,omitempty"`.
- `MintAgentRunToken` caller rule:
  - The body names a scope with `MintByTenantMember`. The caller must be a human: `!user.IsAgent()`, not `DelegatingAgent()`, not `IsService()`, not a bare `Surface()`. A surface-relayed human (`RelaySurface()`) is allowed, which is how S1 reaches it. The caller must also have `user.PrincipalID() != ""`.
  - Then the tenant check:
    - `body.Tenant` is required (400 `agent_scope_tenant_required`) and must exist (`GitReader`/tenant lookup used by `GetTenant`; 404 `tenant_not_found`).
    - `isAdmin := user.IsAdmin()`. Membership is `slices.Contains(user.Groups, body.Tenant)`. It is checked by group, not by `HasTenantAccess`, so that admin status is recorded separately.
    - If neither holds, audit and return 403 `agent_scope_tenant_forbidden`.
  - Otherwise the existing `isDirectService` rule stands unchanged, and a non-empty `Tenant` is refused with `agent_scope_tenant_unexpected`.
- TTL: default `scope.DefaultTTL`, cap `scope.MaxTTL` when set.
- `issuerOf(user)` already records the issuing principal. Pass `Tenant` and `RequestedBy = user.PrincipalID()` into `MintAgentRunTokenInput`. The audit `extra` gets `tenant`, `via_principal_id` and `admin_override`. The response gains `tenant`.
- `issueAgentRunToken` refuses a `BoundTenant` scope reached from `ExchangeAgentRunToken`, which has no tenant (the empty-tenant rule), so the exchange cannot mint an unbound support token.

### 4. Storage (`internal/workitems/agent_run_tokens.go`)

- Append to `agentRunTokenSchema`:
  `ALTER TABLE agent_run_tokens ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT '';`
  `ALTER TABLE agent_run_tokens ADD COLUMN IF NOT EXISTS via_principal_id TEXT NOT NULL DEFAULT '';`
- Add `Tenant` and `ViaPrincipalID` to `MintAgentRunTokenInput` and `AgentRunToken`. Update the INSERT and the resolver SELECT, and fill `auth.AgentRun.Tenant` and `RequestedBy`.

### 5. REST gate (`internal/api/agent_scope_gate.go`)

- Replace the `scope.AllowsRoute(...)` call with `scope.Allows(auth.AgentScopeRequest{..., Query: r.URL.Query(), Tenant: boundTenant})`. Add `bound_tenant` to the denial audit parameters.
- Shadow branch: if `scope.BoundTenant`, count `deny` with verdict label `shadow_unbound_tenant` and do not evaluate. A static token cannot be judged against a tenant it does not have.

### 6. Handlers whose tenant comes from data

- `GetWorkflow`: for `user.BoundTenant()`, refuse with 403 when the audit entry is missing (cron run) or its team is empty or different. The existing empty-team tolerance stays for other non-admins.
- `ListWorkflows`: for a bound principal, skip rows with `team == ""`. The gate already forces `team=` to equal the bound tenant, so this is defense in depth.
- `GetWorkflowLogs`, `GetIncident`, `IncidentSummary`, `ListIncidents` post-filter and the platform-skill access already go through `HasTenantAccess`. They become correct through section 2, and get dedicated tests.

### 7. MCP (`internal/mcp/agent_scope.go`)

- In `agentScopeMiddleware`, for a scoped agent, call `scope.AllowsToolCall(tool, req.GetArguments(), boundTenant)` instead of `AllowsTool` when `scope.BoundTenant`. On refusal, count it and return the `agent_scope_denied` tool error naming the offending argument. The REST layer is still behind it, so a tool that reaches REST with a different tenant is refused twice.

### Why this way

It reuses the one mechanism the issue points at: the server-held scope, the `agent_run_tokens` row, the gate and the middleware. The tenant becomes data on the token (like work item and execution), not a new principal type. Enforcement runs at three independent layers (MCP arguments, REST route and query, `HasTenantAccess`). Removing any single one still leaves another refusing in most paths, and each layer gets its own test that targets it in isolation.

## Alternatives

1. **Give the agent user `Groups = [tenant]` and rely on existing handler checks.** It is the smallest change, but every handler that tolerates an empty tenant (`GetWorkflow`, `ListWorkflows` rows) or that does not filter would leak. A list call without a filter would return whatever the handler gives a tenant member, with no route-level refusal. Rejected: it fails the "unfiltered list is refused" criterion and makes the agent indistinguishable from a human member.
2. **A new token type or principal kind for support (a separate auth path).** The issue explicitly rejects this. It would duplicate resolution, revocation and audit that `agent_run_tokens` already provides.
3. **Mint support tokens only by the direct service principal (mctl-support's static token), with a `tenant` field.** It keeps the mint rule unchanged, but the service would then be trusted to assert membership. The issue requires that the caller principal be a tenant member, checked by mctl-api. Rejected for this phase. The relayed-human path achieves it through the existing surface relay.
4. **Set `User.viaPrincipalID` to the human caller.** That would put the human in every audit `via_principal_id` automatically. It inverts the established meaning ("relaying actor", see `actorAndSubject`), and it trips `ViaPrincipalID() != ""` guards in unrelated handlers. Kept out. The caller lives on the token row instead (open question in requirements.md).

## Platform impact

- Migration: two additive `ADD COLUMN IF NOT EXISTS ... DEFAULT ''` statements run at startup. Existing rows read as unbound. No backfill is needed.
- Backward compatibility: the `investigate` scope, the unscoped tokens and the exchange are unchanged. `AllowsRoute` keeps its signature. `HasTenantAccess` changes only for principals whose scope has `BoundTenant`, and none exist before this change.
- Mint surface widens: humans can now call POST `/api/v1/agent-run-tokens`, but only for a `MintByTenantMember` scope. Every other scope still requires `isDirectService`. The route already has its own 120/min rate limit keyed on the subject.
- Resource impact: negligible (one query parse per request for scoped agents, two small columns).
- Risks and mitigations:
  - A future handler adds a tenant filter under a new key name. Mitigation: the generic `tenantQueryKeys` check, and `HasTenantAccess` as the backstop. A test enumerates the allowlisted routes against `router.go` to fail on drift.
  - A tool on the support list starts calling an unlisted REST route. The gate refuses it, which fails closed.
  - An admin mints for any tenant. Mitigation: `admin_override=true` in the audit, and the token itself is still tenant-bound.
  - A static token shadowing `support` is counted as unevaluable, not as allow.
