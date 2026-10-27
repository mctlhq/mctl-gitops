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
- Not observed: the request/response timeouts of the Cloudflare MCP portal and of the ingress in front of api.mctl.ai. This is recorded under Open questions in requirements.md.

### Confirmed mctl-support 0.2.1 wire contract (amendment 2026-10-27)

Checked against the mctlhq/mctl-support source at commit `1784f71` (the 0.2.1 release) and the A2A SDK it pins, `a2a-sdk[http-server,sql,postgresql]==1.2.3` (`pyproject.toml`, `uv.lock`). Generic A2A documentation was not used as a source.

- **Where the answer is.** The agent executor (`src/mctl_support/agent/executor.py`, the success path after the tool loop) completes a task with one `TaskStatusUpdateEvent` whose `status.state` is `TASK_STATE_COMPLETED` and whose `status.message` (role `ROLE_AGENT`) has exactly two parts, in this order: a text part (`SupportResult.to_text()`: the summary line, then one `- <action>` line per recommended action) and a data part (`SupportResult.to_data()`: `summary`, `classification`, `evidence[{source, summary}]`, `recommended_actions[]`, `escalation_id` (string or null), `dropped_unsupported_evidence` (int)). mctl-support emits **no artifacts**: the word does not occur in `src/`. FAILED, REJECTED and CANCELED carry their reason as a single text part in `status.message`. `Task.history` holds the conversation, including the caller's own question, and is never an answer.
- **The defect this amendment fixes.** The previous design read the answer text from `artifacts` and fell back to the message only for a direct-message reply. Against 0.2.1 that yields an empty `text` and no `result` for every COMPLETED task, which is a successful-looking empty answer: exactly the "failure read as absence" this proposal forbids.
- **The non-blocking flag.** `SendMessageConfiguration` in a2a-sdk 1.2.3 has `accepted_output_modes`, `task_push_notification_config`, `history_length` and `return_immediately` (proto-JSON `returnImmediately`). **There is no `blocking` field.** The REST dispatcher (`a2a/server/routes/rest_dispatcher.py`, `message:send` handler) decodes the body with `Parse(body, params, ignore_unknown_fields=True)`, so the previous design's `"configuration":{"blocking":false}` was silently dropped and every send blocked until a terminal state. (`blocking` exists only in the v0.3 compatibility layer, `a2a/compat/v0_3/conversions.py`, which maps it to `return_immediately = not blocking`; mctl-support does not serve v0.3.)
- **Send semantics with the flag.** `DefaultRequestHandlerV2.on_message_send` (`a2a/server/request_handlers/default_request_handler_v2.py`) returns the first `Task` event when `return_immediately` is set; the executor keeps running in the background and the result is read with `GET /tasks/{id}`. Without the flag it returns only at a terminal or interrupted state. mctl-support's `SupportRequestHandler` overrides `on_message_send` only for admission and then calls the SDK handler, so the flag is honoured.
- **Duplicate protection exists but is not relied on.** `SupportRequestHandler.on_message_send` (`src/mctl_support/handler.py`) admits each request by `messageId`: a repeated `messageId` with identical content returns the original task (or claims an orphaned admission), different content is refused, and a repeat that arrives before the original produced a task fails with "the original request has not produced a task yet; retry". This design does not resend automatically (section 2, step 4), so it does not depend on that behaviour.
- **Tenant placement.** `admission.requested_tenant_from_body` reads request-level `metadata.tenant` first, then `message.metadata.tenant`. Request-level `metadata.tenant` is correct. This closes the earlier open question.
- **Shapes.** `message:send` returns `SendMessageResponse`, i.e. exactly one of `{"task":{...}}` or `{"message":{...}}`. `GET /tasks/{id}` returns a bare `Task`. States are proto-JSON enum names (`TASK_STATE_SUBMITTED`, `..._WORKING`, `..._COMPLETED`, `..._FAILED`, `..._CANCELED`, `..._INPUT_REQUIRED`, `..._REJECTED`, `..._AUTH_REQUIRED`); roles are `ROLE_USER` / `ROLE_AGENT`. A `Part` carries exactly one of `text`, `raw`, `url` or `data` (a `google.protobuf.Value`), plus optional `metadata`, `filename` and `mediaType`.

