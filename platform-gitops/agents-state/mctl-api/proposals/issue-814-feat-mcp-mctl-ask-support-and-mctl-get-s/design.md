# Design: issue-814-feat-mcp-mctl-ask-support-and-mctl-get-s

## Current state

- MCP tools are defined as `toolXxx() (mcplib.Tool, server.ToolHandlerFunc)` methods on `*mcp.Server` and registered in `Server.NewMCPServer` (`internal/mcp/server.go`). Groups of related tools have their own files (`commerce.go`, `workitems.go`, `roadmap.go`, `usage.go`).
- Outbound calls use `s.apiGet` / `s.apiPostJSON` / `s.doRequest` (`internal/mcp/server.go`, "HTTP helpers"). They target `s.apiURL` (loopback in process) with `s.effectiveToken(ctx)`. That is the caller's raw token from `auth.TokenFromContext`, or `s.apiToken` in stdio mode (`cmd/mcp`). `s.httpClient` has a 30s timeout and `tracingTransport`. No existing tool calls a service other than mctl-api, and nothing in the repo speaks A2A (no A2A matches outside `internal/workitems`).
- Tenant-scoped MCP tools today rely on the REST API for the tenant check (`commerce.go` header comment: "Every call carries the caller's own token, so the tenant check lives in the API"). There is no mctl-api route for support, so S1d must check in the MCP layer. It has `auth.UserFromContext(ctx)` and `(*auth.User).HasTenantAccess` (`internal/auth/oidc.go:245`). That method admits admins, admits a tenant-bound agent run only for its bound tenant, and otherwise checks groups. In stdio mode there is no user in the context. `mctl_whoami` shows that `/api/v1/whoami` returns `groups`, `isAdmin` and `boundTenant`.
- Tenant argument parsing: `commerceTenantPath` / `strictStringArg` (`internal/mcp/commerce.go`) trim, lowercase and refuse anything that is not one path segment.
- Middleware chain (`NewMCPServer`): owner-only filter, tracing, `agentReceiptMiddleware`, `agentScopeMiddleware`, `recoverToolPanic`.
  - `agentScopeMiddleware` (`internal/mcp/agent_scope.go`) limits a scoped run token to its scope's tools. The `support` scope's list is `supportTools` in `internal/auth/agent_scope.go:139`, which holds reads only.
  - `agentReceiptMiddleware` requires an approval receipt for every tool in `governedAgentTools` (`internal/mcp/agent_receipt_gate.go:159`). A test fails if a registered tool is in neither `governedAgentTools` nor `ungovernedAgentTools`, unless it is a read verb (`isAgentReadTool`). `AgentReceiptGatePolicyVersion` ("mctl-api/agent-receipt-gate/v1") must change when the set changes.
- Hints and portal:
  - `internal/mcp/annotations_test.go` `recordedHints` records readOnly/destructive/idempotent for every tool. `server_test.go:67` and `annotations_test.go:139` require the registered tool count to equal `len(recordedHints)`.
  - `docs/portal-allowlist.json` needs an entry, with `enabled` and a `reason` of at least 40 tool-specific characters, for every registered tool.
  - `internal/mcp/portal_allowlist_test.go` `mutatingOnPortal` (line 100) must name any enabled tool that is not recorded read-only. The issue says this map is in `annotations_test.go`. It is not.
- `/mcp` is mounted in `internal/api/router.go:1041-1048` (`r.Post("/mcp", mcpH.ServeHTTP)`). The process's `http.Server` uses `WriteTimeout: mctlapi.ServerWriteTimeout` (`cmd/api/main.go:1191`), which is 30s (`internal/api/handlers_roadmap_wave.go:492`). A 60s synchronous wait would be cut off at 30s if nothing changes.
- `cmd/api/main.go:950` builds `mctlmcp.NewInProcessServer`. Optional features are configured from env with `envOr` / `parseDuration` and the `Set...` setters on `*mcp.Server` (`SetTenantOwnerChecker`, `SetAgentReceiptGate`, `SetScopedCallAuditor`).

