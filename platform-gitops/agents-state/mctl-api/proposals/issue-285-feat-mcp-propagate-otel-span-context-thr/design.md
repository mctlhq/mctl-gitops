# Design: issue-285-feat-mcp-propagate-otel-span-context-thr

## Current state

Transport and tool dispatch
- `internal/mcp/server.go` `NewStreamableHTTPHandler` wraps `server.NewMCPServer(...)` in `server.NewStreamableHTTPServer` with `WithStateLess(true)`. Its `WithHTTPContextFunc` returns `r.Context()` unchanged, so whatever the HTTP middleware put on the request context (auth user, raw token) reaches tool handlers. Tools are registered one by one with `srv.AddTool(s.toolXxx())` in `NewMCPServer`. There is no handler middleware today.
- `internal/api/router.go` mounts `/mcp` (POST/GET/DELETE) inside the authenticated group. The global middleware chain is `middleware.RequestID`, `clientMetaMiddleware`, `Recoverer`, `securityHeaders`, `corsMiddleware`, `metricsMiddleware` (Prometheus). No trace middleware exists.
- Each tool handler calls back into the REST API over loopback through `Server.apiGet` / `apiGetStatus` / `apiPostJSON` / `apiDelete` / `doRequest`, which use `s.httpClient` (a plain `&http.Client{Timeout: 30s}` from `NewServer`; `NewInProcessServer` points it at `http://localhost:<port>`). These requests forward the bearer token but no trace headers.

Operations, incidents, dev loops
- `mctl_get_operation` (`toolGetOperation`) wraps `GET /api/v1/operations/{name}`, which returns a static schema, not an execution.
- Write tools go through `POST /api/v1/operations/{name}/execute` (`internal/api/handlers_write.go` `ExecuteOperation`). That calls `operations.Executor.Submit` (`internal/operations/executor.go`), which creates an Argo `Workflow` with labels `mctl.ai/operation|request-id|user|team`, writes an `audit.Entry` (`internal/audit/logger.go`, table `audit_events` in `internal/audit/postgres.go`), and responds with `{message, operation, workflow: SubmitResult}`.
- `mctl_get_workflow_status` wraps `GET /api/v1/workflows/{name}` (`handlers_read.go` `GetWorkflow`). It resolves the run through `AuditLog.GetByWorkflow`, with an admin-only live fallback for cron runs.
- `mctl_get_incident` wraps `GET /api/v1/incidents/{id}` (`handlers_alerts.go` `GetIncident`). That serializes `alerts.Alert` (`internal/alerts/types.go`) from the `alerts` table (`internal/alerts/store.go`). Incidents are created through `AlertStore.Create` (`handlers_alerts.go:77`).
- `mctl_get_dev_loop` wraps `GET /api/v1/agents/dev-loop/{workflow_id}` (`handlers_dev_loop.go` `GetDevLoopWorkflow`), which returns `{workflow_id, status, shepherd_in_loop, shepherd_in_loop_known}`. `temporalclient.Client.StartDevLoopWorkflow` (`internal/temporalclient/client.go`) starts the workflow with `StartWorkflowOptions{ID, TaskQueue, reuse/conflict policies}` and no memo. `DescribeDevLoopExecution` already reads `RunID` and `StartTime`.

Existing trace fields
- `internal/evidence` (`execution_evidence.trace_id`, filterable via `?trace_id=` in `handlers_evidence.go`) and `internal/usage` (`trace_id`, `span_id` on `usage.Record`) store ids that agents supply. No component in `mctl-api` generates a span.
- `go.mod` has no direct `go.opentelemetry.io/*` dependency. `go.sum` already lists `go.opentelemetry.io/otel v1.44.0` transitively (through gRPC/Temporal), so the module graph accepts it.
- Process lifecycle: `cmd/api/main.go` builds the slog JSON logger, wires stores from env vars (with kill switches through `killSwitchOn`), and shuts down with `srv.Shutdown(shutdownCtx)`.

## Proposed solution

### 1. New package `internal/telemetry`

