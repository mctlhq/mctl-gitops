# Design: mcp-go-v1-upgrade

## Current state
mcp-go 0.31 serves 24 tools over Streamable HTTP with OAuth 2.0 PKCE (context/architecture.md, ADR 0001).

## Proposed solution
Bump to v1.5.0, adapt to API changes across 0.x to 1.x (server constructors, tool/handler signatures, options), set explicit body-size limits where the library exposes them, and ensure any mcp-go client use supplies an http.Client with a CheckRedirect policy that strips credentials. Re-validate all tools with MCP Inspector, as ADR 0001 requires.

## Alternatives
- Stay on 0.31: keeps exposure to unbounded reads; rejected.
- Intermediate step to 0.5x: extra churn; use only if 1.x migration proves too large.
- Replace library: prohibited by ADR 0001.

## Platform impact
- Migrations: none for data.
- Backward compatibility: MCP spec compatibility must be confirmed with Claude.ai connector; high effort due to the version gap.
- Resource impact: admins only; no effect on `labs`.
- Risks: breaking API changes — mitigated by canary and Inspector tests.
