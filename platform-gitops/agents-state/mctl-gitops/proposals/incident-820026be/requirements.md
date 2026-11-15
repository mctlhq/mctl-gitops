# Requirements: incident-820026be

## Incident
- ID: 6490300b-0067-474b-b74b-e7dd820026be
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-10T10:38:20Z

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
analysis: Escalated, no skill matched (type=argocd_app_degraded, alert=ArgoCDApplicationOutOfSyncLong)
```

### Log Snippet
```
ArgoCD status (mctl_get_service_status): health=Healthy, syncStatus=OutOfSync, project=apps, namespace=argocd, imageTag=1.117.0, revision="" (empty)
Service logs (last hour) show the worker running normally: Temporal activities, claim:execution-request policy decisions ALLOW, GitHub API calls HTTP 200.
Unrelated warnings seen in the same logs:
warn: gh graphql branch-protection probe failed for mctlhq/mctl-agents@main: gh: Resource not accessible by integration
WARNING:temporalio.workflow: merge gate identity for dev-loop-mctlhq-mctl-agents-986 could not be stored in mctl-api (degraded to an unverified local context)
INFO:httpx: POST https://api.mctl.ai/api/v1/agents/executions/context "HTTP/1.1 404 Not Found"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the change is applied THEN ArgoCD reports syncStatus Synced for admins-mctl-agents-worker.
