# Requirements: incident-0b2f8701

## Incident
- ID: 2716bf8f-1536-4b06-b502-af870b2f8701
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-15T02:11:20Z

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
analysis: no skill matched this ticket (type=argocd_app_degraded, alert=ArgoCDApplicationOutOfSyncLong)
```

### Log Snippet
```
Service status (mctl_get_service_status): ArgoCD health=Healthy, syncStatus=OutOfSync, imageTag=1.117.0, project=apps, destNamespace=admins, revision empty.
Worker logs (last hour) show no crash or error for the pod itself. Only unrelated warnings:
WARNING:temporalio.workflow: merge gate identity for dev-loop-mctlhq-mctl-agents-986 could not be stored in mctl-api (degraded to an unverified local context)
INFO:httpx: POST https://api.mctl.ai/api/v1/agents/executions/context "HTTP/1.1 404 Not Found"
warn: gh graphql branch-protection probe failed for mctlhq/mctl-agents@main: Resource not accessible by integration
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN ArgoCD is refreshed THEN admins-mctl-agents-worker reports syncStatus=Synced.
