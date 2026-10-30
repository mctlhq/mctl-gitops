# Tasks: issue-859-fix-workload-unknown-service-and-expired

- [ ] 1. Add `resolveWorkloadService(w, team, app) bool` to `internal/api/handlers_workload.go`. It reuses `checkServiceExists` (`handlers_write.go`) and falls back to `h.opts.ArgoCD.ListWorkloads()` (match `Name == team+"-"+app && DestNamespace == team`, skip names prefixed `preview-`) only on a gitops 404. — DoD: it returns true for a catalogue service or a matching ArgoCD app, writes 404 `service not found: {app} ...` only when gitops says absent AND the ArgoCD list was read without a match, and writes 503 for every failed or unconfigured lookup.
- [ ] 2. Call `resolveWorkloadService` in `GetServicePods` after `requireRegisteredTenant` and before the `WorkloadReader` nil check (depends on 1). — DoD: an unknown service never reaches `ListServicePods`. The 200 body is unchanged for known services.
- [ ] 3. Call `resolveWorkloadService` in `ListNamespaceEvents` when `app` is set, after its DNS-label check (depends on 1). — DoD: `?app=<unknown>` answers 404/503 and never `200 []`.
- [ ] 4. Add `EventRetention time.Duration` to `Options` in `internal/api/router.go`. Wire it in `cmd/api/main.go` from `WORKLOAD_EVENT_RETENTION` via `parseDuration(..., time.Hour)`, and document the optional value in `helm/`. — DoD: unset means 1h. The value reaches the handler.
- [ ] 5. Extend the `ListNamespaceEvents` 200 response with `observed_since` (RFC 3339, `now - min(since, retention)`), `coverage_complete` (`since <= retention`), `event_retention`, and `coverage_note` when incomplete. Keep `since` and the 1m–24h range unchanged (depends on 4). — DoD: `since=24h` with the default retention gives `coverage_complete:false` and a note. `since=30m` gives `coverage_complete:true` and no note.
- [ ] 6. Update the descriptions of `toolGetServicePods` and `toolListNamespaceEvents` in `internal/mcp/server.go` (depends on 2, 3, 5). — DoD: the descriptions state the 404/503 semantics and the coverage fields. The tool count is unchanged.
- [ ] 7. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. — DoD: everything is clean.

## Tests
In `internal/api/handlers_workload_test.go`, using the existing GitReader and WorkloadReader fakes, plus a fake `ArgoStatusClient`:
- [ ] T1. Pods: catalogue service with zero pods → 200 `count:0`. The WorkloadReader is called once.
- [ ] T2. Pods: gitops `ServiceExists` false, ArgoCD lists no match → 404, body starts `service not found: {app}`. The WorkloadReader is never called.
- [ ] T3. Pods: gitops `ServiceExists` returns an error → 503. ArgoCD and the WorkloadReader are not called.
- [ ] T4. Pods: gitops false and `ArgoCD == nil` → 503. Gitops false and `ListWorkloads` errors → 503 (not 404).
- [ ] T5. Pods: gitops false and ArgoCD has `{team}-{app}` with `DestNamespace == team` → 200. The same name with a different `DestNamespace`, or a `preview-` app → 404.
- [ ] T6. Events: `?app=<unknown>` → 404. `?app=` with a failed lookup → 503. No `app` → no service lookup at all.
- [ ] T7. Events: `since=24h`, default retention → `coverage_complete:false`, `coverage_note` present, `observed_since` about now-1h. `since=30m` → `coverage_complete:true`, no note, `observed_since` about now-30m. `EventRetention=6h` with `since=24h` → `observed_since` about now-6h.
- [ ] T8. The existing tests (`TestWorkloadReads_TenantGate`, `TestWorkloadReads_Unavailable`, `TestWorkloadReads_OnlyRegisteredTenants`, `TestListNamespaceEvents_Params`) still pass. Adjust fixtures so the fake GitReader reports the test service as existing where those tests expect 200.
- [ ] T9. MCP: `internal/mcp/server_test.go` tool count is unchanged and still passes.

## Rollback
The change is confined to two handlers, one Options field and two tool descriptions. Revert the PR and redeploy the previous mctl-api image (helm image tag rollback). The new env var `WORKLOAD_EVENT_RETENTION` is optional, so leaving it set after a revert is harmless. There is no persisted state or migration to undo.
