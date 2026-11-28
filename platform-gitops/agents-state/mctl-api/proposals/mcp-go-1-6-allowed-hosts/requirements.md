# Adopt mcp-go 1.6.0 and configure WithAllowedHosts

## Context
mcp-go v1.6.0 (19 Nov) adds `WithAllowedHosts` to defend non-loopback binds from DNS rebinding, rejects duplicate in-flight request IDs, and blocks cross-origin redirects in default HTTP clients (GO-2026-6911). The MCP endpoint https://api.mctl.ai/mcp is our main attack surface. Earlier upgrade proposals target older versions.

## User stories
- AS a security owner I WANT the MCP server to accept only expected Host headers SO THAT DNS rebinding cannot reach it.

## Acceptance criteria (EARS)
- WHEN a request to /mcp carries a Host not in the allowlist THE SYSTEM SHALL reject it with 403.
- WHEN a request carries Host api.mctl.ai THE SYSTEM SHALL process it normally.
- WHEN a client reuses an in-flight JSON-RPC request ID THE SYSTEM SHALL reject the duplicate.
- WHILE AUTH_REQUIRED=false locally THE SYSTEM SHALL allow localhost hosts.
- IF the allowlist is configured empty in production THEN THE SYSTEM SHALL fail startup.

## Out of scope
- Replacing mcp-go or changing transport (ADR 0001).
