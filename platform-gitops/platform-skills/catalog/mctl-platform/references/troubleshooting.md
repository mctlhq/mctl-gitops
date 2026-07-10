# Troubleshooting Guide

## Service Not Starting

```
mctl_get_service_status(team, service)
→ check: Synced? Healthy? If Degraded → read message

mctl_get_service_logs(team, service, since="15m", lines="200")
→ look for: crash reason, missing env var, port mismatch

mctl_get_resource_usage(team)
→ check: pods vs quota, memory headroom
```

Common causes:
- Wrong port (default template expects 8080 — check Dockerfile `EXPOSE`)
- Missing required env var or secret
- Quota exhausted — need to scale down another service first

## Build Failed

```
mctl_get_workflow_status(workflow_name)
→ read build step logs for the error
```

Common causes:
- Dockerfile syntax error or missing dependency
- Repo not accessible — check with `mctl_list_repos` or `mctl_grant_repo_access`
- OOM during build — large Node/Go builds can exceed builder memory

## CPU Throttling / `CPUThrottlingHigh` Alerts

Each tenant namespace has a `LimitRange` that sets a **default container CPU
limit of 500m**. A pod spec without an explicit `limits.cpu` silently inherits
that default — useful for safety, fatal for sidecars with bursty workloads.

Symptoms:
- `CPUThrottlingHigh` alert, throttled CFS periods > 25% over 15m.
- `mctl_get_resource_usage` shows low average CPU, but the pod still throttles
  (peaks bury the average).

Diagnosis: get the container's actual limit and compare against burst peaks.

Fix patterns:
- **Set the limit explicitly** above the LimitRange default in the chart's
  `extraContainers[*].resources.limits.cpu`. Don't rely on omitting the field —
  LimitRange will inject 500m.
- The limit must fit under the tenant's `ResourceQuota` `limits.cpu` (default
  3 CPU) and the per-container `LimitRange` `max` (1500m for legacy labs,
  2 for everything else).
- For known bursty sidecars (e.g. openclaw `s3-sync` running `mc mirror` every
  10s), 1000m is the standard default — covers the burst, fits all quotas.

Real platform components watch for the same trap: argo-workflows controller and
loki-stack promtail both got their limits raised in mctl-gitops `1.5.0`-era
changes after chronic throttling.

## OOM / CrashLoop

```
mctl_get_service_logs(team, service, since="30m", lines="500")
→ look for: "OOMKilled", exit code 137, "JavaScript heap out of memory"
```

Fix:
```
mctl_deploy_service(
  action="update-config",
  team_name="...",
  component_name="...",
  # increase memory limit in config
)
```
Or switch to a template with higher defaults (e.g. `openclaw` → 1Gi).

## ArgoCD Sync Stuck / OutOfSync

```
mctl_get_service_status(team, service)
→ check sync status and message

mctl_get_service_config(team, service)
→ verify values match expected state
```

If stuck after a config change, a redeploy with `update-config` usually forces a resync.

## Tenant Created But Invisible

When a tenant was created from `mctl.ai` or Backstage but a tool reports `tenant not found`, check the three read models separately:

1. **GitOps/Kubernetes:** `mctl-gitops/platform-gitops/tenants/<tenant>/values.yaml`, ArgoCD Application `tenant-<tenant>`, and namespace `<tenant>`.
2. **Portal/OIDC:** Backstage database `backstage`, schema `tenant-management`, tables `tenants` and `tenant_members`. OIDC groups are derived from `tenant_members`, not from ArgoCD or Kubernetes RBAC.
3. **mctl-api:** local GitOps reader cache. The live `admins-mctl-api` ArgoCD Application deploys the pod in namespace `mctl-api`. Check `kubectl logs -n mctl-api deploy/mctl-api` for `gitops refresh failed`.

Known failure mode: if the `mctl-api` cache branch diverges from `origin/main`, old builds that use `git pull --ff-only` can keep serving stale tenants even while GitOps, ArgoCD, Kubernetes, and Portal/OIDC are correct. The durable fix is in `mctl-api`'s GitOps reader; a pod restart only clears the `emptyDir` cache as a short-term mitigation.

## Workflow Stuck / No Progress

