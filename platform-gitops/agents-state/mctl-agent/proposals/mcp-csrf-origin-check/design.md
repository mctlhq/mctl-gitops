# Design: mcp-csrf-origin-check

## Current state
As described in `context/architecture.md`, mctl-agent is a Go 1.24 service using chi/v5 5.2.1 as its HTTP router. The `POST /mcp` route is mounted directly on the chi router with no middleware beyond whatever global middleware the router applies. There is no Origin header inspection, no Content-Type enforcement, and no CSRF mitigation of any kind on this route. The other API routes (`/api/v1/alerts`, `/api/v1/telegram`, etc.) are similarly unprotected against CSRF, but they are not in scope for this proposal.

## Proposed solution

### Overview
Introduce a single chi-compatible `http.Handler` middleware function — `MCPCSRFMiddleware` — in a new file `internal/middleware/csrf.go`. The middleware is applied inline to the `POST /mcp` route registration only, leaving all other routes untouched.

### Configuration
A new environment variable `MCP_ALLOWED_ORIGINS` is read at startup and parsed into a `map[string]struct{}` for O(1) lookups. The variable accepts a comma-separated list of origin values (e.g. `https://dashboard.mctl.ai,https://staging.mctl.ai`). The special value `*` disables the check entirely for local development. If the variable is unset or empty, the map is empty and every request carrying an `Origin` header is rejected.

Parsing happens once in the existing config initialisation path (e.g. `internal/config/config.go`), so the middleware receives an already-parsed `map[string]struct{}` and a boolean `allowAll` flag — no string parsing in the hot path.

### Middleware logic
```
func MCPCSRFMiddleware(allowAll bool, allowed map[string]struct{}) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            // 1. Content-Type check
            ct := r.Header.Get("Content-Type")
            if !strings.HasPrefix(ct, "application/json") {
                writeJSONError(w, http.StatusUnsupportedMediaType,
                    "unsupported_media_type", "Content-Type must be application/json")
                return
            }

            // 2. Origin check
            origin := r.Header.Get("Origin")
            if origin != "" && !allowAll {
                if _, ok := allowed[origin]; !ok {
                    slog.Warn("mcp csrf: origin rejected",
                        "remote_addr", r.RemoteAddr,
                        "origin", origin)
                    writeJSONError(w, http.StatusForbidden,
                        "forbidden", "origin not allowed")
                    return
                }
            }

            next.ServeHTTP(w, r)
        })
    }
}
```

The helper `writeJSONError` writes `Content-Type: application/json`, the given status code, and a `{"error":"...","reason":"..."}` body. It is defined in the same file and is unexported.

Requests with no `Origin` header at all (e.g. direct `curl` or server-to-server calls) are not blocked by the origin check — this is correct per the CSRF threat model, which targets browser-originated cross-site requests. The Content-Type check still applies to all requests regardless.

### Route registration change
In the chi router setup (e.g. `cmd/agent/main.go` or `internal/server/server.go`), the single line change is:

```go
// Before
r.Post("/mcp", mcpHandler)

// After
r.With(middleware.MCPCSRFMiddleware(cfg.MCP.AllowAll, cfg.MCP.AllowedOrigins)).Post("/mcp", mcpHandler)
```

No other routes are touched.

### Error response format
All rejection responses follow a consistent JSON schema to aid log parsing and alerting:
```json
{"error":"<code>","reason":"<human-readable message>"}
```
HTTP 403 is used for origin rejections; HTTP 415 for Content-Type rejections.

## Alternatives

### 1. Global chi middleware applied to all routes
Adding CSRF protection at the router level would cover all `POST` routes uniformly. This was dropped because the other endpoints (`/api/v1/alerts`, `/api/v1/telegram`) receive requests from external systems (AlertManager, Telegram) that do not send `Origin` headers or use `application/json` Content-Type consistently. Applying the middleware globally would break those integrations and require a broader compatibility analysis, significantly increasing effort and risk for no additional security gain in this proposal's scope.

### 2. Token-based CSRF (double-submit cookie or synchroniser token)
Classic token-based CSRF is appropriate for browser-rendered HTML forms. MCP clients are programmatic JSON-RPC consumers, not browsers rendering forms. Issuing and validating CSRF tokens would require a stateful token store, a `GET /mcp/csrf-token` endpoint, and client-side changes. The Origin-header approach achieves the same protection for same-origin policy-enforced browser environments with zero client-side changes. The token approach was dropped as over-engineered for this threat model.

### 3. Vendor a dedicated CSRF middleware package (e.g. `gorilla/csrf`)
Third-party CSRF packages are designed for cookie/session-based web apps and bring dependencies that are unnecessary here. Writing the 30-line middleware in-house keeps the dependency tree stable, keeps the logic fully auditable, and avoids the risk of the external package not supporting chi/v5's middleware interface cleanly.

## Platform impact

### Migrations
None. This is a pure code change with a new optional environment variable. No database schema changes, no new persistent state.

### Backward compatibility
- Existing MCP clients that send requests from a browser context must add their origin to `MCP_ALLOWED_ORIGINS`. Server-to-server MCP clients (no `Origin` header) are unaffected.
- The new `MCP_ALLOWED_ORIGINS` env var defaults to empty. Operators must explicitly set it in the Kubernetes `Deployment` manifest or Helm values before deploying, otherwise all browser-originated MCP calls will be rejected (fail-secure default).
- All other API routes are completely unaffected.

### Resource impact (labs tenant)
The middleware adds a single map lookup and two `strings.HasPrefix` calls per `POST /mcp` request. Memory overhead is one `map[string]struct{}` with at most a handful of entries. CPU impact is unmeasurable at MCP call frequencies. There is no risk to the `labs` tenant memory limit.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operators forget to set `MCP_ALLOWED_ORIGINS`, blocking legitimate browser clients | Medium | Document in deployment runbook; add a startup log warning if the var is unset and at least one MCP request has been received |
| `*` wildcard left enabled in production | Low | Emit a `slog.Warn` at startup when `allowAll` is true |
| Middleware inadvertently applied to other routes | Low | Unit tests verify the middleware is only registered on `POST /mcp` by inspecting the chi route tree |
| CVE fix is incomplete (e.g. missing header canonicalisation) | Low | Go's `net/http` canonicalises all header names before `Header.Get`, so `origin` and `Origin` resolve identically |