## Proposed solution

### 1. New file `internal/mcp/support.go`

- `type SupportConfig struct { BaseURL string; Wait, PollInterval, RequestTimeout time.Duration }` and `func (s *Server) SetSupportConfig(c SupportConfig)`. It is stored in an `atomic.Pointer` like the other setters. An unset config makes both tools answer `support agent is not configured on this server`. They stay registered, so the tool count is stable.
- Its own HTTP client: `tracingTransport` over `http.DefaultTransport`, `CheckRedirect` returning `http.ErrUseLastResponse` (a 3xx then fails as non-2xx, so the bearer never follows a redirect), and **no `http.Client.Timeout`**. Every request takes its deadline from its context instead (section 2, "Wait budget"). `RequestTimeout` (default 15s) only caps a single `GET /tasks/{id}` poll, and never extends past the budget. It is separate from `s.httpClient`, whose fixed 30s timeout and error collapsing (`doRequest`) do not fit.
- `func (s *Server) supportDo(ctx, method, path string, body any) (*a2aTask, *a2aMessage, error)`:
  - It sets `A2A-Version: 1.0`, `Accept`/`Content-Type: application/json` and `Authorization: Bearer <effectiveToken(ctx)>`. An empty token is refused.
  - It reads the body with a bound of 1 MiB.
  - Non-2xx returns `fmt.Errorf("mctl-support returned %d: %s", code, short body or error field)`.
  - It decodes `{"task":{...}}` or `{"message":{...}}`, or a bare Task for `GET /tasks/{id}`. Anything else returns `fmt.Errorf("mctl-support response could not be decoded: %w", err)`.
  - Transport errors are wrapped. Errors are logged with `slog` and returned to the caller as tool errors. None is ever collapsed into an empty answer.
- Minimal A2A 1.0 types (unexported): Task `{id, contextId, status{state, message, timestamp}, artifacts[{artifactId, name, parts[]}], history[], metadata}`, Message `{messageId, role, contextId, taskId, parts[], metadata}`, Part `{text?, raw?, url?, data? (json.RawMessage), mediaType?, filename?, metadata?}`. `history` is decoded only so that tests can prove it is ignored. `normalizeState` strips an optional `TASK_STATE_` prefix and uppercases. That accepts both the proto-JSON enum form and short forms. Terminal states are COMPLETED, FAILED, CANCELED and REJECTED. Interrupted states are INPUT_REQUIRED and AUTH_REQUIRED. Any other value, unknown values included, counts as still running, and is reported verbatim if the wait expires.
- `renderSupportAnswer(task|message) (supportAnswer, error)` implements the answer contract below. It returns `{task_id, context_id, state, terminal, answer_source, text, result, additional_data, reason}`, which the tool returns as indented JSON text, matching how other tools return API bodies. This one function is used by both tools and by the parity test.

#### Answer contract (amendment 2026-10-27)

A **source** is an ordered list of parts. The candidate sources are, in priority order:

1. `task.status.message.parts` (`answer_source: "status_message"`). This is the primary source and is where mctl-support 0.2.1 puts the answer.
2. The parts of `task.artifacts`, flattened in artifact order and then part order (`answer_source: "artifacts"`). This is a fallback only.

A direct-message reply to `message:send` has one source, `message.parts` (`answer_source: "message"`). `task.history` is never a source.

A source is **meaningful** when it contains at least one text part whose text is non-empty after trimming whitespace, or at least one data part whose value is a JSON object. `raw`, `url` and file parts, empty or whitespace-only text, and data parts that are not objects (null, string, number, array) do not make a source meaningful and are never rendered.

For a COMPLETED task:

