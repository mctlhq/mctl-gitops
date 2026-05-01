# Node.js March 2026 Process-Crash CVEs (21637 + 21713 + 21714 + 21717)

## Context
The Node.js March 24, 2026 security release discloses four vulnerabilities that affect Node.js 22.x, which is the runtime used by mctl-portal. Three of the four (CVE-2026-21714, CVE-2026-21717, CVE-2026-21713) are rated MEDIUM and expose the service to memory exhaustion, HashDoS, and timing side-channels respectively. One (CVE-2026-21637) is rated HIGH and allows any unexpected TLS servername to crash the entire Node.js process via an uncaught synchronous exception in SNICallback. An existing proposal (`nodejs-security-upgrade`) already tracks CVE-2026-21710; these four CVEs are out of scope for that proposal and require dedicated acceptance criteria and test coverage.

All four vulnerabilities are present in the current runtime image. Because mctl-portal runs on tenant `admins` behind nginx + ArgoCD, the fix is a targeted runtime image bump to a patched Node.js 22.x build. The tenant `labs` is not affected. Delaying remediation leaves the portal process susceptible to remote crash and denial-of-service from any authenticated or unauthenticated attacker who can reach the backend over TLS or HTTP.

## User stories
- AS a platform engineer I WANT the mctl-portal runtime upgraded to a Node.js 22.x build that patches CVE-2026-21637, CVE-2026-21713, CVE-2026-21714, and CVE-2026-21717 SO THAT the portal is no longer vulnerable to process-crash and denial-of-service attacks from malformed TLS, HTTP/2, HMAC, or JSON input.
- AS a security officer I WANT explicit acceptance criteria and verified test coverage for each of the four CVEs SO THAT I can confirm remediation in the audit trail without relying solely on the `nodejs-security-upgrade` proposal.
- AS a portal operator I WANT the upgrade applied with zero planned downtime and a documented rollback path SO THAT reliability commitments to developers using the portal are maintained.

## Acceptance criteria (EARS)

### CVE-2026-21637 — SNICallback process crash (HIGH)
- WHEN a TLS ClientHello arrives with an unexpected or malformed `servername` value THEN THE SYSTEM SHALL handle the resulting exception without terminating the Node.js process.
- WHEN the portal process receives a TLS connection with an unexpected servername THEN THE SYSTEM SHALL respond with a TLS alert and continue serving subsequent requests.

### CVE-2026-21713 — HMAC timing side-channel (MEDIUM)
- WHILE the portal backend performs any HMAC verification operation THE SYSTEM SHALL use a constant-time comparison so that response time does not reveal information about the expected MAC value.

### CVE-2026-21714 — HTTP/2 WINDOW_UPDATE memory exhaustion (MEDIUM)
- WHEN an HTTP/2 client sends a WINDOW_UPDATE frame targeting stream 0 THE SYSTEM SHALL release the associated Http2Session for garbage collection, preventing unbounded memory growth.
- WHILE the portal is receiving sustained HTTP/2 traffic THE SYSTEM SHALL not accumulate unreleased Http2Session objects over time.

### CVE-2026-21717 — V8 HashDoS via JSON.parse (MEDIUM)
- WHEN the portal backend receives JSON payloads containing attacker-controlled integer-like string keys THE SYSTEM SHALL compute hash values in a manner that does not allow an attacker to force systematic hash collisions.
- IF a request body or query parameter contains a large number of integer-like keys THEN THE SYSTEM SHALL process the input without exhibiting O(n²) hash-table degradation.

### General runtime upgrade
- WHEN the Dockerfile is built THE SYSTEM SHALL use a Node.js 22.x base image whose version string is greater than or equal to the first patched release that resolves all four CVEs.
- WHEN the upgraded image is deployed to the `admins` tenant via ArgoCD THE SYSTEM SHALL pass all existing smoke tests before the rollout is declared complete.
- IF the CI pipeline smoke test fails after the image bump THEN THE SYSTEM SHALL block promotion and preserve the previous image tag.

## Out of scope
- CVE-2026-21710 (__proto__ header crash) — addressed in the separate `nodejs-security-upgrade` proposal.
- Upgrading Node.js beyond the 22.x line (e.g., to 24.x) — that is a separate compatibility effort.
- Changes to application-level HMAC logic or custom TLS configuration — the fix is solely in the runtime image.
- Any impact on tenant `labs` — this proposal applies exclusively to tenant `admins`.
- Patching third-party Backstage plugins against these CVEs — only the Node.js runtime is in scope.
