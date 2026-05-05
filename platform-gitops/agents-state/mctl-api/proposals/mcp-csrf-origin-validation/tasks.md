# Tasks: mcp-csrf-origin-validation

- [ ] 1. Add `MCP_ALLOWED_ORIGINS` config field — DoD: `internal/config/config.go` parses the env var as a `[]string`; startup exits with a descriptive error if any entry fails `url.Parse` or has an empty host; unit tests cover valid list, empty list, and malformed entry.
- [ ] 2. Register `mcp_csrf_rejected_total` Prometheus counter (depends on 1) — DoD: counter is registered in `internal/metrics/metrics.go` with label `origin_domain`; existing metrics test passes; metric appears in `/metrics` output in a local run.
- [ ] 3. Implement `middleware.OriginValidation` (depends on 1, 2) — DoD: `internal/middleware/origin.go` contains the middleware; logic: absent Origin → pass through; matching Origin → pass through; non-matching Origin → 403 `{"error":"forbidden_origin"}` + WARN log + counter increment; pure unit tests cover all three branches with table-driven cases.
- [ ] 4. Mount middleware on chi router at `/mcp` (depends on 3) — DoD: `cmd/api/router.go` applies `middleware.OriginValidation` in the `/mcp` route group after auth middleware; no other routes are affected; `go build ./...` succeeds.
- [ ] 5. Update ArgoCD / Helm values for `admins` tenant (depends on 4) — DoD: `MCP_ALLOWED_ORIGINS=https://claude.ai,https://app.mctl.ai` is set in the `admins` values file; PR reviewed by a platform engineer; change is reviewed against the deployment runbook.
- [ ] 6. Update deployment runbook (depends on 5) — DoD: runbook documents the `MCP_ALLOWED_ORIGINS` variable, the secure-default behaviour when unset, and how to add new allowed origins; runbook change is reviewed in the same PR as the values file.

## Tests

- [ ] T1. Unit — `TestOriginValidation_NoOriginHeader`: request with no `Origin` header passes through to the next handler, counter not incremented.
- [ ] T2. Unit — `TestOriginValidation_AllowedOrigin`: request with `Origin: https://claude.ai` (in allowlist) passes through.
- [ ] T3. Unit — `TestOriginValidation_DisallowedOrigin`: request with `Origin: https://evil.example.com` returns 403 with `{"error":"forbidden_origin"}`, counter incremented with `origin_domain=evil.example.com`.
- [ ] T4. Unit — `TestOriginValidation_MalformedAllowlistStartup`: config parsing returns an error for `MCP_ALLOWED_ORIGINS=not-a-url`.
- [ ] T5. Unit — `TestOriginValidation_EmptyAllowlist`: when allowlist is empty, any request with an Origin header is rejected.
- [ ] T6. Integration — end-to-end HTTP test: spin up the chi router with the full middleware chain, confirm that a POST to `/mcp` with `Origin: https://claude.ai` is routed correctly, and a POST with `Origin: https://attacker.example` returns 403.
- [ ] T7. Regression — confirm that CLI smoke tests (no Origin header) against the staging `/mcp` endpoint continue to pass after deployment.

## Rollback
1. Remove `middleware.OriginValidation` from the `/mcp` route group in `router.go` and revert the config field in `config.go`.
2. Delete or zero-out `MCP_ALLOWED_ORIGINS` from the ArgoCD values file.
3. ArgoCD will sync the previous deployment automatically on merge to main.
4. The Prometheus counter will stop incrementing; no persistent state is affected (no migrations were applied).
