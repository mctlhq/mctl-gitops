# Requirements: incident-a6be7604

## Incident
- ID: b9192ad2-116a-425e-8fa8-9a79a6be7604
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-09T19:38:20.35695Z

### Summary
```
ArgoCD application admins-mctl-agents-worker OutOfSync for 1h
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
confidence: LOW
analysis: Escalated: no skill matched this ticket (type=argocd_app_degraded, alert=ArgoCDApplicationOutOfSyncLong). No diagnostic rule for this signal.
```

### Observed State (independent, from platform tools)
```
ArgoCD app admins-mctl-agents-worker: health=Healthy, syncStatus=OutOfSync, revision="" (empty), project=apps, namespace=argocd, updatedAt=2026-11-09T20:05:00Z
Service imageTag=1.117.0, componentType=base-service, hasDatabase=false
```

### Log Snippet
```
Last 50 lines of the worker pods (admins-mctl-agents-worker and -exec) show normal operation:
- POLICY_DECISION ... decision ALLOW (claim:execution-request) repeating every ~15s
- httpx GET/POST to api.mctl.ai returning 200/202
- warn: gh graphql branch-protection probe failed for mctlhq/mctl-agents@main: gh: Resource not accessible by integration
- WARNING: merge gate identity for dev-loop-mctlhq-mctl-agents-986 could not be stored in mctl-api (POST /api/v1/agents/executions/context returned 404)
None of these relate to ArgoCD sync state.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the ArgoCD application is inspected THEN syncStatus is Synced.
