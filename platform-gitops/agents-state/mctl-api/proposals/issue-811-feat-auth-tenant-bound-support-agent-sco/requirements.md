# Tenant-bound support agent run scope (support S0a)

## Context

Issue mctlhq/mctl-api#811 is phase S0a of the tenant support agent epic (mctlhq/.github#243). The future `mctl-support` service (S1) answers questions for one tenant. It must never hold more authority than that tenant. Today the only scoped run token is `investigate` (`internal/auth/agent_scope.go`). That scope has `ReadAllTenants: true`, and `User.HasTenantAccess` in `internal/auth/oidc.go` admits every tenant for it. Only the direct service principal or the pod ServiceAccount exchange can mint a scoped token (`internal/api/handlers_agent_run_tokens.go`, `internal/api/handlers_agent_run_token_exchange.go`). No token exists that can read one tenant and nothing else, and a tenant member cannot request a token for their own tenant.

This proposal adds a server-defined `support` scope with a new tenant binding. The scope is minted through the existing run-token mint path. It is enforced by the existing REST gate (`internal/api/agent_scope_gate.go`) and the existing MCP middleware (`internal/mcp/agent_scope.go`). It is also enforced by `HasTenantAccess`, which protects the handlers that read the owning tenant from the data rather than from the URL. No new authentication path is built.

## User stories

- AS the `mctl-support` service I WANT a run token that reads exactly one tenant SO THAT a support answer cannot leak another tenant's data, even if the model is prompt-injected.
- AS a tenant member I WANT support to act with no more authority than my own tenant SO THAT asking for help never widens anyone's access.
- AS a platform admin I WANT to mint a support token for any tenant, and have that recorded, SO THAT I can triage on a tenant's behalf with an audit trail.
- AS a security reviewer I WANT every refusal path covered by a test that fails when its check is removed SO THAT the boundary cannot regress silently.

## Acceptance criteria (EARS)

Scope definition
- THE SYSTEM SHALL define an agent scope named `support` in `internal/auth/agent_scope.go` with `ReadAllTenants: false`, `BoundTenant: true` and a tool predicate that admits only the explicit support tool list, each entry of which is also a read under `auth.IsReadTool`.
- THE SYSTEM SHALL limit the `support` route list to GET on: `/api/v1/whoami`, `/api/v1/status/{tenant}/{app}`, `/api/v1/services` (tenant filter required), `/api/v1/services/{tenant}/{app}`, `/api/v1/logs/{tenant}/{app}`, `/api/v1/workflows` (tenant filter required), `/api/v1/workflows/{name}`, `/api/v1/workflows/{name}/logs`, `/api/v1/resources/{tenant}`, `/api/v1/incidents` (tenant filter required), `/api/v1/incidents/summary`, `/api/v1/incidents/{id}`, `/api/v1/operations`, `/api/v1/operations/{name}`, `/api/v1/domains` (tenant filter required), `/api/v1/platform-skills`, `/api/v1/platform-skills/{name}`, and the MCP transport `/mcp`. The S0b diagnostics routes are added when S0b defines them.

