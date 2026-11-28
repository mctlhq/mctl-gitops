# Design: mcp-go-1-6-allowed-hosts

## Current state
mcp-go 0.31 Streamable HTTP server, 24 tools, no Host validation (context/architecture.md, ADR 0001).

## Proposed solution
Bump to v1.6.0, adapt for API changes since 0.31, set `WithAllowedHosts` from env `MCP_ALLOWED_HOSTS` (default api.mctl.ai; localhost when AUTH_REQUIRED=false), and validate startup config.

## Alternatives
- Host check in chi middleware: duplicates library logic and may miss future behaviour.
- Upgrade only, no allowlist: leaves rebinding open.

## Platform impact
- Migrations: add env var in gitops values.
- Compatibility: Claude.ai connector uses api.mctl.ai; verify OAuth PKCE flow.
- Resource impact: negligible; no change for `labs`.
- Risks: wrong allowlist blocks clients; mitigated by staging and rollback.
