# Design: mcp-go-upgrade-v2

## Current state
mctl-api imports `github.com/mark3labs/mcp-go` at v0.31, providing:
- Streamable HTTP transport (POST + GET) at `/mcp`
- Schema generation and validation for 24 tools (11 read + 13 write)
- OAuth 2.0 PKCE for the Claude.ai connector
- MCP spec version 2025-06-18

The library has no built-in observability hooks. Panics in message handlers are caught by the
existing Go HTTP server recover middleware but result in silent 500 responses with no MCP-layer
error returned to the client.

## Proposed solution
**Bump `github.com/mark3labs/mcp-go` from v0.31 to v0.54.0** via:

```
go get github.com/mark3labs/mcp-go@v0.54.0
go mod tidy
```

**Key changes between v0.31 and v0.54.0 relevant to mctl-api:**

1. **Panic recovery in message handlers** — upstream fixed goroutine cleanup and added per-handler
   recover wrappers. No mctl-api code changes required; the fix is in the library's dispatch loop.

2. **JSON field-name normalisation (CVE-2026-27896)** — v0.54.0 enforces strict lowercase
   field-name matching in the JSON-RPC dispatcher, closing the case-variant bypass. Transparent
   to well-behaved clients; malformed requests now receive a `-32600` Invalid Request error.

3. **OpenTelemetry tracing hooks** — v0.54.0 exposes `mcp.WithServerTracer(tracer)` and
   `mcp.WithClientTracer(tracer)` options. We will wire these to the existing OTel SDK instance
   already used by the service (if one exists) or initialise a no-op tracer if OTel is not
   configured, ensuring zero-configuration backward compatibility.

4. **New protocol fields** — `BaseMetadata.title`, `Icon.theme`, `Resource.size` are additive
   and require no changes to existing tool definitions.

5. **ADR-0001 compliance** — Streamable HTTP transport and MCP spec 2025-06-18+ are preserved.
   All 24 tools must be re-validated through MCP Inspector after the bump.

**OTel integration sketch:**
```go
// In cmd/server/main.go (or equivalent init):
tracer := otel.Tracer("mctl-api/mcp")
mcpServer := mcp.NewServer(
    mcp.WithServerTracer(tracer),
    // existing options unchanged
)
```

## Alternatives

### Upgrade only to v0.50.0 (as in the prior proposal)
v0.50.0 does not include the CVE-2026-27896 fix confirmed in v0.54.0. Rejected — security fix
requires the full bump.

### Patch the case-sensitivity bug locally without upgrading
Would require forking or monkey-patching the dispatcher, creating a maintenance burden and
diverging from upstream. Rejected.

### Replace mcp-go with the Anthropic Go SDK (if released)
ADR-0001 explicitly records this as a rejected alternative: loss of Streamable HTTP compat with
the Claude.ai connector. Not reconsidered here.

## Platform impact
- **Migrations:** go.mod / go.sum update; optional OTel wiring in server init.
- **Backward compatibility:** Streamable HTTP transport preserved; existing 24 tools unchanged.
  Well-behaved Claude clients are unaffected. Malformed requests now receive explicit errors
  (previously they might silently bypass validation).
- **Resource impact:** OTel tracing adds minimal per-request overhead (~1–3 µs per span).
  No `labs` tenant impact (mctl-api runs in `admins`).
- **Risks and mitigations:**
  - Risk: 23-version jump may introduce subtle API changes in tool registration or handler
    signatures. Mitigation: MCP Inspector validation of all 24 tools (per ADR-0001); full
    integration test suite.
  - Risk: OTel tracer initialisation could panic if the OTel provider is misconfigured.
    Mitigation: wrap initialisation in a no-op fallback; add a startup smoke test.
  - Risk: New JSON-RPC strict field-name enforcement may reject existing internal test clients
    that send non-lowercase fields. Mitigation: audit test harness request payloads in step 2.
