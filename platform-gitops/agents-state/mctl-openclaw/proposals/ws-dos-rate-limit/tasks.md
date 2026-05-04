# Tasks: ws-dos-rate-limit

- [ ] 1. **Confirm nginx ingress controller version and annotation support** — Verify the mctl platform ingress controller supports `nginx.ingress.kubernetes.io/limit-connections`, `limit-rps`, and `limit-rpm` annotations (available since nginx-ingress 0.25). — DoD: annotation names confirmed against the deployed controller version; version recorded in the PR description.

- [ ] 2. **Draft shared Helm partial for rate-limit annotations** (depends on 1) — Add a helper template `_ingress-ratelimit.yaml` (or equivalent) to the shared Helm base layer in mctl-gitops that emits the three annotations with configurable default values. — DoD: template renders correctly in a local `helm template` dry-run for all three tenant values files.

- [ ] 3. **Apply annotation to `labs` Ingress** (depends on 2) — Reference the shared partial in `tenants/labs/ingress.yaml` (or equivalent). Merge PR and let ArgoCD sync. — DoD: `kubectl describe ingress -n labs openclaw` shows the three annotations at their configured values; nginx config reloaded without error.

- [ ] 4. **Validate rate-limit behaviour on `labs`** (depends on 3) — From a test machine, send 50 rapid WebSocket Upgrade requests from a single IP. Confirm requests 21–50 receive HTTP 429. Confirm a legitimate single connection still succeeds. — DoD: HTTP 429 observed for excess requests; no false positives for single-connection test; events logged in ingress access log with rule tag.

- [ ] 5. **Monitor `labs` ingress logs for 24 h** (depends on 4) — Confirm no legitimate clients are being rate-limited (no unexpected 429s in normal traffic patterns). Adjust threshold if needed. — DoD: zero unexpected 429s from known legitimate clients; memory delta on openclaw pod is zero.

- [ ] 6. **Apply annotation to `admins` Ingress** (depends on 5) — Same as task 3 for the `admins` tenant. — DoD: `kubectl describe ingress -n admins openclaw` shows annotations; no disruption to normal traffic.

- [ ] 7. **Apply annotation to `ovk` Ingress** (depends on 6) — Same as task 3 for the `ovk` tenant. Prefer a low-traffic window. — DoD: `kubectl describe ingress -n ovk openclaw` shows annotations; existing WebSocket sessions unaffected (rate limit applies to new Upgrade requests only).

- [ ] 8. **Document threshold rationale in runbook** — Add a short note to the ops runbook (or inline in the Helm values comment) explaining the chosen thresholds and how to tune them. — DoD: comment or runbook entry committed; reviewable by an on-call engineer without additional context.

## Tests

- [ ] T1. Burst test (labs): send 100 concurrent WebSocket Upgrade requests from a single IP; confirm ≥70 receive HTTP 429 and none cause openclaw process errors.
- [ ] T2. Legitimate-use test (labs): open 3 concurrent WebSocket connections from a single IP (simulating a normal client); confirm all 3 connect successfully.
- [ ] T3. After all tenants: confirm existing long-lived WebSocket sessions on `ovk` (Discord, Slack) are not disconnected by the new annotation (limit-connections applies to new upgrades, not existing connections).
- [ ] T4. Memory test: `kubectl top pod -n labs` before and after annotation deployment — confirm zero delta.

## Rollback

1. Remove the three `nginx.ingress.kubernetes.io/limit-*` annotations from the affected tenant's Ingress resource in mctl-gitops.
2. Open a PR, merge, let ArgoCD sync.
3. Nginx configuration reloads within seconds; rate limiting stops immediately.
4. No openclaw pod restart required.
