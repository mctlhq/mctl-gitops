# Harden POST /mcp Endpoint Against MCP stdio Command Injection (CVE-2026-30623)

## Context
CVE-2026-30623 (published 2026-04-15) identifies a command injection vector in the MCP SDK's
stdio transport layer. mctl-agent is the sole service in the platform that exposes a
`POST /mcp` JSON-RPC endpoint with 6 registered MCP tools (see `context/architecture.md`),
making it a direct and uniquely exposed attack surface in the `admins` tenant. The service runs
at `https://agent.mctl.ai` and is reachable from within the cluster by any component that can
reach the `admins` namespace.

The CVE has not yet been weaponised publicly, but the CVSS score is pending and the attack
class (command injection via crafted tool-name or parameter payloads) is well-understood and
trivially exploitable once a proof-of-concept circulates. Hardening the MCP handler layer with
strict tool-name allowlisting and request sanitisation closes the primary injection vector
without replacing the underlying HTTP transport, limiting blast radius and engineering cost.

## User stories
- AS a platform security engineer I WANT all MCP tool invocations to be validated against an
  explicit allowlist SO THAT a crafted JSON-RPC request cannot invoke unregistered or injected
  tool names.
- AS a platform engineer I WANT malformed or oversized MCP request payloads to be rejected
  before they reach the skill dispatcher SO THAT injection payloads do not propagate into the
  diagnose or fix pipeline.
- AS an on-call engineer I WANT suspicious MCP requests to be logged with structured context
  SO THAT I can reconstruct an attempted attack in the audit log.

## Acceptance criteria (EARS)
- WHEN a `POST /mcp` request arrives with a `method` field that does not exactly match one of
  the 6 registered tool names THE SYSTEM SHALL return HTTP 400 and a JSON-RPC error response
  with code `-32601` (Method Not Found) and MUST NOT forward the request to the skill dispatcher.
- WHEN a `POST /mcp` request body exceeds 64 KB THE SYSTEM SHALL return HTTP 413 and reject
  the request before JSON unmarshalling.
- WHEN a `POST /mcp` request contains a `params` object with a string field whose length
  exceeds 8 KB THE SYSTEM SHALL return HTTP 400 with JSON-RPC error code `-32602`
  (Invalid Params) and log the field name and truncated value at `WARN` level.
- WHEN any MCP request is rejected by the validation layer THE SYSTEM SHALL emit a structured
  `slog` log entry at `WARN` level containing: request ID, remote IP, rejected field, and
  rejection reason.
- WHILE the MCP handler is processing a request THE SYSTEM SHALL enforce a per-request timeout
  of 30 seconds and return HTTP 408 if the timeout is exceeded.
- IF the allowlist configuration is empty or missing at startup THE SYSTEM SHALL refuse to
  start and log a `FATAL` message indicating which configuration key is absent.

## Out of scope
- Replacing the MCP HTTP transport with a different transport (e.g., SSE, WebSocket).
- Adding authentication or mTLS to the `POST /mcp` endpoint (tracked separately).
- Modifying the 6 registered MCP tool implementations — only the handler layer is in scope.
- Hardening non-MCP endpoints (`/api/v1/*`, `/healthz`, `/readyz`).
- Upgrading the MCP SDK version (no safe version is available at time of writing).
