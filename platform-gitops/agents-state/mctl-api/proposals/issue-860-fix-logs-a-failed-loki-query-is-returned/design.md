# Design: issue-860-fix-logs-a-failed-loki-query-is-returned

## Current state

- Route: `internal/api/router.go:602` registers `r.Get("/logs/{team}/{app}", h.GetServiceLogs)`. The issue calls the handler `GetLogs`; its real name is `GetServiceLogs`.
- Handler: `internal/api/handlers_read.go:826-880` `GetServiceLogs`:
  - checks auth and `user.HasTenantAccess(team)`, but does not validate `team`/`app` as DNS labels, does not check that the tenant is registered, and does not check that the service exists;
  - `lines`: `strconv.Atoi`, accepted only if `0 < n <= 1000`, otherwise silently 100;
  - `since`: `time.ParseDuration`, accepted only if `> 0`, otherwise silently 1h. There is no upper bound;
  - `LogQuerier == nil` → `200 {"lines":[],"count":0,"note":"Log querying requires in-cluster deployment ..."}`;
  - `QueryRange` error → `200 {"lines":[],"count":0,"note":"Loki query error: "+err.Error()}`, with no `slog` call;
  - success → `200 {"lines": logLines, "count": len(logLines)}`. `logLines` comes from `parseLokiResponse`, which uses `var lines []LogLine`, so an empty result serializes as `null`.
