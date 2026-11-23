# Requirements: incident-cf6b7a8b

## Incident
- ID: 365aa395-c328-4f28-9ac8-d65ccf6b7a8b
- Tenant: admins
- Service: monitoring-kube-state-metrics
- Alert: KubeQuotaFullyUsed (type=generic)
- Created: 2026-11-17T19:40:45.259429Z

### Summary
```
Namespace quota is fully used.
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: admins
```

### Log Snippet
```
Service logs unavailable: service not found: monitoring-kube-state-metrics (workspace "admins").
Independent observation from mctl_get_resource_usage for tenant admins:
  services: used 10 / allocated 10
  pods: used 14 / allocated 16
  limits.memory: used 4032Mi / allocated 5Gi
  limits.cpu: used 3400m / allocated 10
  requests.cpu: used 785m / allocated 2
  requests.memory: used 2096Mi / allocated 3Gi
  persistentvolumeclaims: used 0 / allocated 2
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