- The **chosen source** is `status_message` if it is meaningful, otherwise `artifacts` if that is meaningful. The two are never mixed: when `status_message` is chosen, artifacts are not read at all, so the same text present in both is not duplicated.
- `text` is every text part of the chosen source whose trimmed text is non-empty, in part order, each kept verbatim (not trimmed), joined with a single `"\n"`.
- `result` is the value of the **first** data part of the chosen source whose value is a JSON object, passed through byte-for-byte as `json.RawMessage`: no field is renamed, dropped or defaulted. Further object-valued data parts of the same source are returned in order in `additional_data` (omitted when empty) so nothing is silently dropped.
- If neither source is meaningful, `renderSupportAnswer` returns an error and the tool returns a tool error `support_empty_answer: task <id> is COMPLETED but carries no answer in status.message or artifacts`. It never returns an empty success.

For FAILED, REJECTED, CANCELED, INPUT_REQUIRED and AUTH_REQUIRED, `reason` is the text of `status.message` assembled with the same text rule, and `text`/`result` are left empty. A missing reason is not an error for these states, because the state alone is the outcome. For a non-terminal state after the wait, only ids and state are returned.

### 2. `mctl_ask_support(tenant, question, context_id?)`

- Annotations: title "Ask the support agent", readOnly=false, destructive=false, idempotent=false.
- The description states that it creates a task, spends the tenant's model budget, waits up to the configured bound, and is followed up with `mctl_get_support_task`.
- Steps:
  1. Parse `tenant` with the `commerceTenantPath` normalization (factored into `normalizeTenantArg`). Require a non-empty `question` (bounded to 8 KiB). `context_id` is optional and must be a string.
  2. Tenant check, in `s.supportTenantAllowed(ctx, tenant)`. If there is a user in the context, it uses `user.HasTenantAccess(tenant)`. Otherwise (stdio) it calls `/api/v1/whoami` and allows the tenant only when `isAdmin` is true, `boundTenant == tenant`, or `groups` contains it. A whoami error refuses the call. A refusal returns `tenant_forbidden: you are not a member of tenant <t>` and sends nothing.
  3. **Start the wait budget.** Immediately before the send, `budgetCtx, cancel := context.WithDeadline(ctx, time.Now().Add(Wait))`. This single deadline covers the send and all polling. It is never reset or extended per phase, and every later request and sleep derives from `budgetCtx`.
  4. **Send.** `POST /message:send` with `{"message":{"messageId":<new uuid>,"role":"ROLE_USER","parts":[{"text":question}],"contextId":ctx?},"configuration":{"returnImmediately":true},"metadata":{"tenant":tenant}}`. The send request's context is `budgetCtx`, so its timeout is the whole remaining budget, with no shorter fixed cap. With `returnImmediately` the server answers as soon as the task exists. If a server ever ignored the flag and blocked, the send would still be bounded by the same budget. The handler treats the send reply the same way in both cases: a terminal or interrupted task is rendered at once without polling.
     - Send outcome **known**: a 2xx reply decoded as a task or message, or a 4xx reply (admission refused before any task exists: 400, 401, 403, 404, 409, 429). A 4xx is a tool error naming the status and the A2A error message.
     - Send outcome **unknown**: transport error, budget expiry during the send, a 5xx, or a 2xx body that cannot be decoded as a task or message. No task id was received, so the tool **does not poll and does not promise that polling can recover**. It returns the tool error `support_send_outcome_unknown: message <messageId> may or may not have created a task (<failure class>); the call was not retried`. The text says that a task may exist and may spend budget.
     - **No automatic resend.** The handler never repeats `message:send`, not even with the same `messageId`. Server-side `messageId` deduplication exists in mctl-support (see "Confirmed wire contract") but has a documented gap ("has not produced a task yet; retry"), and nothing in this tool needs it. A caller-driven retry with a caller-supplied `message_id` is out of scope.
  5. If the reply is a message, render it and return. If the reply is a task that is not yet terminal or interrupted, poll `GET /tasks/{id}` every `PollInterval` (default 2s) until it is. Each poll's context is `budgetCtx` further capped at `RequestTimeout`, and the sleep between polls ends early when `budgetCtx` ends. The poll uses the same bearer. Because there are two replicas with a shared store, which replica answers does not matter. A 4xx on a poll stops polling with a tool error naming the task id. A transport error or 5xx on a poll is retried at the next interval while budget remains, because the id is known and `GET` is safe to repeat.
  6. Results: COMPLETED returns the rendered answer as a normal result, or the `support_empty_answer` tool error described under "Answer contract". FAILED, REJECTED and CANCELED return `mcplib.NewToolResultError` with the rendered JSON, whose state and reason are visible. Interrupted states return a normal result with state, reason and context id. If the budget ends and the last successful read was non-terminal, the call returns a normal result with `{task_id, context_id, state, terminal:false, note:"still running; call mctl_get_support_task"}`. If the budget ends and no poll after the send succeeded, or the last poll failed, it is a tool error that names the task id and the last failure, so the client can continue with `mctl_get_support_task`. If the caller's own context is cancelled, the handler returns its error.