- Interface: `internal/api/interfaces.go:148` `LogQuerier.QueryRange(ctx, namespace, app, lines, since)`.
- Loki client: `internal/loki/client.go`. `http.Client{Timeout: 15 * time.Second}`. Errors wrap with `%w`: `loki: request failed: %w`, which wraps a `*url.Error` whose text includes the full request URL (internal host plus the LogQL query). `loki: HTTP %d: <raw body>` includes Loki's whole response body. The client therefore passes internal hostnames, the query and upstream bodies through `note` to the client today. The deployed LOKI_URL carries no credentials, but none of this is meant for clients.
- Precedent from #859: `internal/api/handlers_workload.go`. `dnsLabelPattern`, `requireRegisteredTenant` (404 on definite absence, 503 on a failed lookup) and `resolveWorkloadService` (gitops catalogue first, ArgoCD fallback, 503 when it cannot confirm) have already landed and are used by `GetServicePods` and `ListNamespaceEvents`. Those handlers answer backend failures with `slog.Warn(...)` and `writeError(w, 503, ...)`, and reject bad `since` with 400 (`ListNamespaceEvents`, 1m..24h). The issue's "once that lands" condition is already met.
- Audit: `internal/api/agent_scope_gate.go:151` `serveAudited` sets `result = "failed"` when `status >= 400`. `internal/mcp/agent_scope.go:89-97` marks a scoped tool call `failed` when `res.IsError`. The MCP tool `toolGetServiceLogs` (`internal/mcp/server.go:2068`) calls `s.apiGet`, which turns any `>= 400` into an error, and then returns `NewToolResultError`. So returning non-2xx is enough to make both audits record `failed`; no audit code changes.
- MCP description: `internal/mcp/server.go:2073-2082` says nothing about failure semantics. OpenAPI: `internal/openapi/openapi.yaml:2281-2342` documents `200` (with `note`) and `404` only.
- Tests: there are no handler tests for `GetServiceLogs`. `internal/api/handlers_workload_test.go` has reusable fakes (`workloadTenants`, `workloadArgo`, `serveUser`, `workloadRouterWith`). `e2e/e2e_test.go:575` requires `200` from the logs endpoint and accepts `note` as an explanation.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml:294`: `LOKI_URL: "http://loki-stack.monitoring.svc.cluster.local:3100"`. Production has the querier configured, so the nil-querier 503 path only affects local/dev deployments. The URL contains no credentials.
- `$MCTL_GITOPS_ROOT/tenants/`: lists admins, commerce-proof, erpact, karabu, labs, mctl, namax66 (at least). Real teams, including `admins`, are registered tenants, so `requireRegisteredTenant` will not newly reject them.
- No mctl MCP tool calls were made; the gitops checkout answered the deployment question.

## Proposed solution

Restructure `GetServiceLogs` to mirror `GetServicePods` (and keep it in `handlers_read.go`):

1. **Order of checks**: auth (401) → `dnsLabelPattern` on team/app (400) → tenant access (403) → parse `lines`/`since` strictly (400) → `requireRegisteredTenant` (404/503) → `resolveWorkloadService` (404/503) → `LogQuerier == nil` → `503 "log querying not configured"` → query. The parameters are validated before the gitops/ArgoCD lookups, so a bad request costs no backend reads.
2. **Strict params**: `lines` must parse as an int in [1, 1000]. `since` must parse as a duration in [`minLogWindow` = 1m, `maxLogWindow` = 720h]. Empty means default (100, 1h). Anything else is a 400 with a message naming the accepted range, in the same style as `ListNamespaceEvents`.
3. **Failure mapping**: a small helper `classifyLogQueryError(ctx, err) (status int, class, msg string)`:
   - `errors.Is(err, context.Canceled)` or `r.Context().Err() == context.Canceled` → 503, class `canceled`;
   - `errors.Is(err, context.DeadlineExceeded)` or `errors.As(err, &netErr) && netErr.Timeout()` → 504, class `timeout`, msg `"log query timed out; Loki did not answer in time, try again or narrow since/lines"`;
   - anything else → 503, class `unavailable`, msg `"log query failed: Loki unavailable"`.
   The handler calls `slog.Warn("log query failed", "team", team, "app", app, "error_class", class, "error", err)` and then `writeError(w, status, msg)`. The client message is a fixed string, so no URL, LogQL or upstream body reaches the client. This also covers the sweep item on leaked error text.
4. **Success body**: `{"team","app","lines","count","limit":lines,"since":since.String()}`. When `QueryRange` returns nil, `lines` is set to an empty slice, so the JSON is `[]` and never `null`. The `note` field is removed: success needs no note, and failures are now errors.
5. **Docs**: update the `mctl_get_service_logs` description in `internal/mcp/server.go`. Add: "A failed or unconfigured log read is an error (503/504), never an empty list; 404 means the tenant or service does not exist. An empty `lines` with `count: 0` means only that Loki answered with no lines in this window. `lines` must be 1-1000 and `since` a duration between 1m and 720h; invalid values are rejected." Update the openapi.yaml path with 400/503/504 responses, add `limit`/`since` to the 200 schema, and drop `note`. Update the README row only if its wording claims otherwise. `docs/portal-allowlist.json` is unchanged: the tool name and its read-only nature stay the same.
6. **e2e**: `e2e/e2e_test.go` logs test accepts `200` (and asserts `count` equals `len(lines)`), or `503` with `"log querying not configured"` as a skip, and fails on anything else.

## Alternatives

- **Keep 200, add a structured `observed: false` / `error_class` field.** Backward compatible, but the issue explicitly asks for non-2xx. The existing status-derived audit (`serveAudited`, MCP `IsError`) would keep saying `succeeded`, and every caller would still have to opt in to the flag. Rejected.
- **Classify errors inside `internal/loki` (typed sentinel errors) instead of in the handler.** Cleaner long term, but the `%w` chain already exposes `context.DeadlineExceeded` / `net.Error` to `errors.Is/As`. Adding sentinels would widen the change to the client and the `LogQuerier` contract for no behavioral gain. Rejected for now. A follow-up can add them if other callers (`QueryNamespace`) need classification.
- **Echo the effective values instead of rejecting invalid params.** The issue allows either. Rejecting is consistent with `ListNamespaceEvents` and stops a typo like `since=7d` (which `ParseDuration` does not accept) from silently becoming 1h. Echoing the values is added as well, so an empty result is self-describing.

## Platform impact

- **No migrations; no config changes.** Production has `LOKI_URL` set.
- **Backward compatibility**: this is a deliberate contract change. A caller that relied on `200` + `note` now gets 503/504/400/404. The MCP tool already surfaces non-2xx as a tool error that carries the API message, so MCP consumers, including the support agent, see a clear error instead of an empty list. The `note` field disappears from 200 responses. Callers that pass `since` > 720h or malformed values now get 400 instead of a silent default.
- **New dependency on gitops/ArgoCD reads per logs call** (`requireRegisteredTenant`, `resolveWorkloadService`). These are the same reads pods/events already do. An ArgoCD outage now turns a logs read for a service outside the catalogue into a 503 rather than a possibly-empty 200. That follows "cannot confirm" semantics and is intended.
- **Resources**: there are no extra Loki calls. Each request may make one more git/ArgoCD lookup, which is negligible.
- **Risk**: an admin or `ReadAllTenants` caller reading logs for a non-tenant namespace such as `monitoring` loses that ability. Mitigation: this is intended (the same reason `requireRegisteredTenant` exists), and namespace-wide Loki access is not this endpoint's purpose.
- **Observability**: Loki failures now produce WARN lines with `error_class`, which can be counted or alerted on.