- `telemetry.Setup(ctx, Config) (shutdown func(context.Context) error, err error)`:
  - Always installs the global propagator `propagation.NewCompositeTextMapPropagator(propagation.TraceContext{}, propagation.Baggage{})`. Propagation works even when export is off.
  - Installs an SDK `TracerProvider` only when `OTEL_SDK_DISABLED != "true"` and `OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set. The exporter is `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp`, which reads the standard `OTEL_EXPORTER_OTLP_*` env. Spans go through `sdktrace.NewBatchSpanProcessor` with a bounded queue (`OTEL_BSP_MAX_QUEUE_SIZE`, default 2048) and an export timeout (default 10s). It never blocks the caller and drops spans on overflow.
  - When the provider is not installed, it uses a minimal "id-only" provider: an SDK `TracerProvider` with no span processor and a sampler of `ParentBased(AlwaysSample)`. Spans then still get valid trace ids that can be persisted and returned, but nothing is exported. This keeps `trace_id` in responses independent of whether a Collector exists. Allocation cost is small, and spans are discarded on `End()`.
  - Sampler comes from the standard `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG`. The default is `parentbased_always_on`.
  - Resource: `service.name=mctl-api`, `service.version` (build version), `deployment.environment` (from env), plus `OTEL_RESOURCE_ATTRIBUTES`.
  - Export errors go to slog at debug level through `otel.SetErrorHandler`, with a rate limit, so a down Collector does not flood logs.
- `internal/telemetry/attrs.go` is the only place that defines attribute keys. Every key maps to the `mctl-docs#107` catalog. Provisional keys: `mctl.mcp.tool.name`, `mctl.mcp.tool.outcome`, `mctl.operation.name`, `mctl.operation.risk_level`, `mctl.team`, `mctl.workflow.name`, `mctl.workflow.namespace`, `mctl.incident.id`, `temporal.workflow_id`, `temporal.run_id`, `mctl.execution.id`, `mctl.work_item.id`, `enduser.id`. Helper constructors (`attrs.Tool(name)`, etc.) are the only way handlers add attributes. A test (T6) asserts that the set of keys emitted equals this allowlist.
- `telemetry.TraceIDFrom(ctx) string` returns the hex trace id when `trace.SpanContextFromContext(ctx).IsValid()`, otherwise `""`. `telemetry.TraceparentFrom(ctx) string` injects into a `MapCarrier` and returns `traceparent`.

### 2. HTTP server spans and context extraction

- Add `otelhttp.NewMiddleware("mctl-api")` (`go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp`) as a router middleware right after `middleware.RequestID` in `internal/api/router.go`. Configure it with:
  - `WithSpanNameFormatter`, which uses the chi route pattern (as `metricsMiddleware` does) to keep cardinality low.
  - `WithFilter`, which skips `/healthz`, `/readyz`, `/metrics`.
  - No request or response body capture (otelhttp does not record bodies or headers by default; the design forbids enabling `WithMessageEvents` or header capture).
- Extracting an incoming `traceparent` / `tracestate` header makes the server span a child of the caller. This covers REST callers and MCP clients that set the header.

### 3. MCP tool spans

- `traceparent` in MCP `_meta`: some callers (stdio bridges, the aggregate portal) cannot set HTTP headers. A tool-level wrapper therefore reads `req.Params.Meta.AdditionalFields["traceparent"|"tracestate"]` (the field mcp-go exposes for `_meta`). If present and valid, it becomes the parent and overrides the HTTP-level parent. The HTTP server span is then linked (span link), not parented.
- The wrapper is applied centrally. Replace the direct `srv.AddTool(s.toolXxx())` calls with `s.addTool(srv, s.toolXxx())`, where `addTool` wraps the handler as `s.traced(tool.Name, handler)`. If mcp-go v1.0.0 offers `server.WithToolHandlerMiddleware`, use that instead in `NewMCPServer`; behavior is the same. Either way no tool is added or removed, so the `server_test.go` tool count is unchanged.
- `traced` starts span `mcp.tools/call <name>` (kind SERVER), sets `mctl.mcp.tool.name` and `enduser.id` (from `auth.UserFromContext`, subject to `OTEL_MCTL_RECORD_ENDUSER`), runs the handler, and sets `mctl.mcp.tool.outcome` to `ok`, `tool_error` (`result.IsError`) or `error` (Go error, status Error). It never reads or records `req.GetArguments()`.
- Loopback propagation: in `NewServer`, wrap `s.httpClient.Transport` with `otelhttp.NewTransport(http.DefaultTransport, ...)` using the same span-name formatter. The REST handler that serves the loopback call then becomes a child of the tool span. The transport is configured not to record URL query strings (`otelhttp.WithSpanOptions` plus a custom `WithSpanNameFormatter`). Paths contain ids, not secrets, but the query is dropped to be safe.

