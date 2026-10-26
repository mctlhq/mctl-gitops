# Design: issue-812-feat-api-tenant-scoped-pod-state-and-eve

## Current state
- **Kubernetes access.** `internal/k8s/quotas.go` builds a clientset with `newClientset()` (in-cluster, KUBECONFIG fallback). It exposes `QuotaClient.GetNamespaceUsage` (ResourceQuota) and `NamespaceAbsent`. `internal/k8s/previews.go` (`PreviewClient.ListPreviewReleases`) lists Deployments in `{team}-preview`, reports an observed namespace NotFound as `ErrNamespaceAbsent`, and treats every other failure as an error. `internal/k8s/agent_run_binding.go` already does a `Pods(ns).Get`. Nothing lists pods or events.
- **Interfaces and wiring.** `internal/api/interfaces.go` declares `QuotaReader` and `PreviewLister`. `internal/api/router.go` `Options` carries them as optional fields. `cmd/api/main.go` (~L951-963) builds them and logs a warning when the client is unavailable. `ListPreviews` answers 503 when its lister is nil.
- **Tenant reads.** `GetResourceUsage`, `ListPreviews` and `GetServiceLogs` in `internal/api/handlers_read.go` all gate with `!user.IsAdmin() && !user.HasTenantAccess(team)` and answer 403. `GetServiceLogs` uses namespace = team. Loki selects pods by `pod=~"{ns}-{app}-.+"` (`internal/loki`), and the ArgoCD app is `{team}-{app}`. A tenant's namespace is the tenant name: `GetNamespaceUsage(r.Context(), tenant)`.
- **Routes.** These live in the authenticated group of `internal/api/router.go` (~L565-570): `/workflows`, `/previews`, `/logs/{team}/{app}`, `/resources/{tenant}`.
- **MCP.** `internal/mcp/server.go` registers tools in `NewMCPServer` (read tools ~L249-257). Example: `toolGetResourceUsage` uses `mcplib.WithReadOnlyHintAnnotation(true)` and `WithDestructiveHintAnnotation(false)` and calls `s.apiGet`. `internal/mcp/annotations_test.go` holds `recordedHints` and `TestReadOnlyToolsAreTheRecordedSet`. `server_test.go` `TestNewMCPServer_ToolCount` compares against `len(recordedHints)`. `internal/mcp/agent_scope_test.go` `TestReadToolsAreRecordedReadOnly` holds `auth.IsReadTool` (`internal/auth/agent_scope.go`, verbs `get_/list_/read_/search_/describe_`) to those annotations.
- **Agent scopes.** `agentScopes[AgentScopeInvestigate]` in `internal/auth/agent_scope.go` has `ReadAllTenants: true` and an explicit GET route allowlist. A new REST route is unreachable for that scope until it is added there. `User.HasTenantAccess` (`internal/auth/oidc.go`) returns true for admins, for `ReadAllTenants` scopes and for group == tenant. No support scope or bound-tenant concept exists yet (S0a).
- **The leak.** `Handlers.ListWorkflows` (`internal/api/handlers_read.go` ~L355) skips a row for non-admins only when `e.ParametersUnreadable || (team != "" && !user.HasTenantAccess(team))`. A row with `team == ""` (`auditEntryTenant` found no `tenant_name`/`team_name`) passes for every caller. `GetWorkflow` already refuses a non-admin when no audit entry is found, and it 503s an unreadable one.
- **Secret scanning.** `internal/secretscan.Scan(content) (pattern, found)` detects secret patterns. It does not redact.

Deployed state checked:
- `mctl_get_service_status(namax66, news-factory)`: ArgoCD app `namax66-news-factory`, Healthy/Synced, image 0.1.4, base-service. This confirms the `{team}-{app}` naming that the pod selector relies on.
- `mctl_list_workflows()` with this run's investigate-scope token: 21 rows, all with `team: ""` (`mctl-agents-*`, `dev-loop-*`, `mctl-agents-approve`). This shows that empty-tenant platform rows reach non-admin callers today.
- `$MCTL_GITOPS_ROOT/tenants/namax66/values.yaml`: quotas `pods: "5"`, `limits.memory: 1Gi`, a LimitRange with max memory 1Gi. These are the limits whose violations surface as `FailedCreate ... exceeded quota` events.
- `$MCTL_GITOPS_ROOT/services/namax66/news-factory/values.yaml`: memory limit 512Mi (headless Chromium). This is a plausible OOMKilled source, matching the issue's motivation.
- mctl-api ServiceAccount RBAC: **not observed**. `helm/templates/` has only `serviceaccount.yaml` (no Role/ClusterRole), and the visible gitops checkout contains only `services/` and `tenants/`. Whether `list pods`/`list events` is granted in tenant namespaces is unknown; see Open questions.

