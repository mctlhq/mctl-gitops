# Upgrade chi to v5.2.5 — Harden Against CVE-2025-69725 Open Redirect

## Context
CVE-2025-69725 (GHSA-4h76-926q-wxxw, CVSS 4.7 Medium) is an open-redirect vulnerability in the `RedirectSlashes` middleware shipped with go-chi/chi. Versions v5.2.2 through v5.2.4 are affected: a crafted URL can cause the middleware to issue an HTTP redirect to an arbitrary external domain, enabling phishing and session-hijacking attacks against end users. The fix is present in v5.2.5, which hardens the redirect logic to reject cross-host redirect targets.

mctl-api is currently pinned to chi v5.2.1, which predates the vulnerable range and is therefore not directly exposed today. However, any accidental or transitive partial upgrade to v5.2.2–v5.2.4 would silently introduce the vulnerability. Upgrading proactively to v5.2.5 eliminates that risk permanently, satisfies security-audit requirements for keeping HTTP router dependencies at their hardened release, and additionally delivers the atomic-type refactor included in the v5.2.x patch series.

## User stories
- AS a platform engineer I WANT chi upgraded to v5.2.5 SO THAT the service cannot inadvertently enter the CVE-2025-69725 vulnerable range in a future partial upgrade.
- AS a security auditor I WANT the HTTP router dependency to be at the hardened version SO THAT open-redirect risk is provably mitigated.

## Acceptance criteria (EARS)
- WHEN the build pipeline runs THE SYSTEM SHALL reference chi v5.2.5 or later in go.mod.
- WHEN a request with a trailing-slash redirect is served THE SYSTEM SHALL redirect only to the same host and not to an arbitrary external domain.
- WHILE the service is running THE SYSTEM SHALL preserve all existing routing behaviour with no 404 or redirect regressions.
- IF any chi middleware API changed between 5.2.1 and 5.2.5 THEN THE SYSTEM SHALL compile cleanly with all middleware call-sites updated.

## Out of scope
- Switching the HTTP router from chi to gin, echo, or any other framework (rejected by architecture.md)
- Upgrading to chi v6 (not yet stable)
- Changes to route definitions or middleware ordering
