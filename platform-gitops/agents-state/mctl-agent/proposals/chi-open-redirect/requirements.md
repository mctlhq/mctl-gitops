# chi Open-Redirect CVE Fix: Upgrade go-chi/chi to v5.2.5

## Context
mctl-agent uses `github.com/go-chi/chi/v5` at version 5.2.1 as its HTTP router, wiring up REST endpoints, the AlertManager webhook, and the Telegram webhook. GHSA-mqqf-5wvp-8fh8 / GO-2026-4316 documents an open-redirect vulnerability in chi's `RedirectSlashes` middleware: a crafted URL can cause the middleware to issue a 301/302 redirect to an attacker-controlled external host, enabling phishing or SSRF chaining. The fix landed in v5.2.4; the latest stable release is v5.2.5.

Although the Go Vulnerability Database lists the confirmed vulnerable range as v5.2.2–v5.2.3, the underlying URL-validation gap is structurally present in earlier versions. Upgrading to v5.2.5 closes the risk definitively and also brings a secondary bug fix for double handler invocation in `RouteHeaders`.

## User stories
- AS a security engineer I WANT chi upgraded to v5.2.5 SO THAT the open-redirect vulnerability in `RedirectSlashes` is eliminated.
- AS an on-call engineer I WANT no unexpected redirects from mctl-agent webhook endpoints SO THAT alert pipelines are not disrupted by redirect loops.
- AS a platform operator I WANT the upgrade to be a drop-in module bump SO THAT no router configuration changes are required.

## Acceptance criteria (EARS)
- WHEN `go.mod` is updated, THE SYSTEM SHALL declare `github.com/go-chi/chi/v5 v5.2.5` or later.
- WHEN `govulncheck` is run, THE SYSTEM SHALL report no findings for GO-2026-4316 / GHSA-mqqf-5wvp-8fh8.
- WHEN the AlertManager webhook receives a valid alert payload, THE SYSTEM SHALL process it without issuing any unintended redirect responses.
- WHEN the Telegram webhook receives a valid update, THE SYSTEM SHALL respond with HTTP 200 without redirect.
- WHILE `RedirectSlashes` middleware is active, THE SYSTEM SHALL only redirect to paths on the same host.
- IF any existing integration test relies on router behaviour that changed between v5.2.1 and v5.2.5, THE SYSTEM SHALL have that test updated and passing before merge.

## Out of scope
- Replacing chi with a different HTTP router.
- Changing any route definitions or handler logic.
- Adding new middleware.
