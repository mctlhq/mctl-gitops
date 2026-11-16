# Requirements: incident-3970f7ae

## Incident
- ID: 138d19c2-2a18-4141-87db-efde3970f7ae
- Tenant: labs-preview
- Service: monitoring-kube-state-metrics
- Alert: KubeQuotaFullyUsed (type=generic)
- Created: 2026-11-15T23:32:44.92803Z

### Summary
```
Namespace quota is fully used.
```

## Evidence
### Labels
```
(no labels returned by the incident record)
```

### Log Snippet
```
Logs unavailable: mctl_get_service_logs returned "tenant not found: labs-preview".
Independent observation (tenant "labs", resource usage, 2026-11-16T00:11Z):
  limits.cpu 10450m / 20, limits.memory 11904Mi / 16Gi, pods 19 / 30,
  requests.cpu 2300m / 4, requests.memory 4608Mi / 7Gi,
  persistentvolumeclaims 0 / 2, requests.storage 0 / 20Gi, services 21 / 25.
No resource in the "labs" namespace is at its hard limit.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
