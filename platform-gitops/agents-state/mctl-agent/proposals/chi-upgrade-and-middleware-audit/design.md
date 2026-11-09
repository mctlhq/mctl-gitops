# Design: chi-upgrade-and-middleware-audit

## Current state
chi/v5 5.2.1 is the HTTP router for `/api/v1/alerts`, `/api/v1/telegram`, `/api/v1/tickets`, `/api/v1/skills`, `/mcp`, `/healthz`, `/readyz` (see `context/architecture.md`). Which middleware are mounted (RealIP, RedirectSlashes, others) is not known from context and must be read from the code.

## Proposed solution
1. Verify: confirm the chi advisories via `govulncheck` and the Go vuln DB (IDs, dates, fixed-in), and read the 5.5.0 release notes.
2. Audit: grep the router setup for `middleware.RealIP`, `middleware.RedirectSlashes`, `SupressNotFound`, and any code reading `X-Forwarded-For`, `X-Real-IP` or `r.RemoteAddr`. Document where client IP is used for decisions.
3. Remediate by finding: remove unused risky middleware; if RealIP is needed, only trust it behind a known ingress, and do not use the value for authorization.
4. Upgrade `github.com/go-chi/chi/v5` to 5.5.0 (or the verified fixed version) and add route regression tests (status codes, trailing-slash behavior, 404/405, Retry-After if used).
5. Deploy via ArgoCD to `admins`.

Rationale: audit and upgrade in one change, since the upgrade alone does not fix misuse of middleware.

## Alternatives
- Upgrade only, no audit: misses misuse-based exposure that no version fixes.
- Remove RealIP and RedirectSlashes unconditionally: may break trailing-slash clients or log accuracy; decide only after the audit.
- Migrate to net/http ServeMux (Go 1.22+ patterns): larger refactor than the risk warrants.

## Platform impact
- Migrations: none.
- Backward compatibility: chi 5.5.0 changes (Deprecation header, Retry-After rounding, SupressNotFound context handling) are low risk; AlertManager and Telegram callers should see no change. Removing RedirectSlashes could change behavior for trailing-slash URLs, so confirm the webhook URLs configured in AlertManager and Telegram.
- Resource impact: negligible; none on `labs` (agent runs in `admins`).
- Risks and mitigations: unverified advisories (verification tasks first); behavior drift (regression tests on all routes); the ingress may already set the real IP (check before touching RealIP).
