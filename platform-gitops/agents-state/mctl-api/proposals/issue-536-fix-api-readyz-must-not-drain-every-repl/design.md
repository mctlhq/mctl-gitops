# Design: issue-536-fix-api-readyz-must-not-drain-every-repl

## Current state
- `internal/api/ready.go` `handleReadyz` builds a list of four `ReadyCheck` probes from `Options` (`GitopsReady`, `PostgresReady`, `DexReady`, `VaultReady`). It runs them concurrently. Each probe runs in its own goroutine with `context.WithTimeout(r.Context(), readyCheckTimeout)` (2s), and a `nil` probe is reported as `not_configured`. Any probe error records `unavailable` with `fail: true`, which sets `ready = false`.
- The same handler checks `Options.StoreInitFailures` (mctl-api#387) without any network I/O. A non-empty result reports `checks.stores = "init_failed"`, adds `failed_stores`, and returns 503.
- Response: `writeJSON(w, code, {"status": "ready"|"not ready", "checks": {...}, "failed_stores"?: [...]})`.
- Probe wiring is in `cmd/api/main.go` (around lines 825-848):
  - `gitopsReady`: `LastSync` is non-zero and `ListTenants` succeeds.
  - `postgresReady`: the audit log's `Ping`.
  - `dexReady`: `HTTPReady` on the OIDC discovery document, only when Dex is configured.
  - `vaultReady`: `vault.Client.Health` (`internal/vault/client.go`).
  - Everything is passed into `mctlapi.NewRouter(Options{...})` (around line 895).
- `internal/api/router.go` documents these options at lines 184-195 ("A nil check ... does not fail readiness"; "any entry keeps GET /readyz at 503"). It mounts `/healthz`, which always returns 200, and `/readyz` at lines 262-266. Prometheus collectors are registered in `init()` with `prometheus.MustRegister` (router.go:790-809, handlers_identity_link.go:121).
- Graceful shutdown in `cmd/api/main.go` (around lines 950-963) waits on `rootCtx.Done()`, then calls `stopSignals()` and `srv.Shutdown`. Nothing tells the handler that a drain is in progress.
- Helm (`helm/templates/deployment.yaml:191-204`): the liveness probe calls `/healthz` every 30s. The readiness probe calls `/readyz` every 10s with timeout 5s and failureThreshold 6.
- Tests in `internal/api/ready_test.go` currently assert that a failed probe gives 503 (`TestReadyz_FailedProbeReturns503`, `TestReadyz_SlowProbeDoesNotStarveOthers`). Those assertions encode the behaviour this issue removes.
- Consumers in mctl-gitops (read only, not changed here):
  - `vm-rules/mctl-api-alerts.yaml`: `MctlApiDown` uses the blackbox probe of `https://api.mctl.ai/healthz` through Traefik. `MctlApiNoReadyReplicas` averages `kube_deployment_status_replicas_available`. Both descriptions tell on-call to read `readyz probe failed` logs to find the failing dependency.
  - `otel-collector.yaml` drops `/readyz` spans.
  - No rule reads the `/readyz` status code directly.

## Proposed solution
Chosen approach: **keep dependency status in the `/readyz` body, but exclude it from the status code, and export it as a metric.** There is no new endpoint.

1. `internal/api/ready.go`
   - Keep running the probe fan-out exactly as today: concurrent goroutines, each with its own `readyCheckTimeout` context. Hanging probes therefore still return within about 2s.
   - Drop `fail` from the readiness decision. The `result.fail` field becomes "dependency down" and feeds a new aggregate `dependencies` value:
     - `"ok"` when every configured probe succeeded;
     - `"degraded"` when at least one configured probe failed;
     - `"not_configured"` when no probe is configured.
   - The readiness decision (`ready`) is computed only from pod-local conditions:
     - `StoreInitFailures()` is non-empty: `checks.stores = "init_failed"` plus `failed_stores`. This logic is unchanged.
     - The new `Options.Draining func() bool` returns true: `checks.shutdown = "draining"`. When the option is unset, nothing is reported (tests stay unchanged).
   - Add a package-level `dependencyUp = prometheus.NewGaugeVec({Name: "mctl_api_dependency_up", Help: ...}, []string{"check"})`, registered in `init()`. Set it after each configured probe completes: 1 on success, 0 on failure. `not_configured` probes are not set, so no series exists for them.
   - Update the `ReadyCheck` doc comment: probes are reported only and never fail the pod.
2. `internal/api/router.go`: update the `Options` comments for `GitopsReady`/`PostgresReady`/`DexReady`/`VaultReady` (reported in the body and in metrics, never fail readiness). Add `Draining func() bool` with a comment.
3. `cmd/api/main.go`: add `var draining atomic.Bool`. Pass `Draining: draining.Load` into `Options`. Call `draining.Store(true)` right after `<-rootCtx.Done()` and before `srv.Shutdown`.
4. Documentation: update `README.md` and `LLMS.md` to say that `/readyz` fails only on store init failure or drain, and that dependency health is in the body (`checks`, `dependencies`) and in `mctl_api_dependency_up`.

Why this way: the issue asks for one approach to be chosen. Keeping the data in the existing body has three advantages:
- Nothing needs to be re-plumbed: same handler, same probes, same JSON keys, so humans already curling `/readyz` still see each dependency.
- The gauge gives alerting a proper signal, which a status code never did for a single dependency.
- It avoids a second unauthenticated endpoint that would also need to be added to `helm/templates/ingress.yaml`, `helm/values.yaml` (allow-listed paths), the tracing/logging skip lists in `router.go:813` and `tracing.go:28`, and the OpenAPI spec.

## Alternatives
- **Separate `/healthz/deps` endpoint, with `/readyz` local only.** This is cleaner semantically, but it adds a new public path that must be allow-listed in `helm/templates/ingress.yaml` and `helm/values.yaml`, excluded from tracing and request logs, and documented. It also hides dependency status from the endpoint operators already look at. Rejected for a larger surface with no extra signal.
- **Quorum or "fail only if this pod alone is failing".** This would need cross-replica coordination or a shared view, and it still drains everything when the dependency is truly down. Rejected as complex and still wrong.
- **Keep failing on dependencies but raise `failureThreshold` or add hysteresis.** This only delays the total outage. The 2026-10-09 incident lasted hours, far beyond any reasonable threshold. Rejected.
- **Per-dependency criticality (for example, postgres stays critical).** Every dependency is shared by every replica, so any "critical" one brings back the same fan-out. Rejected. The routes that need a dependency already fail individually.

## Platform impact
- **Migrations:** none.
- **Backward compatibility:** the JSON keys and values are unchanged. `dependencies`, and optionally `checks.shutdown`, are additive. The behavioural change is intended: dependency failures now return 200. Nothing in mctl-gitops keys off the `/readyz` status code. `MctlApiDown` probes `/healthz` through Traefik, and `MctlApiNoReadyReplicas` uses available replicas. Both still make sense: they now fire only on real pod or edge failures, not on dependency outages.
- **Observability loss and mitigation:** before this change, a dependency outage surfaced (indirectly) as an API outage that set off `MctlApiDown`. After it, a dependency outage is silent unless someone alerts on `mctl_api_dependency_up`. **Gitops follow-ups for the PR description** (not done in this PR):
  1. Add a `MctlApiDependencyDown` VMRule on `min by (check) (mctl_api_dependency_up) == 0 for 5m` (warning). Ensure vmagent scrapes `/metrics`; it already does for the `http_*` series.
  2. Update the `MctlApiDown` and `MctlApiNoReadyReplicas` descriptions in `vm-rules/mctl-api-alerts.yaml` and their test fixtures in `vm-rules/tests/mctl-api-alerts_test.yaml`. They say the `readyz probe failed` log "names the failing dependency". The new causes of unreadiness are a store init failure (`failed_stores`) or draining.
  3. Optionally add the gauge to `mctl-platform-dashboard-configmap.yaml`.
- **Freshness of the gauge:** probes run only when `/readyz` is called. Kubelet calls it every 10s per pod, so the gauge is at most about 10s stale while the pod is running. This is documented in the metric's Help text.
- **Resource impact:** negligible. One gauge vector with at most four series, and the same probe load as today.
- **Risk:** a pod-local fault that shows up only as a dependency probe failure, such as a broken network namespace or a bad DNS config in one pod, no longer removes that pod from rotation. This is accepted: such a pod still fails only the routes that need the dependency, and the gauge identifies it per pod. Mitigation: the per-pod `instance` label on `mctl_api_dependency_up` lets an alert catch a single pod disagreeing with its peers.
