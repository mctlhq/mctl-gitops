# mcp-go-upgrade-v2: Upgrade mcp-go from v0.31 to v0.54.0

## Context
mctl-api's core value is its 24-tool MCP server, built on `github.com/mark3labs/mcp-go`. The
library is pinned at v0.31; the latest release is v0.54.0 (May 13, 2026) — 23 minor versions and
roughly six months of development behind. A prior proposal (`proposals/mcp-go-upgrade/`) targeted
v0.50.0. This v2 raises the target to v0.54.0 following additional signals:

1. **Security:** CVE-2026-27896 discloses that mcp-go's JSON parser handles field names
   case-insensitively. An attacker can send MCP requests with case-variant field names
   (e.g., `"Method"` vs `"method"`) to silently bypass server-side validation logic on all 24
   tools. The advisory is unresolved in v0.31.
2. **Reliability:** Known panic vectors in message handlers and goroutine cleanup paths were fixed
   in releases between v0.31 and v0.54.0. A panic in an MCP handler drops the client session
   silently without returning an error to the Claude client.
3. **Observability:** v0.54.0 adds OpenTelemetry tracing hooks for server and client operations,
   filling a current blind spot in per-tool production observability.

Per ADR-0001, each mcp-go bump requires re-validating all 24 tools through MCP Inspector before
deployment. This drives the effort estimate higher but is non-negotiable.

## User stories
- AS a platform security engineer I WANT mcp-go upgraded to v0.54.0 SO THAT CVE-2026-27896's
  validation-bypass is closed across all 24 MCP tools.
- AS an SRE I WANT panic-safe MCP message handling SO THAT a malformed request cannot silently
  drop a Claude client session.
- AS a platform engineer I WANT OpenTelemetry traces per tool invocation SO THAT I can monitor
  per-tool latency, error rates, and downstream call chains in the existing OTel collector.
- AS a Claude.ai connector user I WANT the server to remain on Streamable HTTP (POST + GET) SO
  THAT existing connector configuration requires no changes (ADR-0001 constraint).

## Acceptance criteria (EARS)
- WHEN mctl-api starts, THE SYSTEM SHALL import `github.com/mark3labs/mcp-go` at v0.54.0 or
  higher, as verified by `go list -m github.com/mark3labs/mcp-go`.
- WHEN a Claude client sends an MCP request with case-variant JSON field names, THE SYSTEM SHALL
  reject or normalise the request and not silently bypass validation (CVE-2026-27896 mitigation).
- WHEN a malformed or truncated MCP message is received, THE SYSTEM SHALL return a JSON-RPC error
  response and not panic or crash the serving goroutine.
- WHEN all 24 MCP tools are exercised via MCP Inspector against the upgraded server, THE SYSTEM
  SHALL return correct schemas and responses for all tools with zero regressions.
- WHILE mctl-api is running, THE SYSTEM SHALL continue serving MCP traffic over Streamable HTTP
  (POST + GET) without requiring clients to reconnect or reconfigure (ADR-0001).
- IF OpenTelemetry environment variables are configured, THEN THE SYSTEM SHALL emit a span per
  MCP tool invocation carrying tool name, tenant, and status code attributes.
- WHEN the CI pipeline runs, THE SYSTEM SHALL pass all existing MCP integration tests without
  modification to test code.

## Out of scope
- Replacing mcp-go with a custom JSON-RPC implementation (ADR-0001).
- Moving MCP to gRPC (ADR-0001 + architecture.md).
- Enabling `sampling-with-tools` capability from v0.54.0 (separate feature proposal).
- Adding new MCP tools beyond the current 24-tool manifest.
- Downgrading for simplicity (ADR-0001).