### 4. Operation, workflow, incident and dev-loop spans plus persisted trace ids

Execute and workflow status (stands in for "operation results"; see Open questions)
- `ExecuteOperation`: child span `operation.execute <name>` with `mctl.operation.name`, `mctl.operation.risk_level`, `mctl.team`, then `mctl.workflow.name` and `mctl.workflow.namespace` after submit. Validation and authz failures set status Error with a fixed reason code, never the message text.
- `operations.Executor.Submit`: add Argo annotations (not labels, because label values cannot hold a traceparent) `mctl.ai/traceparent` and `mctl.ai/trace-id` so downstream workers (`mctl-agents#195`) can continue the trace. Do not change workflow parameters. Templates are cluster-scoped and stay untouched.
- `audit.Entry` gains `TraceID string \`json:"traceId,omitempty"\``. `audit_events` gains `ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT ''` (same idempotent pattern as the existing `via_execution_id` migration). `logAudit` fills it from `telemetry.TraceIDFrom(r.Context())`. The in-memory logger stores it too.
- `ExecuteOperation` response adds top-level `"trace_id"` (omitted when empty). `SubmitResult` stays unchanged.
- `GetWorkflow` adds `"trace_id"` from the audit entry when non-empty. The cron fallback path reads the `mctl.ai/trace-id` annotation when present.

Incidents
- `alerts.Alert` gains `TraceID string \`json:"trace_id,omitempty"\``. The `alerts` table gains `ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT ''`. `Store.Create` writes it, and every select or scan that populates `Alert` reads it.
- `CreateIncident` (`handlers_alerts.go` around line 77) sets `a.TraceID = telemetry.TraceIDFrom(r.Context())` only when the caller did not supply one. A caller-supplied `trace_id` in the body (for example from mctl-agent, per the `mctl-agent#97` correlation contract) is accepted only if it matches `^[0-9a-f]{32}$` and is not all zeros.
- `GetIncident` already serializes the whole `Alert`, so `trace_id` appears automatically. Add span attribute `mctl.incident.id`.

Dev loop
- `StartDevLoopWorkflow` sets `StartWorkflowOptions.Memo = {"mctl.trace_id": <hex>, "mctl.traceparent": <w3c>}` when the context has a valid span. The memo is immutable workflow metadata and is returned by `DescribeWorkflowExecution` with no worker involvement. It also serves as the handoff for the Python workers in `mctl-agents#195`.
- `DevLoopExecution` gains `TraceID string`, decoded from `info.GetMemo()` with the default data converter. A decode failure gives `""`, never an error.
- `GetDevLoopWorkflow` switches from `DescribeDevLoop` to `DescribeDevLoopExecution`. That needs one more interface method on the `TemporalClient` interface in `internal/api/interfaces.go`, or it already exists there (check during implementation). The handler adds `"run_id"` and, when non-empty, `"trace_id"` to the response map. The four existing keys keep their values and meaning (see the comment that protects `shepherd_in_loop`).
- Temporal client calls (`Start`, `SignalApprove`, abandon, `Describe`, `QueryShepherdInLoop`) get CLIENT spans with `temporal.workflow_id` and `temporal.run_id`. The Temporal Go SDK OTel interceptor (`go.temporal.io/sdk/contrib/opentelemetry`) is not adopted in this slice. See Alternatives.

### 5. Wiring and configuration

