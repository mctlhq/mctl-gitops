# Requirements: incident-c9b1d97a

## Incident
- ID: 80c04205-d98d-4385-9904-560dc9b1d97a
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-17T07:08:20.40998Z

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
analysis: Escalated: no skill matched this ticket (alert=ArgoCDApplicationOutOfSyncLong); needs a human or a new skill.
```

### Log Snippet
```
Service status (ArgoCD): health=Healthy, syncStatus=OutOfSync, revision="" (empty), project=apps, destNamespace=admins, imageTag=1.117.0
Pod admins-mctl-agents-worker-base-service-6c59864d64-w8zxb logs (last hour): only routine POLICY_DECISION allow lines (claim:execution-request) and httpx GET 200 / one 404 on a proposed-content.md lookup. No errors, crashes or restarts related to sync.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
