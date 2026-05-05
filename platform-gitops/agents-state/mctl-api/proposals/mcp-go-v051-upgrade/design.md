# Design: mcp-go-v051-upgrade

## Current state
`mctl-api` uses mark3labs/mcp-go v0.31 (see `context/architecture.md`). The library is the sole implementation of the MCP Streamable HTTP server. 24 tools are registered at startup. There is no library-level CORS handling, no RFC 9728 metadata endpoint, and no tool output schema validation. JSON-RPC tracing requires custom middleware.

ADR 0001 (see `context/decisions/`) mandates that every mcp-go bump must pass a full MCP Inspector re-validation of all 24 tools before merge.

## Proposed solution

### 1. Dependency upgrade

Run:
```
go get mark3labs/mcp-go@v0.51.0
go mod tidy
```

Track and resolve any API breakages methodically, tool registration file by tool registration file (see tasks).

### 2. CORS interaction with `mcp-csrf-origin-validation`

v0.51.0 introduces built-in CORS controls on the Streamable HTTP transport. The separate `mcp-csrf-origin-validation` proposal ships a chi middleware guard. To avoid double-handling:

- If the `mcp-csrf-origin-validation` middleware is deployed before this upgrade lands, configure the mcp-go v0.51 CORS option with the same `MCP_ALLOWED_ORIGINS` allowlist and **disable** the chi middleware (remove it from the router, keep the code for rollback).
- If this upgrade lands first, rely on the library CORS controls and the chi middleware is not needed. Document the decision in a short ADR update.

In either case, a single source of truth (the `MCP_ALLOWED_ORIGINS` env var) drives the allowlist.

### 3. RFC 9728 OAuth Protected Resource Metadata

v0.51.0 adds a `.well-known/oauth-protected-resource` endpoint. Configure it in `cmd/api/router.go` or via the mcp-go server options:

```go
mcpServer := mcp.NewServer(mcp.WithOAuthProtectedResource(mcp.OAuthProtectedResourceConfig{
    Resource:             "https://api.mctl.ai",
    AuthorizationServers: []string{"https://ops.mctl.me/api/dex"},
}))
```

The values come from existing env vars `API_BASE_URL` and `DEX_ISSUER`. No new secrets required.

### 4. Tool output schema validation

Enable the library's schema validation option:

```go
mcp.NewServer(mcp.WithToolOutputValidation(true))
```

Any tool whose handler returns a shape not matching its registered output schema will surface as a JSON-RPC error. This requires that all 24 tools have accurate output schemas — part of the MCP Inspector validation gate.

### 5. LoggingTransport

Wrap the server transport in `mcp.LoggingTransport` when `MCP_LOG_TRANSPORT=true`:

```go
if cfg.MCPLogTransport {
    transport = mcp.NewLoggingTransport(transport, logger)
}
```

This emits DEBUG-level structured log lines. It must be disabled in production by default to avoid logging sensitive tool payloads; only enable on staging or during incident triage.

### 6. SchemaCache for stateless deployments

Enable `SchemaCache` in the server options. This is a correctness improvement for multi-pod deployments (Kubernetes) where each replica must serve consistent schema documents. No additional config required.

### 7. MCP Inspector CI gate

Add a `Makefile` target `mcp-inspector-ci` that:
1. Starts `mctl-api` with `AUTH_REQUIRED=false` on a local port.
2. Runs `npx @modelcontextprotocol/inspector --headless --assert-tool-count=24` against it.
3. Exits non-zero if any tool is missing or returns an error on a happy-path call.

This target runs in the CI pipeline (GitHub Actions / ArgoCD pre-sync hook) on every PR that touches `mcp-go` version or tool registration files.

## Alternatives

### Option A: Incremental upgrades (v0.31 → v0.35 → ... → v0.51)
Considered. Reduces per-step diff size but multiplies the number of MCP Inspector validation runs required. The library changelog between v0.31 and v0.51 does not show intermediate breaking changes severe enough to require stepwise migration. A single jump with a thorough test pass is more efficient. Rejected.

### Option B: Fork mcp-go and backport only CVE-2026-33252 fix
Considered for the security fix only. Maintaining a fork is ongoing toil and diverges us from upstream improvements (RFC 9728, schema validation). The `mcp-csrf-origin-validation` chi middleware already provides an independent CSRF guard in the interim, making a fork unnecessary. Rejected.

### Option C: Replace mcp-go with a different MCP library
Explicitly excluded by ADR 0001 and by the architecture constraint that Claude.ai clients require HTTP (not gRPC). No alternative Go MCP library at comparable maturity exists. Rejected.

## Platform impact

### Migrations
No database schema changes. No new persistent state. The `SchemaCache` is in-process and stateless.

### Backward compatibility
- All 24 existing MCP tool names and input schemas must remain identical. The MCP Inspector CI gate enforces this.
- The RFC 9728 endpoint is additive; existing clients that do not request it are unaffected.
- If tool output schema validation rejects previously-accepted malformed responses, those call sites will see JSON-RPC errors instead of malformed data. This is a correctness improvement but could surface latent bugs. The MCP Inspector happy-path tests will catch regressions before merge.
- The `mcp-csrf-origin-validation` chi middleware must be coordinated with this upgrade (see section 2 above) to avoid double-firing 403s.

### Resource impact
- `SchemaCache` holds serialised JSON schemas in memory. Estimated additional heap: < 1 MB for 24 tools. Negligible.
- `LoggingTransport` in DEBUG mode adds log volume proportional to MCP traffic. Default is off.
- This change affects the `admins` tenant only. No impact on `labs` tenant memory.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| API breakage in tool registration across 20 versions | Address tool by tool; CI must pass before merge. MCP Inspector gate provides an integration-level safety net. |
| CORS double-handling with `mcp-csrf-origin-validation` middleware | Explicit coordination step in tasks; one mechanism must be disabled before the other is enabled. |
| Tool output schema validation rejects currently-accepted responses | Run MCP Inspector in validation mode on staging before promoting to production. Fix any failing tools first. |
| `LoggingTransport` accidentally enabled in production, leaking sensitive payloads | `MCP_LOG_TRANSPORT` defaults to `false`; Helm values file for `admins` does not set it. |