```
mctl_get_workflow_status(workflow_name)
→ check which step is running or failed
→ open https://workflows.mctl.ai/workflows/{namespace}/{workflow_name} for full logs
```

If a workflow is truly stuck (>15min with no progress), report to user — manual intervention in Argo Workflows UI may be needed.

## Argo Workflows Persistence Errors

If `https://workflows.mctl.ai` returns 500 or UI fails to load archived workflows:
- **Error:** `column "creationtimestamp" does not exist`.
- **Error:** `operator does not exist: text -> unknown`.

**Cause:** DB schema mismatch in `shared-pg` (database `argo-workflows`, table `argo_archived_workflows`).
**Fix:**
1. Scale controller and server to 0.
2. Manually fix schema in Postgres (use `jsonb` for workflow data, ensure all columns like `clustername`, `creationtimestamp`, `uid` exist).
3. Update `schema_history` to a high version (e.g. 100) to stop broken automatic migrations.
4. Scale back to 1.

## Admin Access (OpenClaw)

If a user gets "Access Denied" in Telegram:
1. Check if `dbInitJob` was enabled in `values.yaml`.
2. If not, enable it and set the correct Telegram ID.
3. If the Job already ran but failed, ArgoCD will retry on next Sync.
4. Manual fix: `kubectl exec` into Postgres and run the `INSERT` query from `values.yaml`.

## Domain Not Resolving

```
mctl_list_domains(team)
→ check domain status

mctl_verify_domain(team, service)
→ check CNAME is pointing correctly
```

Required CNAME: `{team}-{service}.mctl.ai` (or ask `mctl_verify_domain` for the exact target).
DNS propagation can take up to 10 minutes.

## Rollback

```
mctl_rollback_service(team_name, component_name, target_tag)
```

## mctl-agent: Stale Tickets / Daily Digest Noise

mctl-agent (≥ 1.5.0) auto-resolves stale tickets and filters noise. Two
controls in env:

- `AUTO_RESOLVE_STALE_AFTER` (default `24h`) — open tickets whose `UpdatedAt`
  has not advanced within the window are auto-resolved by the poller.
- `ALERT_IGNORE_SERVICE_REGEX` — services matching the regex are dropped
  before ticket creation (default covers `openclawpr\d+`, `*-demo\d*`,
  `hooktest-*`, `svcprobe-*`, `external-agent-demo*`, `auto-remediation-demo`).
  Empty string explicitly disables the filter.

Heartbeat contract — only ticket types and sources that emit `Touch` on
duplicate signals are GC-eligible:
- Types: `argocd_app_degraded`, `pod_crashloop`, `resource_limit`,
  `workflow_failed`, `generic`, `github_actions_failed`.
- Sources: `alertmanager`, `polling`, `github_webhook`. `SourceManual`
  (from `TriggerAnalysis`) is preserved — never auto-resolved.
- ArgoCD-degraded GC also requires the current poll cycle to have
  successfully refreshed that specific service via `mctl-api`.

Adding a new ticket type or source means wiring a `store.Touch` call in
its duplicate-detection path before adding it to the whitelist in
`internal/monitor/poller.go`.

## Custom Alerts (mctl-custom-alerts VMRule)

Beyond the upstream `victoria-metrics-k8s-stack` rules, the platform deploys
`mctl-custom-alerts` (`platform-gitops/infra-components/observability/vm-rules/mctl-alerts.yaml`):

- `mctl.tenant-quotas`: `TenantCPUQuotaHigh`, `TenantMemoryQuotaHigh` — fire
  at >85% of a namespace's `ResourceQuota` hard `limits.{cpu,memory}`.
- `mctl.node-health`: `NodeHighCPU` (>90% 15m), `NodeHighMemory` (>90% 15m),
  `NodeDiskPressure`.
- `mctl.vault`: `VaultSealed`.

All four route to the `mctl-agent` webhook receiver via the Alertmanager
`alertname =~` matcher in `monitoring.yaml`. Add new alert names to that
matcher when extending `classifyAlert` in mctl-agent.

Use when a new deploy caused regressions. `target_tag` is the previous image tag (visible in `mctl_get_service_config`).