### 3. `mctl_get_support_task(id)`

- Annotations: readOnly=true, destructive=false, idempotent=false. The name uses the `get_` read verb, so it is ungoverned for the receipt gate and counts as a read for agent scopes. It is still not added to `supportTools`.
- `id` must be non-empty, one path segment, and at most 256 bytes. The tool sends one `GET /tasks/{url.PathEscape(id)}` and renders the result with the same state and failure rules as above. There is no tenant argument. mctl-support's own check on the caller's bearer decides visibility, and a task the caller may not see answers as mctl-support answers (for example a 404). That answer is returned as a tool error.

### 4. Wiring and configuration (`cmd/api/main.go`, `cmd/mcp/main.go`)

- Env vars:
  - `SUPPORT_A2A_URL`: for example `https://support.mctl.ai`. Empty means not configured. Startup refuses a non-absolute URL, and refuses `http://` unless the host is loopback, which tests need.
  - `SUPPORT_ASK_WAIT`: the single wait budget for send plus polling. Default 60s, allowed range 5s to 90s. It is not 0, because the send itself runs inside the budget.
  - `SUPPORT_REQUEST_TIMEOUT`: cap on one `GET /tasks/{id}` poll, default 15s, range 1s to `SUPPORT_ASK_WAIT`. It never applies to the send.
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

### 6. Contract fixtures (amendment 2026-10-27)

mctl-api is a public repository, so no recorded response from a real tenant goes into it. The fixtures under `internal/mcp/testdata/support/` are **synthetic and anonymised** but follow the 0.2.1 shape exactly: field names, proto-JSON enum strings, part order, and the `SupportResult` data keys and value types listed under "Confirmed wire contract". Placeholder values only: tenant `example-tenant`, service `example-app`, ids `00000000-0000-4000-8000-0000000000NN`, evidence sources `tool:call_example_N`. No real tenant, service, host, user, token or labs output.

| File | Shape | Used by |
|---|---|---|
| `send_task_submitted.json` | `{"task":{...}}`, state `TASK_STATE_SUBMITTED`, no status message | send/poll tests |
| `task_working.json` | bare task, `TASK_STATE_WORKING` | poll and timeout tests |
| `task_completed_status_message.json` | **main contract**: COMPLETED, `status.message.parts = [text, data]`, no `artifacts`, `history` holding the user question | T5, T15, mutation check |
| `task_completed_artifacts_only.json` | COMPLETED, `status.message` absent, answer in one artifact `[text, data]` | T16 |
| `task_completed_both_sources.json` | COMPLETED, answer in `status.message` and different text/data in artifacts | T17 |
| `task_completed_no_answer.json` | COMPLETED, `status.message` with an empty-text part and a null data part, no artifacts | T18 |
| `task_completed_multi_text.json` | COMPLETED, `status.message.parts = [text, data, text, url, text("  "), data(object)]` | T19 |
| `task_failed.json`, `task_rejected.json`, `task_canceled.json`, `task_input_required.json` | single reason text part in `status.message` | T7, T9 |
| `send_message_reply.json` | `{"message":{...}}` with `[text, data]` | direct-message test |

A `README.md` in that directory states that the files are synthetic, names the shape source (mctlhq/mctl-support `1784f71`, `executor.py` completion event and `agent/result.py` `SupportResult`; a2a-sdk 1.2.3 proto), and forbids recorded responses. Each test that loads a fixture also asserts expected values written out in the test (for example the exact `text` and `result.summary`), so the parity check cannot pass merely because both sides share one rendering bug.

### 7. Docs

