# Design: issue-859-fix-workload-unknown-service-and-expired

## Current state
- `internal/api/handlers_workload.go`
  - `GetServicePods` validates `team`/`app` against `dnsLabelPattern`, checks access, then calls `requireRegisteredTenant(w, team)`. That function uses `GitReader.TenantExists`: missing → 404, error or nil reader → 503. Next it calls `WorkloadReader.ListServicePods(ctx, team, team+"-"+app)` and always answers 200 with `items`, `count`, `team`, `namespace`, `service`. Nothing checks that the service exists.
  - `ListNamespaceEvents` accepts `since` in `[minEventWindow=1m, maxEventWindow=24h]` (default `defaultEventWindow=1h`), `type` (Warning/Normal) and `app`. `app` becomes `EventQuery.Workload = team+"-"+app` and is not checked for existence either. The response echoes `"since": since.String()` plus `truncated`. Nothing says the cluster only holds events for its TTL.
- `internal/k8s/workload.go`
  - `ListServicePods` selects pods by `app.kubernetes.io/instance={workload}`, and when nothing matches falls back to unlabeled pods named `{workload}-*`. An empty match is `([]PodState{}, nil)`.
  - `ListEvents` lists every event in the namespace and filters by `cutoff = now - q.Since` on `eventLastSeen`. Events older than the apiserver TTL were already deleted by the apiserver, so the cutoff never removes anything older than that.
- `internal/api/interfaces.go`
  - `GitReader.ServiceExists(team, component) (bool, error)` is documented: "Only a missing path is (false, nil); a read that failed is an error". It is implemented in `internal/gitops/reader.go` (`statServiceFileLocked` on `services/<team>/<component>/values.yaml`, with a `checkFreshLocked` staleness check).
  - `ArgoStatusClient.ListWorkloads() ([]argocd.Workload, error)`. `argocd.Workload` (`internal/argocd/client.go`) has `Name`, `Project` and `DestNamespace`.
- `internal/api/handlers_write.go: checkServiceExists(team, component) (status int, msg string)` already maps `ServiceExists` to 0 / 404 / 503, with a log line that does not leak checkout paths. The write handlers use it.
- `internal/api/service_listing.go: listServiceEntries` joins catalogue rows (gitops) with ArgoCD workloads. Applications in a tenant namespace that are not catalogue rows become `managed: "external"` (project == team) or `"platform"` rows. Their short name is `strings.CutPrefix(w.Name, team+"-")`. These services have no `services/{team}/{app}` directory, but `GET /pods/{team}/{app}` works for them today because their pods carry `instance={team}-{app}`.
- `internal/mcp/server.go: toolGetServicePods`, `toolListNamespaceEvents`. These are thin wrappers over the two routes (`internal/api/router.go` lines 600-601). The events tool description says "Time window, 1m to 24h (default 1h)".
- `cmd/api/main.go` builds `Options` (`WorkloadReader`, `ArgoCD`, `GitReader`) and reads duration env vars with `parseDuration(os.Getenv(...), default)`.
- Tests: `internal/api/handlers_workload_test.go` (`TestWorkloadReads_TenantGate`, `TestListNamespaceEvents_Params`, `TestWorkloadReads_Unavailable`, `TestWorkloadReads_OnlyRegisteredTenants`).

Deployed state checked:
- `mctl_list_services(team=labs)`: `argocd: ok, complete: true`, 20 rows, all `managed: catalogue` with `argoApp = labs-<name>`. This confirms that the `{team}-{app}` workload naming the pod read relies on holds for catalogue services. No external or platform rows were present in this tenant, so the ArgoCD fallback path could not be confirmed against a live external row.
- `$MCTL_GITOPS_ROOT/services/`: tenants `admins`, `karabu`, `labs`, `namax66`, each with `services/<tenant>/<service>/` directories. This is the source `ServiceExists` reads. mctl-api itself is not under `services/`, so its deployment env (where a new `WORKLOAD_EVENT_RETENTION` would be set) was not read. Its helm chart is in the repo's `helm/`.
- The apiserver `--event-ttl`: not observable with the available read-only tools. Recorded under Open questions in requirements.md.

## Proposed solution

### 1. Resolve the service before reading its workload
Add `resolveWorkloadService(w, team, app) bool` in `handlers_workload.go`, next to `requireRegisteredTenant`, with the same "write the response and return false" contract:

1. `status, msg := h.checkServiceExists(team, app)`. This reuses the existing helper, so messages and logging match the write paths.
   - `status == 0`: the service is known (catalogue), return true.
   - `status == 503`: write 503 with `msg`, return false.
   - `status == 404`: go to step 2. The gitops absence alone is not yet proof.