## Proposed solution

### 1. `internal/k8s/workload.go` (new): `WorkloadClient`
```go
type WorkloadClient struct{ client kubernetes.Interface }
func NewWorkloadClient(cs kubernetes.Interface) *WorkloadClient
func NewWorkloadClientFromEnv() (*WorkloadClient, error)   // uses newClientset()
func (c *WorkloadClient) ListServicePods(ctx, namespace, workload string) ([]PodState, error)
func (c *WorkloadClient) ListEvents(ctx, namespace string, opts EventQuery) (events []Event, truncated bool, err error)
```
- **`ListServicePods`** lists pods with `LabelSelector: app.kubernetes.io/instance=<workload>`, where workload = `{team}-{app}`. If that returns zero, it lists the namespace and keeps pods whose name has the prefix `workload + "-"`, the same rule as Loki. Each pod is mapped into allow-listed DTOs, never by marshaling `corev1.Pod`:
  - `PodState{Name, Phase, Ready bool, Reason, Message, CreatedAt, StartedAt, ImagePullSecretNames []string, InitContainers, Containers []ContainerState}`
  - `ContainerState{Name, Image, Ready, RestartCount, State StateDetail, LastTermination *StateDetail, Requests, Limits map[string]string}`
  - `StateDetail{Kind: running|waiting|terminated, Reason, Message, ExitCode *int32, Signal *int32, StartedAt, FinishedAt}`

  `Requests` and `Limits` reuse `resourceListToStrings` from quotas.go. Env, envFrom, volumes, command/args and annotations are never copied. Building DTOs field by field is what guarantees the "no secret/env values" criterion, and a reflection test (T3) pins it.
- **`ListEvents`** lists core `v1` Events in the namespace. It filters by last timestamp (`LastTimestamp`, falling back to `EventTime`, then `FirstTimestamp`) >= now-since, plus the optional `Type` and the optional involved-object-name prefix. It sorts newest first and caps at `Limit` (default 200), reporting `truncated`. Core v1 events are used because client-go's `CoreV1().Events` is already in the dependency set and covers every source. The time filter runs client-side because there is no field selector on timestamps.
- **Message scanning.** Both methods run `secretscan.Scan` on every `Message` (event, waiting and terminated state messages) and replace a hit with `[redacted: <pattern>]`. Terminated-state messages can carry a container's termination log.
- **Errors** are wrapped with `fmt.Errorf("listing pods in %s: %w", ns, err)`. Nothing returns an empty slice on error.

### 2. API surface
- **`interfaces.go`**: add `WorkloadReader` with the two methods. `router.go` `Options`: `WorkloadReader WorkloadReader` (optional). `cmd/api/main.go`: build it next to `previewLister` with the same warning pattern.
- **New file `internal/api/handlers_workload.go`:**
  - `GetServicePods`: `GET /api/v1/pods/{team}/{app}`
  - `ListNamespaceEvents`: `GET /api/v1/events/{team}?since=1h&app=&type=`

  Both handlers follow `ListPreviews` exactly: 401 without a user, then `!user.IsAdmin() && !user.HasTenantAccess(team)` gives 403 **before** any Kubernetes call, nil reader gives 503, a Kubernetes error is logged with `slog.Warn` and answered 503 with "could not list pods in <ns>". Path params are validated against the DNS-label pattern (`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`, 400 otherwise), so a crafted team cannot address another namespace. `since` uses `time.ParseDuration`, bounded 1m..24h (400 outside). Responses are `{"items": [...], "count": n, "team": ..., "namespace": ...}`, plus `"service"` for pods and `"since"`/`"truncated"` for events.
- **Routes** are added in the authenticated group next to `/logs/{team}/{app}`.
- **`internal/auth/agent_scope.go`**: add `getRoute("^/api/v1/pods/[^/]+/[^/]+$")` and `getRoute("^/api/v1/events/[^/]+$")` to `AgentScopeInvestigate`. S0a's support scope will list them too.

