# Requirements: incident-84e0e5bf

## Incident
- ID: 4399cb28-67b6-47a2-9c27-4f7a84e0e5bf
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-20T15:38:20.445929Z

### Summary
```
ArgoCD application admins-mctl-agents-worker OutOfSync for 1h
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: admins
service: admins-mctl-agents-worker
trace_id: 955e020bae1b920e4056114bdcaba680
```

### Log Snippet
```
ArgoCD status (mctl_get_service_status): health=Healthy, syncStatus=OutOfSync, revision="" (empty), imageTag=1.117.0, project=apps, destNamespace=admins
Pod logs (last 50 lines) show only routine worker activity: execution-request claim POLICY_DECISION ALLOW lines, gh api polling, Temporal dev-loop activity.
WARNING: merge gate identity for dev-loop-mctlhq-mctl-agents-1014 could not be stored in mctl-api (POST /api/v1/agents/executions/context returned 404)
warn: gh graphql branch-protection probe failed for mctlhq/mctl-agents@main: gh: Resource not accessible by integration
No log line refers to ArgoCD, sync, or manifest rendering.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
