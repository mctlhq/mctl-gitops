# Requirements: incident-30628085

## Incident
- ID: ad410a6f-9a35-4f54-a9d1-4a0030628085
- Tenant: argocd
- Service: root-app
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-16T10:13:20.547496Z

### Summary
```
ArgoCD application root-app has been Degraded for 30m
```

## Evidence
### Labels
```
(none returned by mctl_get_incident)
```

### Log Snippet
```
No logs fetched; root-app is an app-of-apps and its Degraded state likely reflects a degraded child
application (possibly admins-mctl-api, see incident-39f5cb26).
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