### 3. MCP tools (`internal/mcp/server.go`)
- `mctl_get_service_pods(team, service)` calls `/api/v1/pods/{team}/{service}`.
- `mctl_list_namespace_events(team, since?, service?, type?)` calls `/api/v1/events/{team}`.

Both are registered in the read block and declare title, `ReadOnlyHint(true)`, `DestructiveHint(false)` and `IdempotentHint(false)` (matching neighbouring live reads). Each is added to `recordedHints`, to the `want` list in `TestReadOnlyToolsAreTheRecordedSet` and to `TestToolDescriptions_NotEmpty`. `TestNewMCPServer_ToolCount` follows `recordedHints` automatically. Both names satisfy `auth.IsReadTool`, so `TestReadToolsAreRecordedReadOnly` covers them. The descriptions state that no env or secret values are returned.

### 4. Workflow leak (`ListWorkflows`)
Replace the inline condition with a helper in `handlers_read.go`:
```go
// workflowRowVisible: rows of a tenant need access to that tenant; rows
// without a readable tenant are platform rows and need platform read.
func workflowRowVisible(u *auth.User, team string, unreadable bool) bool {
    if u.IsAdmin() { return true }
    if bound, ok := u.BoundTenant(); ok { return !unreadable && team != "" && team == bound }
    if unreadable || team == "" { return platformReader(u) }
    return u.HasTenantAccess(team)
}
```
- `platformReader(u)` is true only for an agent scope with `ReadAllTenants` (today only `AgentScopeInvestigate`). Ordinary tenant members, service users that are not admins, and CI identities get false.
- `auth.User.BoundTenant() (string, bool)` is added in `internal/auth` as returning `("", false)` until S0a defines the support scope. S0a then implements it from the support token's binding. If S0a merges first, this task uses S0a's accessor directly. The test for the bound rule constructs a user via the S0a constructor when available. Otherwise it is added in S0a with the accessor (tasks.md 6).
- The unreadable row stays hidden from non-admins even for `platformReader`, preserving the current behaviour and the mctl-api#586 reasoning.

## Alternatives
1. **Reuse the ArgoCD resource tree** (ArgoCD reports pod health and events) instead of the Kubernetes API. Dropped: ArgoCD's resource-tree view lacks last termination reason, exit codes and requests/limits, events would need a per-resource call, and it hides pods that ArgoCD does not track (failed ReplicaSet creations are precisely `FailedCreate` cases).
2. **Return raw `corev1.Pod` / `corev1.Event` JSON with fields stripped.** Dropped: a deny-list leaks every new field Kubernetes adds (env, envFrom, projected volumes). An allow-listed DTO is the only shape that makes "no env values" provable.
3. **Fix the leak by hiding empty-tenant rows from all non-admins, including investigator scopes** (the literal reading of the issue). Dropped as the default because the investigator scope already reads every tenant and diagnoses platform workflows through these rows. It is recorded as an open question; tightening is a one-line change in `platformReader`.
4. **Use `events.k8s.io/v1`** instead of core v1. Deferred: it needs separate RBAC with no data gain for this use, and core v1 reads see the same objects.

## Platform impact
- **Migrations**: none. No database or audit schema changes.
- **Backward compatibility**: new routes and tools are additive. `GET /api/v1/workflows` returns fewer rows to non-admin tenant callers, which is the intended fix. The MCP tool count rises by 2, and the portal read-only allowlist copied from `TestReadOnlyToolsAreTheRecordedSet` must add the two names.
- **RBAC**: the mctl-api ServiceAccount needs `list` on `pods` and `events` in tenant namespaces. Where that RBAC is managed was not observed (Open questions). Without it the endpoints answer 503, never an empty "healthy" answer.
- **Resource impact**: each call is one namespaced LIST. Tenant namespaces are small (namax66 `pods: 5`). The events list is bounded by Kubernetes' 1h default event TTL, and the response is capped at 200 items.
- **Risks and mitigations**:
  - Cross-tenant read through a crafted path: DNS-label validation, plus the access check before the Kubernetes call. Tests T1/T2 fail if the check is removed.
  - Secret leakage through messages: allow-listed DTOs plus a `secretscan` pass, and reflection test T3.
  - Exposure to support scopes before S0c read audit exists: accepted by the epic's phasing, because S0c follows.
