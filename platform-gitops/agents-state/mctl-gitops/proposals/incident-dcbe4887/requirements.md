# Requirements: incident-dcbe4887

## Incident
- ID: b1b9a7ca-31b3-480a-ac65-a60ddcbe4887
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-18T03:38:20.375934Z

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
analysis: no skill matched (type=argocd_app_degraded, alert=ArgoCDApplicationOutOfSyncLong)
```

### Log Snippet
```
Service status (observed independently): argocd health=Healthy, syncStatus=OutOfSync, revision="" (empty), updatedAt 2026-11-18T04:10:56Z, imageTag 1.117.0, project apps, dest namespace admins.
Pod logs (last 50 lines) show only normal worker activity: POLICY_DECISION ALLOW for claim:execution-request every 15s, gh api issue comment polling, httpx 200 OK for incident-responder resolve. No errors, no crash loops.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the change is applied THEN ArgoCD reports admins-mctl-agents-worker as Synced and Healthy.
