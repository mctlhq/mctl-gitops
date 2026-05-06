# Upgrade mark3labs/mcp-go to v0.52.0

## Context

mctl-api v4.14.0 uses mark3labs/mcp-go v0.31 to expose 24 MCP tools over
Streamable HTTP at `https://api.mctl.ai/mcp`. Versions from v0.32 through v0.51
have been covered by earlier upgrade proposals; this proposal targets v0.52.0
specifically.

mcp-go v0.52.0 fixes a TCP connection and file-descriptor (fd) leak in
`StreamableHTTPServer`: when retry logic encounters 404 responses, response
bodies are not closed, causing connections and file descriptors to accumulate
over time. Because mctl-api's `/mcp` endpoint is publicly reachable and any
client that retries on 404 (including Claude.ai and well-behaved MCP clients)
triggers the leak, the service is at risk of fd exhaustion, which leads to
failed accept(2) calls, connection refusals, and eventually OOM-kill. The same
release also introduces a transport-agnostic `Handle` entry point for
`StreamableHTTPServer`, which simplifies future router integration.

## User stories

- AS a platform engineer I WANT mcp-go upgraded to v0.52.0 SO THAT the fd leak
  is eliminated and the service does not accumulate open file descriptors under
  normal client retry traffic.
- AS an SRE I WANT the `/mcp` endpoint to remain available during the upgrade
  SO THAT connected Claude/AI clients experience no downtime.
- AS a platform engineer I WANT to adopt the new transport-agnostic `Handle`
  entry point SO THAT future router changes require less boilerplate.

## Acceptance criteria (EARS)

- WHEN a connected MCP client retries a request and receives a 404 response
  THE SYSTEM SHALL close the response body before the retry attempt so that no
  file descriptor is leaked.
- WHEN mcp-go v0.52.0 is in production THE SYSTEM SHALL expose all 24 existing
  MCP tools at `https://api.mctl.ai/mcp` with identical request/response
  semantics as before the upgrade.
- WHILE the service is running under sustained client load THE SYSTEM SHALL
  maintain a stable open-fd count that does not grow unboundedly over time.
- WHILE the service is processing concurrent MCP requests THE SYSTEM SHALL
  continue to enforce per-request auth header validation as required by
  `architecture.md`.
- IF mcp-go v0.52.0 introduces a breaking change to the `StreamableHTTPServer`
  API THEN THE SYSTEM SHALL adapt call sites so that all unit and integration
  tests pass before the change is merged.
- IF the new transport-agnostic `Handle` entry point is available THEN THE
  SYSTEM SHALL register the MCP handler via `Handle` rather than the previous
  transport-specific method.
- WHEN the upgraded binary is deployed THE SYSTEM SHALL pass all existing
  acceptance tests for the 24 MCP tools without modification to tool
  definitions.

## Out of scope

- Upgrading mcp-go beyond v0.52.0 (handled by a future proposal).
- Changes to tool definitions, tool count, or MCP protocol version.
- Replacing mark3labs/mcp-go with a custom implementation or gRPC transport
  (prohibited by ADR-0001).
- Changes to the chi/v5 router, auth flow, or any non-MCP dependency.
- Tuning the Kubernetes pod fd limit (`ulimit -n`) — the fix should make that
  unnecessary; raising the limit without fixing the root cause is not in scope.