Mint
- WHEN a mint request names scope `support` THE SYSTEM SHALL require a non-empty `tenant` that names an existing tenant, and SHALL otherwise refuse with 400 `agent_scope_tenant_required` or 404 `tenant_not_found`.
- WHEN a mint request names a tenant for a scope without `BoundTenant` THE SYSTEM SHALL refuse it with 400 `agent_scope_tenant_unexpected`.
- WHEN a human principal, acting directly or relayed by a registered surface, mints a `support` token for a tenant whose group it holds THE SYSTEM SHALL mint the token bound to that tenant and record the caller's principal id as `via_principal_id`.
- IF the caller is not a member of the named tenant and is not a platform admin THEN THE SYSTEM SHALL refuse with 403 `agent_scope_tenant_forbidden` and write one audit entry, and SHALL NOT mint a token.
- WHEN a platform admin mints a `support` token for a tenant it is not a member of THE SYSTEM SHALL mint it and record `admin_override=true` in the mint audit entry.
- IF the caller is an agent run token, a delegated agent request, or the direct service principal THEN THE SYSTEM SHALL refuse to mint a `support` token with 403 `requester_forbidden`.
- WHEN a `support` token is minted without `ttl_seconds` THE SYSTEM SHALL give it a 10-minute TTL. IF `ttl_seconds` exceeds the scope maximum (1 hour) THEN THE SYSTEM SHALL refuse with 400 `invalid_ttl`.
- THE SYSTEM SHALL bind the token to `execution_id` (the support task's WorkItemExecution), persist `tenant` and `via_principal_id` on the `agent_run_tokens` row, and return `tenant` in the mint response.

Enforcement (REST and MCP)
- WHILE a request carries a `support` token THE SYSTEM SHALL admit a route only if it is in the scope's route list. Every tenant path segment SHALL equal the bound tenant exactly.
- WHILE a request carries a `support` token THE SYSTEM SHALL refuse any request whose query parameters `team`, `tenant`, `team_name` or `namespace` hold a value other than the bound tenant, or appear more than once.
- WHEN a `support` token calls a list route marked tenant-filter-required without the tenant filter THE SYSTEM SHALL refuse it with 403 `agent_scope_denied`, never answer with rows unfiltered.
- WHILE a principal holds a tenant-bound scope THE SYSTEM SHALL return true from `User.HasTenantAccess(t)` only when `t` equals the bound tenant. An empty or unknown tenant SHALL never be treated as "platform".
- WHEN a handler reads the owning tenant from the data (`GET /workflows/{name}`, `GET /workflows/{name}/logs`, `GET /incidents/{id}`, `GET /incidents/summary`) for a tenant-bound principal THE SYSTEM SHALL return only data whose tenant equals the bound tenant, and SHALL refuse a record with no identifiable tenant.
- WHEN a `support` token calls an MCP tool outside its tool list, or calls a tool whose `team`, `team_name` or `tenant` argument differs from the bound tenant or is missing for a tenant-taking tool, THE SYSTEM SHALL refuse with an `agent_scope_denied` tool error before the handler runs.
- WHEN any of these refusals happens THE SYSTEM SHALL increment `mctl_agent_scope_decisions_total{scope="support",verdict="deny"}` and, for REST, write one `agent_scope.denied` audit entry that includes `bound_tenant`.
- WHILE the `investigate` scope is in use THE SYSTEM SHALL keep its behaviour byte-for-byte: no tenant binding, `ReadAllTenants: true`, unchanged routes.

Verification
- Each refusal test (another tenant's read, an unfiltered list, a write tool, a route outside the allowlist, minting for a non-member tenant) SHALL fail when its check is removed. The PR SHALL record this mutation check.
- S0a is done when the unit, gate, handler and MCP tests (T1-T16) pass and the mutation check (T17) is recorded. The live probe is not an S0a criterion: it moves to S1a (mctlhq/.github#245), see Decisions.

## Out of scope

- The S0b diagnostics routes (added to the allowlist by S0b itself).
- The S0c read audit of every admitted support read.
- The `mctl-support` service (S1a) and its agent definition in the registry.
- Migrating other agents off `MCTL_TOKEN` (mctl-agents#737).
- A tenant binding through the pod ServiceAccount exchange (`ExchangeAgentRunToken`). The k8s binding carries no tenant today. The support scope is minted only by the human-caller mint path in this phase.
- Shadow-mode (`X-Mctl-Agent-Scope-Shadow`) observation of the `support` scope. A shadowing static token carries no bound tenant, so shadowing `support` is refused.

## Decisions (owner amendment, 2026-10-26)

- Pilot tenant: `namax66` (decision D9 in mctlhq/.github#243). The probe stays parameterised by tenant.
- Live probe: moved to S1a (mctlhq/.github#245). Minting a `support` token needs the `mctl-support` agent definition in the registry and an existing WorkItemExecution for `execution_id`. Neither exists until S1a, so the probe cannot run after the S0a deploy. S1a runs it against `namax66` (200) and another tenant (403 `agent_scope_denied`), over REST and MCP.
- Support task model: each support task is a WorkItemExecution (`we_...`). This is a decision, not an assumption. S1a must create one work item execution per support task, so the existing execution check and terminal-phase revocation in `internal/workitems/agent_run_tokens.go` apply. No `WithoutExecution` mint path is added for `support`.
- `via_principal`: the caller is stored as `via_principal_id` on the `agent_run_tokens` row and exposed as `User.AgentRunRequestedBy()`. `User.viaPrincipalID` is not set, so its "relaying actor" meaning is unchanged. Which audit column carries the human for admitted support reads is decided in S0c (mctlhq/mctl-api#813), not here.

## Open questions

- Agent name: the scope's `Agents` list needs the registered name of the support agent. This proposal assumes `mctl-support`. If the registry has a different definition name at S1a, change one string.
- Maximum TTL for `support`: the issue gives only the 10-minute default. This proposal caps it at 1 hour.
- `/api/v1/tenants/{name}` and `/api/v1/previews` are not in the issue's list and are excluded. Add them if S1 needs tenant metadata.
