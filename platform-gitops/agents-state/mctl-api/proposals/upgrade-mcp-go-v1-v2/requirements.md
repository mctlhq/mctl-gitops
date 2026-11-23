# Upgrade mark3labs/mcp-go to 1.6.0

## Context
mctl-api pins mcp-go 0.31.0. v1.6.0 (19 Nov) adds host validation, configurable reconnects and protocol reliability fixes. The MCP endpoint is public, so DNS-rebinding hardening matters. Supersedes the 1.5.x target of `upgrade-mcp-go-v1`.

## User stories
- AS a platform operator I WANT the MCP server on a current, hardened mcp-go SO THAT the platform stays secure and stable.

## Acceptance criteria (EARS)
- WHEN a request arrives at /mcp with a Host header not in the allowed list THE SYSTEM SHALL reject it.
- WHEN a client lists tools THE SYSTEM SHALL return all 24 tools with unchanged names and schemas.
- WHILE AUTH_REQUIRED is true THE SYSTEM SHALL enforce bearer auth on every MCP request as before.
- IF the Claude.ai connector OAuth PKCE flow fails after the bump THEN THE SYSTEM SHALL be rolled back.

## Out of scope
- Unrelated dependency bumps and API changes.
