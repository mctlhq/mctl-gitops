# Propagate OTel span context through MCP calls and return trace_id in inspection results

## Context

`mctl-api` serves the platform's MCP surface (`/mcp`, Streamable HTTP, stateless) and the REST control plane behind it. Today there is no OpenTelemetry SDK, tracer or OTLP exporter in the service. Callers that already run inside a trace, such as a DevLoop stage in `mctl-agents` or an `mctl-agent` diagnosis, lose that trace when they call an MCP tool: the tool call, the loopback REST call it makes, and the Argo Workflow or Temporal DevLoopWorkflow it starts are not linked to the caller's trace. The data model already has `trace_id` join fields in `internal/evidence` and `internal/usage`, but nothing in `mctl-api` produces a trace id itself, and the inspection responses (`workflows/{name}`, `incidents/{id}`, `agents/dev-loop/{workflow_id}`) do not include one.

This proposal is the `mctl-api` child of epic `mctlhq/.github#55` (vendor-neutral execution tracing). The service will accept W3C trace context on MCP calls, emit spans for tool invocations and the operations they start, export them over OTLP only (no backend-specific SDK), and persist and return `trace_id` on operation, incident and dev-loop inspection results. Responses must not change shape or latency when the Collector is unavailable. MCP arguments and credentials stay out of spans.

## User stories

- AS an mctl-agents DevLoop stage I WANT my MCP tool calls to continue my trace SO THAT the investigator, implementer and platform operations show up as one trace.
- AS an mctl-agent incident diagnoser I WANT `mctl_get_incident` to return the `trace_id` recorded with the incident SO THAT I can pivot from an incident into its spans and logs.
- AS a platform operator I WANT `mctl_get_workflow_status` and `mctl_get_dev_loop` to return the `trace_id` of the call that started the run SO THAT I can find the full execution trace for a deploy or dev loop.
- AS a security reviewer I WANT tool arguments, tokens and request bodies kept out of span attributes SO THAT the trace backend does not become a credential or PII store.
- AS an SRE I WANT tracing to fail open SO THAT a Collector outage never degrades the MCP surface.

## Acceptance criteria (EARS)

Propagation
- WHEN an HTTP request to `/mcp` or `/api/v1/*` carries a valid W3C `traceparent` header (and optionally `tracestate`) THE SYSTEM SHALL create its server span as a child of that remote span context.
- WHEN an MCP `tools/call` request carries `params._meta.traceparent` (and optionally `params._meta.tracestate`) THE SYSTEM SHALL use that context as the parent of the tool span, taking precedence over the HTTP header.
- IF the incoming `traceparent` is absent or malformed THEN THE SYSTEM SHALL start a new root trace and SHALL NOT reject the request.
- WHEN an MCP tool handler calls the REST API over loopback (`Server.apiGet`, `apiGetStatus`, `apiPostJSON`, `apiDelete`) THE SYSTEM SHALL inject the current span context as a `traceparent` header so the REST handler span is a child of the tool span.

Spans
- WHEN an MCP tool is invoked THE SYSTEM SHALL record one span named `mcp.tools/call <tool_name>` with kind SERVER and the attributes defined in the attribute catalog: tool name, outcome (`ok` / `tool_error` / `error`), and the caller's user id when authenticated.
- WHEN `POST /api/v1/operations/{name}/execute` submits an Argo Workflow THE SYSTEM SHALL record a span covering the submission with the operation name, team, risk level and resulting workflow name.
- WHEN a DevLoopWorkflow is started, signalled (approve/abandon) or described through the Temporal client THE SYSTEM SHALL record a CLIENT span carrying the Temporal workflow id and, when known, run id.
- WHEN an incident is read or created THE SYSTEM SHALL record the incident id as a span attribute.
- WHILE recording spans THE SYSTEM SHALL NOT put MCP tool argument values, request or response bodies, `Authorization` headers, bearer tokens, `confirm` values or secret environment values into span attributes or span events.

