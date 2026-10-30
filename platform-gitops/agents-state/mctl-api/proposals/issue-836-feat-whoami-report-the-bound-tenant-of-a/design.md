# Design: issue-836-feat-whoami-report-the-bound-tenant-of-a

## Current state
- `internal/api/handlers_read.go` `(*Handlers).Whoami` (lines ~40-75) reads `auth.UserFromContext`, de-duplicates `user.Groups`, adds `admins` to `namespaces` for admins, and writes `map[string]interface{}{"id","groups","isAdmin","namespaces"}` via `writeJSON`. A comment says the response is informational: "nothing authorizes against it".
- `internal/auth/agent.go` `(*User).BoundTenant()` (line ~141) returns `(boundTenant, true)` only when the user is an agent, has a non-empty `boundTenant`, and its `AgentScope()` resolves with `BoundTenant: true`. In every other case it returns `("", false)`. Agent users are built with `auth.NewAgentUser(name, auth.AgentRun{Scope, Tenant, ...})`.
- `internal/auth/agent_scope.go`: scope `AgentScopeSupport` (`BoundTenant: true`, agent `mctl-support`) allows `getRoute(^/api/v1/whoami$)` and the `whoami` tool (`supportTools`). Scope `AgentScopeInvestigate` also allows whoami but is not tenant-bound (`ReadAllTenants: true`).
- Enforcement of the bound tenant: `internal/api/agent_scope_gate.go` (passes `Tenant: boundTenant` into `scope.Allows`), `internal/mcp/agent_scope.go` `agentScopeMiddleware` (`scope.AllowsToolCall(tool, args, boundTenant)`), `workflowRowVisible` in `handlers_read.go`.
- `internal/mcp/server.go` `(*Server).toolWhoami` (lines ~383-419) calls `s.apiGet(ctx, "/api/v1/whoami")`. On error it returns `NewToolResultError("Failed to get identity: " + s.redactUpstream(err))`. It then decodes into an anonymous struct `{ID, Groups, IsAdmin, Namespaces}` with `_ = json.Unmarshal(body, &identity)`, discarding the error, and prints `User/Admin/Teams/Accessible namespaces`, prefixed by `Authenticated to <displayURL>` when available.
- Tests: `internal/api/handlers_whoami_test.go` (helper `callWhoami`, struct `whoamiResponse` without `boundTenant`). `internal/mcp/whoami_test.go` (helper `callWhoamiViaMCP`, which drives `tools/call` through `NewMCPServer().HandleMessage` against an `httptest` backend via `NewInProcessServer(port, publicURL)`). `e2e/e2e_test.go` checks only that `User`/`Teams` appear.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/*/mctl-api`: no match. mctl-api is not deployed as a tenant service in this checkout, so its deployed config was not observed. The change is code-only and does not depend on deployed config.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support`: present. This confirms the bound-token consumer named in the issue is deployed in tenant `admins`. Its values were not read, because they are not needed for this change.
- No mctl MCP tool calls were made. Nothing in this change depends on runtime state.

## Proposed solution
1. REST handler (`Whoami`): build the response map as today, then add the key only for bound principals:
   ```go
   resp := map[string]interface{}{"id": user.ID, "groups": groups, "isAdmin": user.IsAdmin(), "namespaces": namespaces}
   if t, ok := user.BoundTenant(); ok {
       resp["boundTenant"] = t
   }
   writeJSON(w, http.StatusOK, resp)
   ```
   `BoundTenant()` is the single source of truth, so whoami reports exactly the tenant the gates enforce. Extend the handler comment: `boundTenant` is informational, and enforcement stays in `BoundTenant()` and the scope gates. `namespaces`/`groups` are untouched.
2. MCP tool (`toolWhoami`):
   - Add `BoundTenant string \`json:"boundTenant"\`` to the decode struct.
   - Replace `_ = json.Unmarshal(...)` with an error check that returns `mcplib.NewToolResultError("Failed to read identity: upstream whoami response could not be decoded")`, plus an `slog.Error` with the decode error. Do not echo the body, which keeps the redaction posture of the existing error path.
   - After the existing four lines, append `"\nBound tenant: " + identity.BoundTenant` when it is non-empty. Output for unbound callers stays byte-identical.
   - Update the description to say: "Returns your user ID, team memberships, admin status, accessible namespaces, and, for a tenant-bound agent token, its bound tenant. A tenant-bound token can act only on that tenant; pass it as team/tenant to other tools."
3. No router, scope, or auth change. The tool count is unchanged, so the `server_test.go` count is unaffected.

## Alternatives
- **Add the bound tenant to `namespaces`/`groups`.** Rejected. The issue explicitly leaves this undecided, and it would change the meaning of existing fields for all consumers. Some code paths treat groups as tenant memberships, so the change carries authorization-adjacent risk.
- **Always emit `boundTenant` (empty string or null for unbound).** Rejected. The issue requires the field to be omitted so existing callers see no change, and an empty value could read as "bound to nothing".
- **Switch to a typed response struct with `omitempty`.** Workable, but a larger diff that touches all keys of a stable response. The conditional map key gives the same wire result with minimal change. It can be revisited if whoami grows further.
- **Compute the bound tenant in the MCP layer from context.** Rejected. `mctl_whoami` reads through the REST API (`apiGet`), and keeping the REST response as the single source keeps REST and MCP consistent.

## Platform impact
- No migrations, config, or Helm changes. Backward compatible: an additive, conditional JSON key and an additive text line, both shown only to bound agent tokens.
- Information exposure: the bound tenant is already known to the token's minter and is what the token can access. Revealing it to the token holder grants nothing new.
- Behaviour change: a malformed 2xx whoami body now yields a tool error instead of an empty identity. This is the intended fix. The risk is negligible because the handler always writes valid JSON.
- Risks: tool description text changes, so any docs or snapshot that embeds the description may need an update. A grep found the text only in `internal/mcp/server.go`.
