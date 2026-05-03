# Design: mcp-go-upgrade

## Current state
mctl-api exposes 24 MCP tools over Streamable HTTP (`POST /mcp`, `GET /mcp`) using **mark3labs/mcp-go v0.31.0**. This library handles JSON-RPC 2.0 framing, server-sent events, tool schema registration, and OAuth 2.0 PKCE for the Claude.ai connector. The service is currently 19 minor versions behind the latest release (v0.50.0, released 2026-04-30). See `context/architecture.md` and ADR `decisions/0001-mcp-go-library-choice.md`.

## Proposed solution
Upgrade `github.com/mark3labs/mcp-go` from **v0.31** → **v0.50.0** in place, following a structured approach to handle breaking changes across 19 minor versions:

1. **Dependency bump**: `go get github.com/mark3labs/mcp-go@v0.50.0 && go mod tidy`.
2. **Compile and fix**: address all compile-time errors introduced by API changes in the v0.31→v0.50 range (likely tool registration API, option struct changes, server init).
3. **Enable SEP-1303 schema validation** (opt-in): for each of the 24 tools, verify that the registered `InputSchema` accurately reflects what the handler accepts; enable server-side validation once schemas are confirmed.
4. **Validation via MCP Inspector**: run the upstream MCP Inspector against `https://api.mctl.ai/mcp` in a staging environment; all 24 tools must pass schema validation and round-trip correctly.
5. **OAuth 2.0 PKCE**: confirm the PKCE flow for the Claude.ai connector is unaffected.

The library upgrade does not change the external `/mcp` URL, transport protocol, or auth flow — it is an internal implementation detail.

## Alternatives

### A: Custom JSON-RPC implementation
Full control; no external dependency. However, this would require re-implementing Streamable HTTP transport, SSE, schema generation, and OAuth 2.0 PKCE — significant effort with high risk of incompatibility with the Claude.ai connector. **Rejected in ADR 0001.**

### B: Switch to anthropics/sdk-go (official Anthropic MCP SDK)
Mentioned as an alternative in ADR 0001. The SDK was in early development when ADR 0001 was written; it may have matured. However, a library switch (vs. a version bump) requires full re-validation of all 24 tools and is out of scope for a security upgrade. **Dropped**: evaluate separately if mark3labs/mcp-go becomes unmaintained.

### C: Upgrade incrementally (e.g. v0.31 → v0.40 → v0.50)
Reduces the diff per step but doubles the review burden. Since the library has no long-term support policy, intermediate versions offer no benefit.
**Dropped**: upgrade directly to v0.50.0.

## Platform impact

### Migrations
No external API changes. Tool schemas registered in mctl-api may need internal corrections to satisfy SEP-1303 validation, but the schemas exposed to callers should be more accurate, not different in breaking ways.

### Backward compatibility
The `/mcp` endpoint URL, transport, and auth are unchanged. Claude.ai connector and Claude Code sessions will continue to work.

### Resource impact
No meaningful change in CPU or memory. SEP-1303 schema validation adds negligible CPU cost per tool call (JSON Schema validation). No impact on `labs` tenant.

### Risks and mitigations
| Risk | Mitigation |
|------|------------|
| Breaking API changes in v0.32–v0.50 require significant handler rewrites | Run `go build` early; triage compile errors before committing to the upgrade scope |
| MCP Inspector reveals schema mismatches in existing tools | Fix schemas before enabling strict validation; opt-in flag allows gradual rollout |
| OAuth 2.0 PKCE flow broken by transport-layer changes | Explicit integration test of the Claude.ai connector in staging |
| 19-version gap may include subtle behaviour changes | Regression test all 24 tools via MCP Inspector + existing integration test suite |
