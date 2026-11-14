# Tasks: chi-suppressnotfound-redirectslashes-audit

- [ ] 1. Check status of `chi-upgrade-and-middleware-audit`, `chi-open-redirect`, `bump-chi`, `chi-v5-security-upgrade`, `chi-redirect-cve-boundary-check` and the current chi version in `go.mod` — DoD: list of already-done vs open items in the PR description.
- [ ] 2. Verify advisories (CVE-2026-114437, CVE-2026-118681, CVE-2026-122132, GO-2026-5774/5775/5777) and fixed versions in the Go vuln DB (depends on 1) — DoD: a table of ID, affected range and fixed version.
- [ ] 3. Audit `cmd/` and `internal/` for `RedirectSlashes`, `SupressNotFound`, `RealIP` and client-IP reads (depends on 1) — DoD: file/line list; every client-IP use classified (logging, rate limit, auth).
- [ ] 4. Upgrade chi to 5.5.0 or newer verified (depends on 2) — DoD: `go.mod`/`go.sum` updated, build passes, `govulncheck` shows no unexplained chi findings.
- [ ] 5. Remove `RedirectSlashes` or replace it with the control-character guard (depends on 3, 4) — DoD: no unguarded `RedirectSlashes` in the router; the webhook URLs were confirmed to have no trailing slash.
- [ ] 6. Handle `SupressNotFound` and `RealIP` per the audit (depends on 3, 4) — DoD: no authorization decision depends on `RealIP`; SupressNotFound runs only on 5.5.0+.
- [ ] 7. Add regression tests and deploy via ArgoCD to `admins` (depends on 5, 6) — DoD: tests green, pod Ready, alerts and Telegram webhooks still accepted.

## Tests
- [ ] T1. Request to an unknown path under a protected prefix without credentials is not answered with success.
- [ ] T2. Path with a tab or `%09` character gets no redirect (400 or 404).
- [ ] T3. Trailing-slash request behaves as designed (documented outcome) for each route.
- [ ] T4. Status codes of `/api/v1/alerts`, `/api/v1/telegram`, `/mcp`, `/healthz`, `/readyz` unchanged.
- [ ] T5. Spoofed `X-Forwarded-For` does not change any authorization result.

## Rollback
Revert the PR and let ArgoCD sync the previous image. If only the RedirectSlashes change breaks a client, restore the previous routing for that path alone behind the control-character guard, not the unguarded middleware.
