# Requirements: incident-55e10e76

## Incident
- ID: 0f0565e2d80b4e7992c8c16d55e10e76
- Tenant: admins
- Service: admins-openclaw
- Alert: ArgoCDApplicationOutOfSyncLong
- Created: 2026-08-28T23:11:19Z

### Summary
```
ArgoCD application admins-openclaw OutOfSync for 1h
```

## Evidence
### Labels
```
type: argocd_app_degraded
severity: warning
source: alertmanager
alert: ArgoCDApplicationOutOfSyncLong
```

### Log Snippet
No logs available from service. Service configuration not found in platform database. ArgoCD application lookup returned: Application not found: admins-admins-openclaw. Service appears to be incomplete or orphaned deployment.
```
```

## Acceptance Criteria
- WHEN the incomplete OpenClaw deployment is either completed or orphaned resources are cleaned up THEN the ArgoCDApplicationOutOfSyncLong alert stops firing for tenant admins.
