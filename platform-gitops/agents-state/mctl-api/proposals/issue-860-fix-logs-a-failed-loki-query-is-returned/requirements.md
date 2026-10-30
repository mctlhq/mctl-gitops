# fix(logs): a failed or impossible Loki read is never answered as 200 with empty lines

## Context

`GET /api/v1/logs/{team}/{app}` (handler `GetServiceLogs` in
`internal/api/handlers_read.go`, exposed over MCP as `mctl_get_service_logs`
and used by the tenant support agent) answers `200` with `"lines": []` and
`"count": 0` in two cases where nothing was observed. One is a failed
`LogQuerier.QueryRange` call, where the error text goes into a free-text
`note`. The other is an unconfigured log backend (`LogQuerier == nil`). The
handler also logs nothing. The support-request audit row is derived from the
HTTP status (`serveAudited` in `internal/api/agent_scope_gate.go`) and the MCP
scoped-tool audit is derived from `IsError` (`internal/mcp/agent_scope.go`), so
both record the call as `succeeded`. On 2026-10-29 a 15s client timeout to Loki
produced this exact response during a pilot support task.

This is the same class of defect as mctl-api#859: if mctl could not observe
something, it must never report it as observed absent. The fix makes every
failed read non-2xx, logged and audited as failed. After the fix, `200` with
`count: 0` means only "Loki answered and returned no lines for this window".
The same handler is also swept for three more problems. Invalid query
parameters are silently replaced by defaults. The handler has no
tenant/service existence check like the one #859 added for pods and events.
Raw Loki/transport error text is passed through to the client.

## User stories

- AS a tenant support agent I WANT a failed log read to come back as an error SO THAT I never tell a customer "the service logged nothing" when the logs could not be read.
- AS a platform operator I WANT failed Loki reads logged at WARN with an error class and audited as failed SO THAT I can see and count Loki outages from mctl-api's side.
- AS an MCP client I WANT invalid `lines`/`since` values rejected, and the values actually used echoed back, SO THAT I know which window an empty result covers.
- AS a tenant member I WANT a typo in the service name to answer 404 SO THAT an unknown service is not mistaken for a silent one.

## Acceptance criteria (EARS)

- IF `LogQuerier.QueryRange` returns an error caused by a deadline or timeout (`context.DeadlineExceeded`, or a `net.Error` with `Timeout() == true`) THEN THE SYSTEM SHALL answer `504` with an `error` body and no `lines`/`count` fields.
- IF `LogQuerier.QueryRange` returns any other error THEN THE SYSTEM SHALL answer `503` with an `error` body and no `lines`/`count` fields.
- WHEN a Loki query fails THE SYSTEM SHALL write one `slog.Warn` record carrying `team`, `app`, `error_class` (`timeout`, `canceled` or `unavailable`) and the full underlying error.
- WHEN a Loki query fails THE SYSTEM SHALL return a client message that does not contain the Loki base URL, the LogQL query, or the raw Loki response body.
- IF `LogQuerier` is nil THEN THE SYSTEM SHALL answer `503` with error `log querying not configured`.
- WHEN Loki answers successfully with zero lines THE SYSTEM SHALL answer `200` with `"lines": []` and `"count": 0`, never `null`.
- WHEN Loki answers successfully THE SYSTEM SHALL include in the response the `lines` limit and the `since` window actually used.
- IF `lines` is present and is not an integer in [1, 1000] THEN THE SYSTEM SHALL answer `400` and SHALL NOT query Loki.
- IF `since` is present and is not a Go duration in [1m, 720h] THEN THE SYSTEM SHALL answer `400` and SHALL NOT query Loki.
- IF `team` or `app` is not a DNS label THEN THE SYSTEM SHALL answer `400`.
- IF `team` is not a registered tenant THEN THE SYSTEM SHALL answer `404`. IF the tenant lookup fails THEN THE SYSTEM SHALL answer `503` (reusing `requireRegisteredTenant`).
- IF `app` is not a known service of `team` THEN THE SYSTEM SHALL answer `404`. IF that cannot be confirmed THEN THE SYSTEM SHALL answer `503` (reusing `resolveWorkloadService`).
- WHILE the response status is `>= 400` THE SYSTEM SHALL record the support-request audit row as `failed` and the MCP scoped-tool call as `failed`. The existing status-derived audit already does this once the handler returns non-2xx.
- THE SYSTEM SHALL state in the `mctl_get_service_logs` MCP description and the OpenAPI spec that a failed or unconfigured read is an error and that `count: 0` means only "Loki answered with no lines in this window".

## Out of scope

- Changing the Loki client's 15s timeout, adding retries, or adding caching.
- `QueryNamespace` callers, and any other handler besides `GetServiceLogs`.
- Changes to the support agent (mctl-support) or other consumers beyond what the status-code change implies.
- Loki or promtail deployment configuration.

## Open questions

- Upper bound for `since`: this proposal uses 720h (Loki's default `max_query_length` is 721h). The issue does not name a bound. A tighter one, such as the 24h used by `ListNamespaceEvents`, would reject values that work today.
- Loki answering a non-200 status such as 400 or 429 is mapped to 503 like any other failure. A distinct 502 for "upstream answered with an error" was considered and left out for simplicity.
- A request whose caller disconnected (`r.Context()` canceled) is still answered with 503 and logged at WARN with `error_class=canceled`. The reviewer may prefer a lower log level for that class.