Deployed state checked:
- `mctl_get_service_status(team=admins, service=mctl-support)`: ArgoCD app `admins-mctl-support` is Healthy and Synced, imageTag `0.2.1`, host `support.mctl.ai`, port 8080, base-service, hasDatabase true.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`: replicaCount 2 with a shared Postgres task store ("a task sent to one replica is readable ... through the other"), `SUPPORT_ALLOWED_TENANTS: namax66` (pilot allowlist), `MCTL_API_URL` / `MCTL_AUTH_ISSUER: https://api.mctl.ai`. Spend caps are left at service defaults (task 0.50, tenant 10, workspace 50 USD per UTC month). The service "mints its tenant-bound run token from the caller's bearer through mctl-api".
- `$MCTL_GITOPS_ROOT/bootstrap/values.yaml:566`: `support.mctl.ai: [admins]` is a reserved platform host.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api's deployed env is set here (for example `AGENT_RUN_EXCHANGE_AUDIENCE` at line 293). It has no support-related env today.
- Not observed: the request/response timeouts of the Cloudflare MCP portal and of the ingress in front of api.mctl.ai, and mctl-support's exact `metadata.tenant` placement. Both are recorded under Open questions in requirements.md.

## Proposed solution

### 1. New file `internal/mcp/support.go`

- `type SupportConfig struct { BaseURL string; Wait, PollInterval, RequestTimeout time.Duration }` and `func (s *Server) SetSupportConfig(c SupportConfig)`. It is stored in an `atomic.Pointer` like the other setters. An unset config makes both tools answer `support agent is not configured on this server`. They stay registered, so the tool count is stable.
- Its own HTTP client: `tracingTransport` over `http.DefaultTransport`, `CheckRedirect` returning `http.ErrUseLastResponse` (a 3xx then fails as non-2xx, so the bearer never follows a redirect), and a per-request timeout of `RequestTimeout` (default 15s). It is separate from `s.httpClient`, whose 30s timeout and error collapsing (`doRequest`) do not fit.
- `func (s *Server) supportDo(ctx, method, path string, body any) (*a2aTask, *a2aMessage, error)`:
  - It sets `A2A-Version: 1.0`, `Accept`/`Content-Type: application/json` and `Authorization: Bearer <effectiveToken(ctx)>`. An empty token is refused.
  - It reads the body with a bound of 1 MiB.
  - Non-2xx returns `fmt.Errorf("mctl-support returned %d: %s", code, short body or error field)`.
  - It decodes `{"task":{...}}` or `{"message":{...}}`, or a bare Task for `GET /tasks/{id}`. Anything else returns `fmt.Errorf("mctl-support response could not be decoded: %w", err)`.
  - Transport errors are wrapped. Errors are logged with `slog` and returned to the caller as tool errors. None is ever collapsed into an empty answer.
- Minimal A2A 1.0 types (unexported): Task `{id, contextId, status{state, message, timestamp}, artifacts[{artifactId, name, parts[]}], metadata}`, Message `{messageId, role, contextId, taskId, parts[], metadata}`, Part `{text?, data?, mediaType?}`. `normalizeState` strips an optional `TASK_STATE_` prefix and uppercases. That accepts both the proto-JSON enum form and short forms. Terminal states are COMPLETED, FAILED, CANCELED and REJECTED. Interrupted states are INPUT_REQUIRED and AUTH_REQUIRED. Any other value, unknown values included, counts as still running, and is reported verbatim if the wait expires.
- `renderSupportAnswer(task|message) supportAnswer` returns `{task_id, context_id, state, terminal, text, result, reason}`. `text` joins all text parts of the artifacts, or of the message. `result` is the first data part's object, passed through unchanged. That object is the structured result: summary, classification, evidence, recommended_actions and escalation_id. `reason` is the text of `status.message` for non-COMPLETED states. The tool returns it as indented JSON text, matching how other tools return API bodies. This one function is also what the parity test compares.

### 2. `mctl_ask_support(tenant, question, context_id?)`

