# Upgrade mcp-go from v0.31 to v0.51.0

## Context
`mctl-api` depends on mark3labs/mcp-go v0.31 as its sole MCP server library. As of 2026-05-04, v0.51.0 is available, spanning 20 minor versions of changes. The gap includes: a fix for CVE-2026-33252 (CSRF via missing Origin validation in Streamable HTTP transport), RFC 9728 OAuth Protected Resource Metadata endpoint support, built-in CORS controls on HTTP transports, tool output schema validation, a `SchemaCache` for stateless deployments, a `LoggingTransport` for JSON-RPC request tracing, and Go 1.23 iterator-based pagination for client calls.

Staying on v0.31 means we carry a known-CVE library in production and miss protocol compliance improvements that Claude.ai clients expect. ADR 0001 accepts mcp-go as the authoritative MCP library but mandates re-validation of all 24 MCP tools through MCP Inspector on every version bump. This proposal scopes the full upgrade including that validation gate.

## User stories
- AS a security engineer I WANT mcp-go upgraded to v0.51.0 SO THAT CVE-2026-33252 is remediated at the library level and we benefit from built-in CORS controls.
- AS a platform administrator I WANT the RFC 9728 OAuth Protected Resource Metadata endpoint available SO THAT Claude.ai and other MCP clients can discover our OAuth configuration automatically.
- AS an on-call engineer I WANT JSON-RPC request/response tracing via `LoggingTransport` SO THAT I can diagnose MCP tool call failures without adding custom instrumentation.
- AS a developer I WANT tool output schema validation enforced by the library SO THAT regressions in tool response shapes are caught at the MCP layer rather than silently passed to clients.

## Acceptance criteria (EARS)

### Upgrade
- WHEN `go get mark3labs/mcp-go@v0.51.0` is applied THE SYSTEM SHALL compile without errors and all existing unit tests shall pass.
- WHEN the service starts after the upgrade THE SYSTEM SHALL serve the MCP endpoint at `https://api.mctl.ai/mcp` identically to the pre-upgrade behaviour for all 24 tools.

### CVE remediation
- WHEN a POST request arrives at `/mcp` with an `Origin` header not in the configured allowlist THE SYSTEM SHALL return HTTP 403 (this behaviour may be delivered either by the library's built-in CORS controls or by the `mcp-csrf-origin-validation` middleware — both must not double-fire).

### RFC 9728
- WHEN a GET request is made to `https://api.mctl.ai/.well-known/oauth-protected-resource` THE SYSTEM SHALL return a valid RFC 9728 JSON document including the `resource` and `authorization_servers` fields.

### Tool validation
- WHEN an MCP tool handler returns a response that does not conform to the tool's declared output schema THE SYSTEM SHALL return a JSON-RPC error to the caller instead of forwarding the malformed response.

### Logging transport
- WHILE `MCP_LOG_TRANSPORT=true` is set THE SYSTEM SHALL log every JSON-RPC request and response pair at DEBUG level including `method`, `id`, and elapsed milliseconds.

### MCP Inspector gate
- WHEN the upgrade PR is opened THEN THE SYSTEM SHALL have a CI step that runs MCP Inspector against a local instance and asserts all 24 tools are listed and return non-error responses on their happy-path invocations.

## Out of scope
- Changes to individual tool business logic (covered by their own tasks).
- Client-side use of Go 1.23 iterator pagination — our service is server-side only.
- Switching MCP transport from Streamable HTTP to any other transport.
- Upgrading unrelated dependencies (pgx, chi, etc.).