- `cmd/api/main.go`: call `telemetry.Setup` immediately after the logger is built, and defer `shutdown` with a 5-second context after `srv.Shutdown`.
- `helm/values.yaml`: document `OTEL_EXPORTER_OTLP_ENDPOINT` (empty by default), `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_SERVICE_NAME=mctl-api`, `OTEL_TRACES_SAMPLER=parentbased_always_on`. The actual endpoint value is set in `mctl-gitops` once the `#902` Collector exists.
- Tool descriptions for `mctl_get_workflow_status`, `mctl_get_incident` and `mctl_get_dev_loop` in `internal/mcp/server.go` mention the optional `trace_id` (and `run_id` for dev loop). `docs/portal-allowlist.json` needs no change because tool names are unchanged.

### Privacy invariant (enforced, not just documented)

- Attributes can only be added through `internal/telemetry/attrs.go` helpers.
- No helper takes free-form strings from tool arguments except identifiers that the handler already validated (operation name from the catalog, team name, workflow name generated by the executor, incident id that resolved to a stored row).
- otelhttp is configured without header or body capture. The query string is stripped from `url.full` / `http.url`.
- A test runs a representative tool set against an in-memory exporter (`tracetest.NewInMemoryExporter`) with sentinel argument values and a sentinel bearer token, and asserts that no attribute or event contains the sentinels.

## Alternatives

1. Backend-specific SDK (Datadog, Honeycomb, Sentry tracing). Rejected: the issue and epic require vendor neutrality and "no backend-specific dependency". OTLP to a Collector keeps the backend swappable in `mctl-gitops`.
2. Only return a trace id that is looked up from the backend at read time (query Tempo or Jaeger by workflow name). Rejected: inspection responses would then depend on backend health and latency, which the acceptance criteria forbid. Persisting the id at creation time is cheap (one TEXT column) and always available.
3. Adopt Temporal's OTel interceptor (`contrib/opentelemetry`) for full header propagation into workflow and activity code. Deferred: it adds a contrib module and only pays off once the Python workers in `mctl-agents` extract the header. The memo is readable both by `Describe` (needed here for `trace_id`) and by workers, without an interceptor on either side. The interceptor can be added in the `mctl-agents#195` follow-up without changing the API surface.
4. Pass trace context as an Argo workflow parameter. Rejected: cluster-scoped `WorkflowTemplate`s declare their parameters, and an undeclared parameter can fail submission or be ignored inconsistently. Annotations are inert metadata.

## Platform impact

- Migrations: two idempotent `ADD COLUMN IF NOT EXISTS ... DEFAULT ''` statements (`audit_events.trace_id`, `alerts.trace_id`), applied by the existing schema-on-startup pattern. Adding a column with a constant default is metadata-only in Postgres 11 and later, with no table rewrite. Old replicas ignore the column during a rolling deploy.
- Backward compatibility: response changes are additive (`trace_id`, `run_id`) and omitted when empty. No tool name, argument or annotation changes, so `server_test.go` counts, `annotations_test.go` and `portal-allowlist.json` stay valid. Clients that send no trace context see identical behavior apart from the new optional fields.
- Dependencies: `go.opentelemetry.io/otel`, `otel/sdk`, `otel/trace`, `otel/exporters/otlp/otlptrace/otlptracehttp`, `contrib/instrumentation/net/http/otelhttp`. All are vendor neutral. The versions must be aligned with the `otel v1.44.0` already in `go.sum` (or bumped together) to avoid a split module graph.
- Resource impact: the batch processor holds up to about 2048 spans in memory (a few MB at worst). CPU overhead per request is microseconds. When export is off, spans are created but not processed. The current memory limit (256Mi in `helm/values.yaml`) has enough headroom, but this should be watched after rollout.
- Risks and mitigations:
  - Collector outage slows requests. Mitigation: asynchronous batch export, drop on full, export timeout. T5 covers this with a blackholed endpoint.
  - Sensitive data leaks into spans. Mitigation: attribute allowlist, no argument capture, no header or body capture, sentinel test T6.
  - Untrusted callers force sampling or inject bogus parents. Mitigation: per-route rate limits already apply. The sampler is env-configurable. Caller-supplied incident `trace_id` is format-validated. A forged parent only affects the caller's own spans.
  - Trace id cardinality in Prometheus. Not applicable, because no trace id is added to Prometheus labels.
  - Duplicate spans for loopback calls (client span plus server span per tool call). This is accepted and intended: it shows loopback latency separately.
