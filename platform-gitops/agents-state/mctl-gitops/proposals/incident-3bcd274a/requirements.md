# Requirements: incident-3bcd274a

## Incident
- ID: 0e921531-a59d-4d2f-ae2f-7c2c3bcd274a
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-13T16:07:20.368203Z

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
```

### Log Snippet
```
Service status (mctl_get_service_status): ArgoCD health=Healthy, syncStatus=OutOfSync, project=apps, namespace=argocd, imageTag=1.117.0, componentType=base-service, no database.
Pod logs (admins/mctl-agents-worker, last hour) show normal operation: temporal activities, execution-request claim POLICY_DECISION ALLOW lines, GitHub API polling. No errors, crash loops or sync failures are visible in the service logs.
mctl-agent analysis: no skill matched this alert type; no diagnosis was made.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
