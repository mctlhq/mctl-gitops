# Requirements: incident-72218f49

## Incident
- ID: e5800941-661e-44d3-be34-de2772218f49
- Tenant: argocd
- Service: argocd-self-managed
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-10-04T02:34:19.934736Z

### Summary
```
ArgoCD application argocd-self-managed OutOfSync for 1h
```

## Evidence
### Labels
```
(no labels returned by the incident record)
```

### Log Snippet
```
(no log lines returned by Loki for team argocd, service argocd-self-managed)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
