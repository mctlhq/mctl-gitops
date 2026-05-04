# WebSocket DoS Rate Limit: Network-level defence against CVE-2026-41399

## Context

CVE-2026-41399 describes an openclaw vulnerability whereby unbounded concurrent unauthenticated WebSocket upgrade requests can be issued without any pre-authentication budget allocation, creating a DoS vector. The patched upstream version boundary is unconfirmed as of 2026-05-04, meaning the risk persists even after the planned upgrade to 2026.4.8 (see proposal `emergency-cve-patch`).

A network-layer control — specifically a per-source connection rate limit on WebSocket Upgrade requests enforced at the Kubernetes ingress — closes the attack surface without requiring an openclaw code change, adds no memory overhead to the `labs` tenant, and provides durable defence-in-depth regardless of future upstream patch coverage.

## User stories

- AS a platform operator I WANT unauthenticated WebSocket upgrade requests to be rate-limited at the ingress SO THAT a single source cannot exhaust the openclaw connection pool.
- AS the `labs` SRE I WANT the rate-limit configuration to introduce zero pod memory overhead SO THAT the tenant remains within its memory budget.
- AS a security engineer I WANT the rate limit to be applied across all three tenants SO THAT `ovk`, `admins`, and `labs` are equally protected.

## Acceptance criteria (EARS)

- WHEN a source IP sends more than N WebSocket Upgrade requests per second (N to be determined in design; initial recommendation: 20 req/s per IP) THE SYSTEM SHALL respond with HTTP 429 and drop the excess connections before they reach the openclaw process.
- WHILE the rate limit is active THE SYSTEM SHALL allow legitimate clients that stay under the threshold to connect without additional latency.
- WHEN the rate-limit annotation is applied to the ingress THE SYSTEM SHALL leave all existing application-layer authentication flows unchanged.
- IF a legitimate client is rate-limited (false positive) THEN THE SYSTEM SHALL surface the HTTP 429 in ingress access logs with a tag that identifies the rate-limit rule, enabling quick diagnosis.
- WHEN the ingress configuration is deployed to `labs` THE SYSTEM SHALL not change the memory footprint of the openclaw pod.
- WHEN the configuration is deployed THE SYSTEM SHALL apply the same rule consistently to all three tenants (`admins`, `labs`, `ovk`) via a shared Helm values overlay.

## Out of scope

- Application-layer changes to openclaw's WebSocket handshake code.
- Global bandwidth throttling or per-user session limits inside openclaw.
- Protection against authenticated DoS (separate concern; separate proposal if needed).
- Mitigation of other CVEs — those are addressed in proposal `emergency-cve-patch`.
