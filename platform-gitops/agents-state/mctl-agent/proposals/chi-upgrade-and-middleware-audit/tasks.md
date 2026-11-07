# Tasks: chi-upgrade-and-middleware-audit

- [ ] 1. VERIFY chi advisories: confirm the RealIP X-Forwarded-For spoofing and RedirectSlashes open redirect entries on pkg.go.dev/vuln (IDs, dates, affected and fixed versions) — DoD: table recorded in the PR; states whether 5.2.1 and 5.5.0 are affected.
- [ ] 2. Run `govulncheck ./...` on the current code — DoD: output saved; chi findings (if any) listed as reachable or not.
- [ ] 3. Audit the code for `RealIP`, `RedirectSlashes`, `SupressNotFound`, and any client-IP reads (`X-Forwarded-For`, `X-Real-IP`, `RemoteAddr`) — DoD: list of file:line and what each usage guards (depends on none).
- [ ] 4. Check how the ingress sets forwarded headers for `agent.mctl.ai` (read-only) — DoD: documented whether RealIP is needed (depends on 3).
- [ ] 5. Remediate audit findings: remove or restrict middleware as the audit dictates (depends on 1, 3, 4) — DoD: no security decision relies on a spoofable IP; no open redirect path.
- [ ] 6. Upgrade chi to 5.5.0 or the verified fixed version, `go mod tidy` (depends on 1) — DoD: builds; go.sum updated.
- [ ] 7. Add route regression tests for all endpoints in the architecture doc (depends on 6) — DoD: tests cover status codes, trailing slash, 404/405.
- [ ] 8. Re-run `govulncheck` and deploy to `admins` via ArgoCD (depends on 5, 6, 7) — DoD: no chi findings; webhook smoke tests pass.

## Tests
- [ ] T1. Table-driven router test: each route returns the expected status before and after the upgrade.
- [ ] T2. Spoofed `X-Forwarded-For` request: resulting identity or IP does not affect any authorization decision.
- [ ] T3. Request such as `//evil.example` or a trailing-slash path does not redirect off-host.
- [ ] T4. Sample AlertManager and Telegram webhook POSTs return 2xx and create tickets.
- [ ] T5. Full `go test ./...` passes.

## Rollback
Revert the PR (go.mod, go.sum, middleware changes) and let ArgoCD sync the prior image. No data migration is involved.
