# Upgrade chi to 5.5.0 and remove or guard the vulnerable middlewares

## Context
The pinned `go-chi/chi/v5` 5.2.1 is below the fixes for CVE-2026-114437 (fixed in 5.4.0) and CVE-2026-118681 (`middleware.SupressNotFound` authentication bypass, fixed in 5.5.0). The `middleware.RealIP` spoofing advisories (GO-2026-5774, GO-2026-5775, GO-2026-5777) matter if rate limiting or audit logging trusts the client IP. CVE-2026-122132 (`middleware.RedirectSlashes` open redirect via a tab in the path, published 2026-11-04) affects chi up to and including 5.5.0 and has no known fixed version.

Existing proposals overlap: `chi-upgrade-and-middleware-audit` (upgrade to 5.5.0 plus a RealIP/RedirectSlashes audit), `bump-chi`, `chi-v5-security-upgrade`, `chi-open-redirect` (RedirectSlashes, targets 5.2.5) and `chi-redirect-cve-boundary-check`. This proposal does not repeat them. Its delta is the new `SupressNotFound` auth-bypass CVE and handling of `RedirectSlashes` now that no chi release fixes it.

## User stories
- AS the service owner I WANT chi on a release with the SupressNotFound fix SO THAT no route can bypass authentication via not-found handling.
- AS a security reviewer I WANT unfixed middleware removed or guarded SO THAT the open redirect cannot be exploited even on the latest chi.

## Acceptance criteria (EARS)
- WHEN the audit runs THE SYSTEM SHALL list every use of `RedirectSlashes`, `SupressNotFound` and `RealIP` in `cmd/` and `internal/`, with file and line.
- WHEN `SupressNotFound` is used THE SYSTEM SHALL run only on chi 5.5.0 or later, and SHALL have a test showing that an unauthenticated request to an unknown protected path does not receive a success response.
- WHEN `RedirectSlashes` is used THEN THE SYSTEM SHALL remove it, or replace it with a guard that rejects paths containing control characters (including tab, `%09`) and redirects only to same-host relative paths.
- IF `RedirectSlashes` is not used THEN THE SYSTEM SHALL record that in the PR and add a regression test that a path with a tab character gets no redirect.
- WHEN `RealIP` is used THE SYSTEM SHALL use the resulting IP only behind the known ingress, and SHALL NOT use it for authorization.
- WHEN the chi dependency is updated THE SYSTEM SHALL pin 5.5.0 or the newest verified release, and `govulncheck` SHALL report no chi findings except documented, unfixed ones.
- WHILE webhook callers (AlertManager, Telegram) use their configured URLs THE SYSTEM SHALL keep answering them with unchanged status codes.

## Out of scope
- Replacing chi with `net/http` ServeMux.
- Go toolchain changes (see `go-1274-nethttp-maxbytes-patch`).
- Redesigning authentication for the API.