- New `docs/support-agent-mcp.md` covering: the two tools, the binding, bearer passthrough, the tenant check, the wait semantics, the failure rules, and the env vars. Link it from `docs/support-agent-scope.md`.
- A follow-up mctl-gitops PR adds `SUPPORT_A2A_URL: https://support.mctl.ai` to `bootstrap/templates/mctl-platform/mctl-api.yaml`. Until it merges, the tools answer "not configured".

## Alternatives

1. **Asynchronous only (ask returns the task id immediately).** This is simplest and avoids the write-timeout change. The issue's amendment 2 rejects it: most questions should take one tool call. A short `SUPPORT_ASK_WAIT` (minimum 5s) is the operator setting closest to it.
1a. **Blocking send without `returnImmediately`, no polling.** 0.2.1 answers in about 15s, so one blocking send would usually fit. It was rejected because a send that times out leaves no task id, so the slow case could only end in "outcome unknown". With `returnImmediately` the id arrives within the first seconds and the slow case degrades to a recoverable `terminal:false` result.
1b. **Automatic resend after an ambiguous send failure.** mctl-support deduplicates by `messageId`, so a resend with the same id and content is usually safe. It was rejected for now: the dedup has a documented "not produced a task yet" gap, and resending would hide a real outage behind a second wait.
2. **A REST route in mctl-api (`POST /api/v1/support/...`) that the MCP tool calls over loopback, like other tools.** This would reuse the API's tenant check and audit. But it adds a second public surface for the same function, and it would hold a REST request open for 60s inside the 30s server write timeout. Dropped as unnecessary for a thin adapter. It can be added later if a non-MCP surface needs it.
3. **A service credential or a mctl-api-minted `support` run token instead of the caller's bearer.** This is explicitly forbidden by amendment 1 ("mctl-api adds no authority, no service credential"). mctl-support already mints its own tenant-bound run token from the caller's bearer.
4. **JSON-RPC `message/send`.** mctl-support 0.2.1 does not serve it (amendment).

## Platform impact

- **Migrations:** none. No state is stored in mctl-api.
- **Backward compatibility:** two new tools. The tool count changes, and `server_test.go` / `annotations_test.go` are updated together with it. Receipt gate audit rows carry the new policy version `v2`. With support unconfigured, `/mcp` behaviour is unchanged. When configured, the `/mcp` write deadline grows to 75s by default.
- **Resources:** each in-flight `mctl_ask_support` call holds one goroutine and one `/mcp` connection for up to the wait, polling every 2s, which is about 30 small GETs at most. mctl-support carries the model cost and has its own spend caps. mctl-api's per-pod rate limiters on `/mcp` still apply.
- **Risks and mitigations:**
  - *Bearer leakage to another host:* the base URL is fixed by operator config, never by caller input. Redirects are not followed. `id` is path-escaped and limited to one segment.
  - *Failure read as an empty answer:* every non-2xx response, decode failure and transport error is a tool error. FAILED, REJECTED and CANCELED are tool errors with their reason. A COMPLETED task with no meaningful answer in either source is a tool error. There are tests for each, and the main contract test is proven to fail against an artifacts-only reader.
  - *Duplicate tasks and spend after an ambiguous send:* the tool never resends. The outcome-unknown error carries the `messageId` and says a task may exist.
  - *Wait budget overrun:* one deadline covers send and polling, so the tool returns within `SUPPORT_ASK_WAIT` plus rendering time, inside the `/mcp` write deadline of `SUPPORT_ASK_WAIT + 15s`.
  - *Tenant check bypass:* mctl-api checks first, and a test asserts zero upstream requests on refusal. mctl-support checks again, and its test lives in mctlhq/mctl-support.
  - *Proxy timeouts shorter than the wait:* the wait is capped at 90s and configurable. On timeout the client still gets the task id, and `mctl_get_support_task` recovers the answer.
  - *Recursion:* the support run scope cannot call `mctl_ask_support`, and a test asserts this.
  - *Token passthrough:* deliberate, and limited to one operator-configured host that already trusts api.mctl.ai as issuer. It is documented in `docs/support-agent-mcp.md`.
