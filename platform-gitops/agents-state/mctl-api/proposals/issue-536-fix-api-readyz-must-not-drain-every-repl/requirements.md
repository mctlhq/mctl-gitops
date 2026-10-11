# Decouple /readyz from shared-dependency health so one outage cannot drain every replica

## Context
`handleReadyz` in `internal/api/ready.go` runs four live dependency probes (gitops, postgres, dex, vault) and also checks `StoreInitFailures`. Today any probe failure sets `ready = false` and returns 503. Every replica probes the same shared dependencies, so one shared outage makes every pod not-Ready at once. Kubernetes then removes every endpoint and Traefik answers "no available server" for the whole API, including the routes that never touch the failing dependency. This happened on 2026-10-09: a Vault probe that timed out from inside the pod kept mctl-api unready for about five hours (see the comments in mctl-gitops `vm-rules/mctl-api-alerts.yaml` and `blackbox/vmprobes.yaml`).

The readiness probe should take one bad pod out of rotation. It should not turn a shared-dependency failure into a total outage. This proposal makes `/readyz` fail only on pod-local conditions: a store failed its startup init (mctl-api#387), or the pod is shutting down. Dependency status stays observable in two places: the `/readyz` JSON body, which no longer affects the status code, and a new Prometheus gauge.

## User stories
- AS a platform operator I WANT a Vault, Postgres, gitops or OIDC outage to degrade only the features that need that dependency SO THAT api.mctl.ai keeps serving everything else.
- AS an on-call engineer I WANT every dependency's health to stay visible in `/readyz` and in metrics SO THAT I can still see and alert on a dependency outage after it stops failing readiness.
- AS a Kubernetes rollout I WANT a pod whose store failed startup init to stay not-Ready SO THAT a rolling update keeps the old, working pod.

## Acceptance criteria (EARS)
- WHEN `/readyz` is requested and every configured dependency probe fails but `StoreInitFailures` returns no entries THE SYSTEM SHALL respond 200 with `status: "ready"`, report each failed dependency as `"unavailable"` under `checks`, and set `dependencies: "degraded"`.
- WHEN `/readyz` is requested and `StoreInitFailures` returns one or more entries THE SYSTEM SHALL respond 503 with `status: "not ready"`, `checks.stores: "init_failed"` and `failed_stores` naming each store, whatever the dependency probes return.
- WHEN `/readyz` is requested while the process is draining (shutdown signal received) THE SYSTEM SHALL respond 503 with `checks.shutdown: "draining"`.
- WHEN every configured dependency probe succeeds THE SYSTEM SHALL report `dependencies: "ok"`. WHEN no dependency probe is configured THE SYSTEM SHALL report `dependencies: "not_configured"`.
- WHILE a dependency probe hangs THE SYSTEM SHALL still answer `/readyz` within about `readyCheckTimeout` (2s), because each probe runs concurrently with its own timeout. A slow probe SHALL NOT change the status code.
- WHEN a dependency probe completes THE SYSTEM SHALL set the gauge `mctl_api_dependency_up{check="<name>"}` to 1 on success and 0 on failure. Unconfigured probes SHALL NOT be exported.
- IF a dependency probe fails THEN THE SYSTEM SHALL keep logging `readyz probe failed` with the `check` name at WARN level, as it does today.
- WHILE serving `/healthz` THE SYSTEM SHALL keep the current liveness behaviour: always 200 `{"status":"ok"}`.
- The JSON body SHALL keep its existing keys and values (`status`, `checks.<name>`, `failed_stores`) so existing consumers keep parsing it. New keys are additive only.

## Out of scope
- Any change in mctl-gitops: alert rules, VMProbe, dashboards, Helm values in the bootstrap templates. Follow-ups are listed in the PR description only.
- Changing the readiness or liveness probe timings in `helm/templates/deployment.yaml`.
- Making individual API routes fail fast or circuit-break when their own dependency is down. Today they return their own errors, and that does not change.
- A separate `/healthz/deps` endpoint (rejected; see design Alternatives).
- Running probes in the background independently of kubelet calls.

## Open questions
- The issue lists "not yet initialised" as a readiness condition. In `cmd/api/main.go`, `srv.ListenAndServe` starts only after all initialisation finishes, so an uninitialised pod refuses the probe connection and is already not-Ready. This proposal therefore adds no explicit "initialised" flag. A reviewer should confirm this is acceptable.
- Draining: `srv.Shutdown` closes the listener at once, so the `draining` 503 is only visible in the short window between the signal and `Shutdown`. It is cheap and matches the issue's wording, so it is included. It can be dropped if a reviewer considers it noise.
- The gitops readiness check (`gitReader.LastSync().IsZero()`, meaning never synced) is arguably pod-local: a fresh pod that never cloned the gitops repo serves empty catalogue data. The issue explicitly lists gitops as a shared dependency, so this proposal treats it as one. If reviewers want "never synced" to stay a local readiness condition, it would need a separate check split out of the gitops probe in `cmd/api/main.go`.
