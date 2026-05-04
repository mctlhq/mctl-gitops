# Design: ws-dos-rate-limit

## Current state

The mctl-openclaw Kubernetes ingress (managed via mctl-gitops / ArgoCD) serves the openclaw HTTP and WebSocket endpoints for all three tenants. Currently there is no per-source connection rate limit applied to WebSocket Upgrade requests before they reach the openclaw process. An attacker can issue an arbitrary number of concurrent unauthenticated WebSocket upgrades, which openclaw processes without a pre-authentication budget — the attack surface described in CVE-2026-41399.

The ingress controller is nginx-based (standard mctl platform ingress class). Rate limiting via nginx annotation is the idiomatic control available without additional infrastructure.

## Proposed solution

### Nginx ingress rate limit annotations

Add the following annotations to the openclaw Ingress resource in mctl-gitops (shared base, applied to all three tenants via Helm values merge):

```yaml
nginx.ingress.kubernetes.io/limit-connections: "30"
nginx.ingress.kubernetes.io/limit-rps: "20"
nginx.ingress.kubernetes.io/limit-rpm: "300"
```

These settings:
- **`limit-connections: 30`** — maximum concurrent connections from a single source IP to an openclaw pod. Prevents connection-pool exhaustion.
- **`limit-rps: 20`** — maximum 20 new connection requests per second per source IP (covers WebSocket Upgrade). Stops burst flooding.
- **`limit-rpm: 300`** — backs up `limit-rps` with a per-minute cap, preventing slow-drip exhaustion.

Excess requests receive **HTTP 429 Too Many Requests**; the nginx ingress logs the event with the source IP and rule name for diagnosis.

### Shared Helm overlay

Rather than duplicating annotations in three tenant values files, add a shared partial `_ingress-ratelimit.yaml` helper template in the openclaw Helm chart (or the mctl-gitops base layer) and reference it from each tenant overlay. This ensures consistency and a single point of change.

### Threshold rationale

- A single legitimate openclaw client (mobile app, desktop client) opens at most 2–3 concurrent WebSocket connections.
- CI/CD test suites opening connections in parallel rarely exceed 10 simultaneous connections from one IP.
- 30 concurrent connections per IP leaves ample headroom for legitimate use while making a DoS attack require 30× more source IPs (which then falls into DDoS territory, handled by upstream infrastructure).
- Values can be tuned upward after observing ingress metrics for 7 days without incident.

### Memory impact

The rate-limit state is stored in the nginx ingress controller's shared memory zone, not in the openclaw pod. **No memory impact on `labs`.**

## Alternatives

### A. Openclaw application-layer connection budget
Add a connection semaphore inside openclaw's WebSocket upgrade handler. **Rejected for this proposal** — requires openclaw code change and upstream coordination; slower to deploy than an ingress annotation. Could be a complementary upstream PR after this network-layer control is in place.

### B. Kubernetes NetworkPolicy connection limits
NetworkPolicy can restrict which pods can communicate but does not support per-IP connection rate limits. **Rejected** — wrong tool; NetworkPolicy operates at L3/L4 without rate semantics.

### C. Dedicated API gateway (e.g., Kong, Envoy)
Full-featured rate limiting with more granularity. **Rejected for now** — adds infrastructure complexity and memory overhead; overkill for a single annotation use-case. Re-evaluate if mctl platform adopts a gateway layer broadly.

## Platform impact

| Dimension | Impact |
|---|---|
| **Migrations** | None — annotation-only change |
| **Backward compatibility** | Full — no change to openclaw application behaviour |
| **Resource impact (labs)** | Zero pod memory delta |
| **Tenant isolation** | Each tenant's Ingress gets the same annotation independently; no cross-tenant blast radius |
| **False positives** | Logged as HTTP 429 with rule tag; diagnosable; thresholds tunable |
| **Rollback** | Remove annotations from Ingress and re-sync ArgoCD |
| **Risk** | LOW — ingress annotation is non-destructive; can be reverted in under 5 minutes |