Trace id in results
- WHEN `ExecuteOperation` submits a workflow and a valid span context exists THE SYSTEM SHALL persist its trace id on the audit entry and include `trace_id` in the response.
- WHEN `GET /api/v1/workflows/{name}` (`mctl_get_workflow_status`) finds an audit entry that has a stored trace id THE SYSTEM SHALL include `trace_id` in the response.
- WHEN an incident is created with a valid span context THE SYSTEM SHALL persist its trace id, and WHEN `GET /api/v1/incidents/{id}` (`mctl_get_incident`) returns an incident with a stored trace id THE SYSTEM SHALL include `trace_id`.
- WHEN a DevLoopWorkflow is started with a valid span context THE SYSTEM SHALL record its trace id and traceparent in the workflow memo, and WHEN `GET /api/v1/agents/dev-loop/{workflow_id}` (`mctl_get_dev_loop`) describes a workflow whose memo carries a trace id THE SYSTEM SHALL include `trace_id` and `run_id` in the response.
- IF no trace id is stored for the resource THEN THE SYSTEM SHALL omit `trace_id` and SHALL leave all existing fields unchanged in name, type and meaning.
- THE SYSTEM SHALL return stored trace ids without contacting the trace backend or the Collector.

Export and resilience
- WHEN `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`) is set and `OTEL_SDK_DISABLED` is not `true` THE SYSTEM SHALL export spans over OTLP using only the vendor-neutral OpenTelemetry Go SDK and OTLP exporter.
- IF no OTLP endpoint is configured or `OTEL_SDK_DISABLED=true` THEN THE SYSTEM SHALL still propagate incoming trace context to outgoing loopback calls, Argo annotations and Temporal memos, and SHALL export nothing.
- WHILE the Collector is unreachable or slow THE SYSTEM SHALL export asynchronously through a bounded batch queue, drop spans when the queue is full, and SHALL NOT block or fail any HTTP or MCP response.
- WHEN the process shuts down THE SYSTEM SHALL flush pending spans with a bounded timeout of at most 5 seconds.

## Out of scope

- Instrumenting the Argo WorkflowTemplates or the mctl-agents Temporal workers themselves. `mctl-api` only hands the context off through an Argo annotation and a Temporal memo; continuing the trace on the other side is `mctlhq/mctl-agents#195`.
- Deploying the Collector or choosing a trace backend (`mctlhq/mctl-gitops#902`).
- Defining the attribute catalog (`mctlhq/mctl-docs#107`) and the execution identity (`mctlhq/mctl-agents#196`). This proposal consumes them.
- Metrics and logs over OTLP. Prometheus metrics in `internal/api/router.go` (`metricsMiddleware`) stay as they are.
- Rendering clickable backend URLs. Only ids are returned; a caller-side or portal-side template turns them into links.
- Backfilling trace ids for incidents, audit entries or dev loops created before this change.
- Adding trace context to tools that only read catalog data and start nothing (for example `mctl_list_operations`).

## Open questions

- `mctl_get_operation` returns a static operation schema from `GET /api/v1/operations/{name}` (`internal/mcp/server.go` `toolGetOperation`). It describes no execution, so it has no trace. This proposal treats the "operation result" in the issue as the execution path: the `ExecuteOperation` response (returned by `mctl_deploy_service` and the other write tools) plus `mctl_get_workflow_status`, which reads the audit entry. Reviewer: confirm this reading. If the author really wants a new per-execution "get operation" tool, that is a follow-up.
- The attribute catalog (`mctlhq/mctl-docs#107`) is not available in this repo. The design keeps every attribute key in one file (`internal/telemetry/attrs.go`) with provisional names (`mctl.mcp.tool.name`, `mctl.operation.name`, `mctl.workflow.name`, `mctl.incident.id`, `temporal.workflow_id`, `temporal.run_id`, `mctl.execution.id`, `mctl.work_item.id`, `enduser.id`). Those names must be reconciled with the catalog before merge.
- Whether `enduser.id` (the GitHub login) is allowed under the epic's privacy invariant. The default here records it; it can be turned off with one flag (`OTEL_MCTL_RECORD_ENDUSER=false`).
- Sampling of externally supplied `traceparent`. The default is `parentbased_always_on` through the standard `OTEL_TRACES_SAMPLER` env var. Any untrusted caller can therefore force sampling for its own requests. That is bounded by the existing per-route rate limits and the batch queue, but operators may prefer `parentbased_traceidratio`.
- Incident creation sources (AlertManager webhook, GitHub Actions poller, mctl-agent POST) are mostly not traced callers. For those, the stored trace id is the server span that created the incident, not an upstream trace. This is still useful for pivoting, but it is not "the caller's trace".