- Annotations: title "Ask the support agent", readOnly=false, destructive=false, idempotent=false.
- The description states that it creates a task, spends the tenant's model budget, waits up to the configured bound, and is followed up with `mctl_get_support_task`.
- Steps:
  1. Parse `tenant` with the `commerceTenantPath` normalization (factored into `normalizeTenantArg`). Require a non-empty `question` (bounded to 8 KiB). `context_id` is optional and must be a string.
  2. Tenant check, in `s.supportTenantAllowed(ctx, tenant)`. If there is a user in the context, it uses `user.HasTenantAccess(tenant)`. Otherwise (stdio) it calls `/api/v1/whoami` and allows the tenant only when `isAdmin` is true, `boundTenant == tenant`, or `groups` contains it. A whoami error refuses the call. A refusal returns `tenant_forbidden: you are not a member of tenant <t>` and sends nothing.
  3. `POST /message:send` with `{"message":{"messageId":uuid,"role":"ROLE_USER","parts":[{"text":question}],"contextId":ctx?},"configuration":{"blocking":false},"metadata":{"tenant":tenant}}`. Request-level `metadata.tenant` is to be confirmed against mctl-support 0.2.1 (see Open questions).
  4. If the reply is a message, render it and return. If the reply is a task, poll `GET /tasks/{id}` every `PollInterval` (default 2s) under `context.WithTimeout(ctx, Wait)` until the task is terminal or interrupted. The poll uses the same bearer. Because there are two replicas with a shared store, which replica answers does not matter.
  5. Results: COMPLETED returns the rendered answer as a normal result. FAILED, REJECTED and CANCELED return `mcplib.NewToolResultError` with the rendered JSON, whose state and reason are visible. Interrupted states return a normal result with state, reason and context id. If the deadline passes, the call returns a normal result with `{task_id, context_id, state, terminal:false, note:"still running; call mctl_get_support_task"}`. A transport or HTTP error during polling is a tool error that still names the task id, so the client can retry with `mctl_get_support_task`. If the caller's own context is cancelled, the handler returns its error.

### 3. `mctl_get_support_task(id)`

- Annotations: readOnly=true, destructive=false, idempotent=false. The name uses the `get_` read verb, so it is ungoverned for the receipt gate and counts as a read for agent scopes. It is still not added to `supportTools`.
- `id` must be non-empty, one path segment, and at most 256 bytes. The tool sends one `GET /tasks/{url.PathEscape(id)}` and renders the result with the same state and failure rules as above. There is no tenant argument. mctl-support's own check on the caller's bearer decides visibility, and a task the caller may not see answers as mctl-support answers (for example a 404). That answer is returned as a tool error.

### 4. Wiring and configuration (`cmd/api/main.go`, `cmd/mcp/main.go`)

- Env vars:
  - `SUPPORT_A2A_URL`: for example `https://support.mctl.ai`. Empty means not configured. Startup refuses a non-absolute URL, and refuses `http://` unless the host is loopback, which tests need.
  - `SUPPORT_ASK_WAIT`: default 60s, allowed range 0 to 90s. 0 means return right after send.
  - `SUPPORT_POLL_INTERVAL`: default 2s, minimum 500ms.
- These are applied through `mcpSrv.SetSupportConfig(...)`. The same is read in `cmd/mcp/main.go`, so the stdio binary also works.
- Write deadline: `api.Options` gets `MCPWriteTimeout time.Duration`. In `router.go`, the `/mcp` POST handler is wrapped so that, when that value exceeds `ServerWriteTimeout`, it calls `http.NewResponseController(w).SetWriteDeadline(time.Now().Add(opts.MCPWriteTimeout))` before `mcpH.ServeHTTP`. `main.go` sets the value to `SUPPORT_ASK_WAIT + 15s` when support is configured, and leaves it 0 otherwise, which keeps today's behaviour. Only `/mcp` is affected, and `ReadTimeout` is unchanged.

### 5. Policy records

