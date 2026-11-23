# Requirements: incident-bdd1cf4b

## Incident
- ID: 427dfefd-411a-42f4-bf5f-3e68bdd1cf4b
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-16T02:08:20.365707Z

### Summary
```
ArgoCD application admins-mctl-agents-worker OutOfSync for 1h
```

## Evidence
### Labels
```
tenant: admins
service: admins-mctl-agents-worker
severity: warning
source: alertmanager
```

### Service State (observed independently)
```
argocd.health: Healthy
argocd.syncStatus: OutOfSync
argocd.revision: (empty)
argocd.project: apps
argocd.destNamespace: admins
imageTag: 1.117.0
componentType: base-service
```

### Log Snippet
```
The service pod is running normally. Recent logs (2026-11-16T03:08-03:11Z) show only
routine POLICY_DECISION "allowed" entries for claim:execution-request and
"gh api" issue-comment polling calls, plus HTTP 200 responses from
api.mctl.ai agent resolve/versions endpoints. No errors or crash loops.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the change is applied THEN ArgoCD application admins-mctl-agents-worker reports Synced and Healthy.
