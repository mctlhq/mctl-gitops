# Tasks: mcp-csrf-origin-check

- [ ] 1. Add `MCP_ALLOWED_ORIGINS` config field — DoD: `internal/config/config.go` (or equivalent) parses the env var into `cfg.MCP.AllowedOrigins map[string]struct{}` and `cfg.MCP.AllowAll bool`; a startup `slog.Warn` is emitted when `AllowAll` is true; unit test covers empty string, single origin, multiple comma-separated origins, and `*` wildcard.

- [ ] 2. Implement `MCPCSRFMiddleware` (depends on 1) — DoD: new file `internal/middleware/csrf.go` contains the unexported `writeJSONError` helper and the exported `MCPCSRFMiddleware(allowAll bool, allowed map[string]struct{}) func(http.Handler) http.Handler`; the file compiles with `go build ./...`; no external dependencies added.

- [ ] 3. Register middleware on `POST /mcp` route only (depends on 2) — DoD: the chi router setup wraps the `/mcp` handler with `middleware.MCPCSRFMiddleware(cfg.MCP.AllowAll, cfg.MCP.AllowedOrigins)` using `r.With(...).Post(...)`; all other routes are unmodified; confirmed by reading the diff and by the integration test in T3.

- [ ] 4. Update Kubernetes Deployment manifest (depends on 3) — DoD: the Deployment YAML (or Helm values) for the `admins` tenant includes `MCP_ALLOWED_ORIGINS` in the `env` block with a comment explaining the `*` wildcard; a PR description references CVE-2026-33252; staging deployment verified healthy via `/healthz` and `/readyz`.

- [ ] 5. Update operator runbook / deployment notes (depends on 4) — DoD: a note is added to the relevant runbook or README section explaining the new env var, the fail-secure default (empty = reject all browser origins), and how to add a new allowed origin without restarting (not supported; restart required — document this explicitly).

## Tests

- [ ] T1. Unit — `MCPCSRFMiddleware` blocks request with missing `Content-Type`: middleware returns HTTP 415 with `{"error":"unsupported_media_type",...}` body; `next` handler is never called.

- [ ] T2. Unit — `MCPCSRFMiddleware` blocks request with `Content-Type: text/plain`: same 415 response; `next` not called.

- [ ] T3. Unit — `MCPCSRFMiddleware` blocks request with disallowed `Origin` header: returns HTTP 403 with `{"error":"forbidden",...}`; `next` not called; `slog` warning logged.

- [ ] T4. Unit — `MCPCSRFMiddleware` passes request with allowed `Origin` and `Content-Type: application/json`: `next` is called exactly once; response is whatever `next` produces.

- [ ] T5. Unit — `MCPCSRFMiddleware` passes request with no `Origin` header and valid `Content-Type`: `next` is called (server-to-server path is not blocked).

- [ ] T6. Unit — `MCPCSRFMiddleware` with `allowAll=true` passes any `Origin` value with valid `Content-Type`: `next` is called; wildcard bypass works.

- [ ] T7. Unit — config parsing: `MCP_ALLOWED_ORIGINS=""` yields empty map and `AllowAll=false`; `MCP_ALLOWED_ORIGINS="*"` yields `AllowAll=true`; `MCP_ALLOWED_ORIGINS="https://a.example.com,https://b.example.com"` yields a two-entry map.

- [ ] T8. Integration — chi route isolation: a test that mounts the full router and sends a `POST /api/v1/alerts` request without `Origin` or `Content-Type` headers receives a non-403/non-415 response (i.e. the middleware is not applied to that route).

## Rollback
1. The middleware is registered only at the route level. To roll back immediately without a full redeploy, set `MCP_ALLOWED_ORIGINS=*` in the Deployment env and perform a rolling restart — this disables origin enforcement while keeping the code in place.
2. For a full rollback, revert the commit that adds `r.With(middleware.MCPCSRFMiddleware(...)).Post("/mcp", ...)` and redeploy. The previous image has no middleware on `/mcp` and restores the pre-fix behaviour exactly.
3. ArgoCD sync should be paused (`argocd app pause mctl-agent`) before manual env var changes to prevent the GitOps reconciliation loop from overwriting the temporary override.
