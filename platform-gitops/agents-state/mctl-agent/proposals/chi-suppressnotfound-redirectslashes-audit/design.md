# Design: chi-suppressnotfound-redirectslashes-audit

## Current state
chi/v5 5.2.1 routes `/api/v1/alerts`, `/api/v1/telegram`, `/api/v1/tickets`, `/api/v1/skills`, `/api/v1/skills/register`, `/mcp`, `/healthz`, `/readyz` (see `context/architecture.md`). Which middleware are mounted is not known from context and must be read from the code. Related earlier work: `chi-upgrade-and-middleware-audit` (general audit and 5.5.0 upgrade), `chi-open-redirect` and `chi-redirect-cve-boundary-check` (redirect handling), `bump-chi`, `chi-v5-security-upgrade`.

## Proposed solution
1. Grep for `RedirectSlashes`, `SupressNotFound` (note the upstream spelling) and `RealIP`, plus reads of `X-Forwarded-For`, `X-Real-IP` and `r.RemoteAddr`. Record results.
2. Check status of the earlier proposals; if `chi-upgrade-and-middleware-audit` is already implemented, only do the items below that remain open. Do not duplicate its tasks.
3. Upgrade chi to 5.5.0 (or a newer verified release). Confirm the advisory IDs and fixed versions in the Go vuln DB.
4. `RedirectSlashes`: because no fixed release exists, remove it if unused or unnecessary. If trailing-slash redirects are needed, replace it with a small local middleware that rejects paths with control characters (tab, CR, LF, and their percent-encodings) with 400 and only issues same-host relative redirects. Reuse any guard already designed in `chi-open-redirect`.
5. `SupressNotFound`: if used, rely on the 5.5.0 fix and add an auth-bypass regression test. If unused, record it.
6. `RealIP`: keep only if a trusted ingress sets the headers; never use the IP for authorization.
7. Add route regression tests, deploy via ArgoCD to `admins`.

Rationale: the version bump alone does not fix `RedirectSlashes`, so the code-level guard or removal is the real mitigation there.

## Alternatives
- Upgrade only: leaves the unfixed open redirect if `RedirectSlashes` is mounted; rejected.
- Wait for a chi release fixing CVE-2026-122132: leaves exposure open for an unknown time; rejected.
- Move to `net/http` ServeMux: large refactor, out of proportion to the risk; rejected.

## Platform impact
- Migrations: none.
- Backward compatibility: removing `RedirectSlashes` changes behavior for URLs with a trailing slash (404 or 400 instead of a redirect). Confirm the configured AlertManager and Telegram webhook URLs before removal. chi 5.2.1 to 5.5.0 changes (Deprecation header, Retry-After rounding, SupressNotFound context handling) are low risk.
- Resource impact: negligible; the agent runs in `admins`, so there is no `labs` impact and no memory increase is expected.
- Risks and mitigations: advisories not verified (verification task first); trailing-slash clients break (check webhook URLs, regression tests); overlap with unfinished earlier proposals (check their status and mark them superseded or complete).