2. ArgoCD fallback for external and platform applications:
   - `h.opts.ArgoCD == nil`: 503 `cannot confirm whether service "{app}" exists in workspace "{team}": argocd not configured`.
   - `ListWorkloads()` error: log it (`slog.Warn`), then 503 with the same message, ending `right now; try again later`.
   - Some workload has `Name == team+"-"+app` and `DestNamespace == team`, and its name does not start with `preview-` (the filter `listServiceEntries` uses): return true.
   - Otherwise: 404 `service not found: {app} (workspace "{team}")`. The prefix is the exact one the issue asks for, so callers can match on it.

`GetServicePods` calls `resolveWorkloadService` after `requireRegisteredTenant` and before the `WorkloadReader == nil` check. A tenant or service problem is reported before "kubernetes not configured", and no Kubernetes call is made for an unknown service. `ListNamespaceEvents` calls it only when `app` is set, after the DNS-label check on `app`.

The 200 body of `GetServicePods` does not change. An empty `items` now always means "known service, no pods observed".

### 2. State the covered window for events
- Add `EventRetention time.Duration` to `Options` (`internal/api/router.go`). In `cmd/api/main.go` set it from `parseDuration(os.Getenv("WORKLOAD_EVENT_RETENTION"), time.Hour)`. Document the env var in `helm/` values as an optional key that defaults to 1h.
- In `ListNamespaceEvents`, after a successful `ListEvents`:
  - `retention := h.opts.EventRetention`; if `<= 0`, use `defaultEventRetention = time.Hour`.
  - `now := time.Now().UTC()`. `observedSince := now.Add(-min(since, retention))`.
  - Add to the response: `observed_since` (RFC 3339), `coverage_complete` (`since <= retention`), `event_retention` (`retention.String()`), and when incomplete, `coverage_note`: "the cluster keeps events for about {retention}; events before observed_since are no longer held, so their absence is unknown".
  - `since` stays the requested window, and the accepted range stays 1m–24h, so the change is additive.
- Do not change the `ListEvents` filtering. An aggregated long-lived event older than `observed_since` can still be returned, because its `lastTimestamp` is recent. `observed_since` is the lower bound of guaranteed coverage, not a filter.

### 3. MCP descriptions
- `mctl_get_service_pods`: "A service unknown to the workspace is an error (service not found), never an empty list; an empty list is a known service with no pods. If existence cannot be checked, the call fails rather than answering empty."
- `mctl_list_namespace_events`: describe `observed_since` / `coverage_complete`, say the cluster retains events for about 1h, and say an unknown `service` is an error. The tool count is unchanged, so the `server_test.go` count is unaffected.

## Alternatives
- **Gitops-only check (exactly as the issue words it).** Simplest, but it would turn today's working pod reads for `external` and `platform` services (`service_listing.go`) into 404s. That is wrong in the other direction (a real service reported as unknown). Dropped in favour of the ArgoCD fallback, which runs only when gitops says "absent".
- **Infer existence from Kubernetes (a Deployment/StatefulSet with `instance={team}-{app}`).** It would also cover external services, but it needs new Kubernetes reads and RBAC (`apps` list). It would also make a deleted-but-catalogued service look unknown. The catalogue and ArgoCD are what `mctl_list_services` already treats as the service list, so they are the consistent source. Dropped.
- **Cap `since` at the retention (reject >1h, or silently clamp).** Rejecting breaks existing callers that pass 24h. Silent clamping hides the coverage loss from callers that read only `since`. Adding `observed_since` / `coverage_complete` is additive and states the gap. Dropped, though a later change could clamp if desired.

## Platform impact
- No migrations, no new dependencies, no new RBAC.
- Backward compatibility: pod reads for unknown names change from 200-empty to 404/503. That is the intended fix, and any caller depending on the old behaviour was getting a wrong answer. The events response only gains fields. The events `app` filter gains 404/503 for unknown names.
- Availability: a pod read for a catalogue service needs only gitops, as today (the tenant check already needs it). Only names absent from gitops depend on ArgoCD. When ArgoCD is down, those answer 503 and not 404, by design.
- Cost: one `ListWorkloads` call, and only for names gitops does not know. `listServiceEntries` already makes this call per `mctl_list_services` request.
- Risk: a newly onboarded service not yet visible in a stale checkout. `checkFreshLocked` returns an error (503) on staleness, and the 404 message from `checkServiceExists` already mentions the up-to-a-minute visibility lag. The ArgoCD fallback also covers it once the app exists.
- Risk: `WORKLOAD_EVENT_RETENTION` set wrong. It is only advisory text and a timestamp. Data returned is unaffected.