- `internal/mcp/annotations_test.go` `recordedHints`: add `mctl_ask_support {readOnly:false, destructive:false, idempotent:false}` and `mctl_get_support_task {readOnly:true, destructive:false, idempotent:false}`.
- `internal/mcp/portal_allowlist_test.go` `mutatingOnPortal`: add `"mctl_ask_support": "creates a support task in mctl-support and spends the tenant's model budget (task cap 0.50 USD)"`.
- `docs/portal-allowlist.json`:
  - `mctl_ask_support`: enabled true, with a reason that it sends the caller's own bearer to mctl-support, is tenant-checked in mctl-api and again in mctl-support, creates a task and spends budget, and returns diagnosis text about the caller's own tenant.
  - `mctl_get_support_task`: enabled true, with a reason that it is read-only, forwards the caller's own bearer, and mctl-support decides visibility.
- `internal/mcp/agent_receipt_gate.go`: add `mctl_ask_support` to `governedAgentTools`. It is not a read verb, and mctl-agents' default policy already requires approval for it. Bump `AgentReceiptGatePolicyVersion` to `.../v2`, as the constant's comment requires.
- `supportTools` in `internal/auth/agent_scope.go` is left unchanged. That keeps the support agent from recursing into itself through mctl-api.

### 6. Docs

- New `docs/support-agent-mcp.md` covering: the two tools, the binding, bearer passthrough, the tenant check, the wait semantics, the failure rules, and the env vars. Link it from `docs/support-agent-scope.md`.
- A follow-up mctl-gitops PR adds `SUPPORT_A2A_URL: https://support.mctl.ai` to `bootstrap/templates/mctl-platform/mctl-api.yaml`. Until it merges, the tools answer "not configured".

## Alternatives

1. **Asynchronous only (ask returns the task id immediately).** This is simplest and avoids the write-timeout change. The issue's amendment 2 rejects it: most questions should take one tool call. `SUPPORT_ASK_WAIT=0` keeps it available as an operator setting.
2. **A REST route in mctl-api (`POST /api/v1/support/...`) that the MCP tool calls over loopback, like other tools.** This would reuse the API's tenant check and audit. But it adds a second public surface for the same function, and it would hold a REST request open for 60s inside the 30s server write timeout. Dropped as unnecessary for a thin adapter. It can be added later if a non-MCP surface needs it.
3. **A service credential or a mctl-api-minted `support` run token instead of the caller's bearer.** This is explicitly forbidden by amendment 1 ("mctl-api adds no authority, no service credential"). mctl-support already mints its own tenant-bound run token from the caller's bearer.
4. **JSON-RPC `message/send`.** mctl-support 0.2.1 does not serve it (amendment).

## Platform impact

- **Migrations:** none. No state is stored in mctl-api.
- **Backward compatibility:** two new tools. The tool count changes, and `server_test.go` / `annotations_test.go` are updated together with it. Receipt gate audit rows carry the new policy version `v2`. With support unconfigured, `/mcp` behaviour is unchanged. When configured, the `/mcp` write deadline grows to 75s by default.
- **Resources:** each in-flight `mctl_ask_support` call holds one goroutine and one `/mcp` connection for up to the wait, polling every 2s, which is about 30 small GETs at most. mctl-support carries the model cost and has its own spend caps. mctl-api's per-pod rate limiters on `/mcp` still apply.
- **Risks and mitigations:**
  - *Bearer leakage to another host:* the base URL is fixed by operator config, never by caller input. Redirects are not followed. `id` is path-escaped and limited to one segment.
  - *Failure read as an empty answer:* every non-2xx response, decode failure and transport error is a tool error. FAILED, REJECTED and CANCELED are tool errors with their reason. There are tests for each.
  - *Tenant check bypass:* mctl-api checks first, and a test asserts zero upstream requests on refusal. mctl-support checks again, and its test lives in mctlhq/mctl-support.
  - *Proxy timeouts shorter than the wait:* the wait is capped at 90s and configurable. On timeout the client still gets the task id, and `mctl_get_support_task` recovers the answer.
  - *Recursion:* the support run scope cannot call `mctl_ask_support`, and a test asserts this.
  - *Token passthrough:* deliberate, and limited to one operator-configured host that already trusts api.mctl.ai as issuer. It is documented in `docs/support-agent-mcp.md`.
