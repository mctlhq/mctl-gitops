# Design: mcp-csrf-origin-validation

## Current state
`mctl-api` mounts the MCP handler from mark3labs/mcp-go v0.31 directly on the chi router at `/mcp`. The chi middleware chain for that route currently includes OIDC/JWT auth and httprate rate-limiting, but no Origin header inspection. Any browser tab that can reach `https://api.mctl.ai/mcp` with an authenticated session can POST arbitrary JSON-RPC tool calls.

The architecture documentation (`context/architecture.md`) confirms 13 write tools are exposed and that all MCP write tools are expected to check org membership, but there is no transport-layer guard against cross-site request forgery.

## Proposed solution

### Chi middleware: `OriginValidation`

Add a single chi-compatible middleware function `middleware.OriginValidation(allowedOrigins []string) func(http.Handler) http.Handler` in a new file `internal/middleware/origin.go`.

**Logic:**
1. If the request has no `Origin` header, call `next` immediately (non-browser callers are unaffected).
2. If the request has an `Origin` header, normalise it (lowercase scheme+host, strip trailing slash).
3. Check it against the compiled allowlist. If it matches, call `next`.
4. If it does not match, log a WARN structured entry (`request_id`, `origin`, `path`), increment `mcp_csrf_rejected_total{origin_domain=<eTLD+1>}`, and return HTTP 403 with body `{"error":"forbidden_origin"}`.

**Configuration** via environment variable `MCP_ALLOWED_ORIGINS` (comma-separated):

```
MCP_ALLOWED_ORIGINS=https://claude.ai,https://app.mctl.ai
```

This is read once at startup in `cmd/api/main.go` and passed to the middleware constructor. If the variable contains a malformed entry (fails `url.Parse` or has no host), the process exits with a non-zero code and a descriptive error.

**Prometheus metric** registered in `internal/metrics/metrics.go`:

```go
mcpCSRFRejected = promauto.NewCounterVec(prometheus.CounterOpts{
    Name: "mcp_csrf_rejected_total",
    Help: "Total MCP requests rejected due to disallowed Origin header.",
}, []string{"origin_domain"})
```

**Router registration** in `cmd/api/router.go` (before the MCP handler mount):

```go
r.With(
    authMiddleware,
    middleware.OriginValidation(cfg.MCPAllowedOrigins),
).Mount("/mcp", mcpHandler)
```

The middleware is placed after auth so that the request ID is already attached to the context, but it runs before the MCP handler to abort invalid requests early.

### Why chi middleware rather than patching mcp-go?

The MCP handler is a black box from mark3labs/mcp-go; we do not fork it. A chi middleware wraps it cleanly, stays in our codebase, and is independently testable.

## Alternatives

### Option A: Upgrade to mcp-go v0.51 which adds built-in CORS/Origin controls
Considered. The library upgrade is tracked as a separate proposal (`mcp-go-v051-upgrade`) because it spans 20 minor versions and requires re-validating all 24 tools through MCP Inspector (ADR 0001). It is high-effort (Impact 3, Effort 4). Waiting for that upgrade leaves the CSRF window open for the duration of the upgrade project. The chi middleware is a thin, low-risk fix that can ship in days.

### Option B: WAF / Ingress-level Origin filtering
Rejecting disallowed Origins at the Nginx/Ingress layer is possible, but the Origin allowlist would then live in infrastructure manifests rather than application config. This couples an application security concern to the Kubernetes/ArgoCD deployment config, makes local development harder, and is harder to test in unit/integration tests. Rejected.

### Option C: CSRF double-submit cookie
Classic CSRF token patterns require the client to read a cookie and echo it as a header. MCP clients (Claude.ai, CLI) are not browsers and would need to be updated to handle the token exchange. The Origin validation approach is transparent to existing non-browser clients. Rejected.

## Platform impact

### Migrations
None. The middleware is additive. No database schema changes.

### Backward compatibility
- CLI and server-side callers that do not send `Origin` are unaffected.
- Claude.ai connector sends `Origin: https://claude.ai` — this origin must be included in `MCP_ALLOWED_ORIGINS` for the Claude.ai integration to remain functional. The default empty allowlist means the **operator must explicitly set** `MCP_ALLOWED_ORIGINS` before deploying to production. Deployment runbook must include this step.
- If `MCP_ALLOWED_ORIGINS` is not set, the service logs a warning but does not crash (it treats all browser Origins as forbidden). This is the secure default.

### Resource impact
The middleware adds one string comparison per request — negligible CPU overhead. No additional memory. No impact on the `labs` tenant (this change is in `admins` only; `labs` is not affected).

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Legitimate origin accidentally excluded from allowlist | Startup validation + integration test that sends a request from the Claude.ai origin. Alert on spike in `mcp_csrf_rejected_total`. |
| Attacker spoofs Origin header from a server-side client | Server-side callers (curl, CLI) do not set Origin; browsers cannot suppress it. This is the standard Origin trust model. |
| Middleware placed after auth, request reaches auth before being rejected | Acceptable: auth is fast (JWT verification) and does not execute MCP tool logic. Placing Origin check before auth would leak whether the endpoint exists to unauthenticated cross-origin probes. |
