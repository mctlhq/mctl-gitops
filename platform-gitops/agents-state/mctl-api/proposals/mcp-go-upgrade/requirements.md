# mcp-go-upgrade: Upgrade mark3labs/mcp-go from v0.31 to v0.50.0

## Context
mctl-api's MCP server — the integration surface for Claude.ai and Claude Code clients — is built on `github.com/mark3labs/mcp-go`. The service is currently at v0.31; the library has advanced to v0.50.0 (released 2026-04-30), a gap of 19 minor versions spanning roughly five months of active development.

The MCP ecosystem has attracted active security research in April 2026 (OX Security advisory; The Register, 2026-04-16) documenting RCE-class issues in JSON-RPC message parsing across Go MCP implementations (CVE-2026-27896). While CVE-2026-27896 targets a parallel SDK, the advisory underscores that the attack surface of JSON-RPC parsing in MCP servers is under scrutiny. Staying 19 versions behind increases exposure to undisclosed edge-cases in the same class.

Beyond security, v0.50.0 ships opt-in per-tool input schema validation per SEP-1303, which would harden all 24 tools in mctl-api against malformed call arguments — currently there is no server-side schema enforcement beyond what each handler implements manually.

ADR 0001 confirms mark3labs/mcp-go as the chosen library. This proposal is an in-place version upgrade, not a library switch.

## User stories
- AS a platform operator I WANT the MCP server to run on a recent version of mcp-go SO THAT known and potential JSON-RPC parsing vulnerabilities are mitigated.
- AS a developer I WANT per-tool input schema validation SO THAT malformed tool calls are rejected at the SDK boundary before reaching handler logic.
- AS a Claude.ai connector user I WANT the MCP server to expose `ListPrompts` and `ListResources` endpoints SO THAT richer MCP client integrations are possible.

## Acceptance criteria (EARS)
- WHEN `go.mod` is evaluated THE SYSTEM SHALL list `github.com/mark3labs/mcp-go` at version `v0.50.0` or higher.
- WHEN a tool call is received with a payload that violates the registered input schema THE SYSTEM SHALL return a JSON-RPC error response with code `-32602` (Invalid params) without invoking the handler.
- WHEN the MCP Inspector is run against `https://api.mctl.ai/mcp` THE SYSTEM SHALL pass validation for all 24 registered tools with no schema errors.
- WHILE the upgraded MCP server is running THE SYSTEM SHALL maintain OAuth 2.0 PKCE authentication for the Claude.ai connector.
- WHILE the upgraded MCP server is running THE SYSTEM SHALL preserve Streamable HTTP transport (POST + GET) on the `/mcp` endpoint.
- IF a breaking API change in v0.50.0 requires handler modifications THE SYSTEM SHALL update all affected handlers before the change is merged.
- WHEN `govulncheck ./...` is executed THE SYSTEM SHALL report zero findings attributable to mcp-go.

## Out of scope
- Replacing mark3labs/mcp-go with a custom JSON-RPC implementation (rejected in ADR 0001 and `context/architecture.md`).
- Moving the MCP transport to gRPC (rejected in ADR 0001).
- Adding new MCP tools beyond what is required to resolve breaking changes.
- Implementing `ListPrompts` or `ListResources` tool logic — only wiring up the SDK stubs if they are required by the new API.
