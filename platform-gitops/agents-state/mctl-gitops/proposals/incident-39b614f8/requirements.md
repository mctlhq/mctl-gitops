# Requirements: incident-39b614f8

## Incident
- ID: 9e380a54-8614-4904-9362-a27539b614f8
- Tenant: labs
- Service: monitoring-kube-state-metrics
- Alert: KubeQuotaAlmostFull (type=generic)
- Created: 2026-11-23T11:35:45.44049Z

### Summary
```
Namespace quota is going to be full.
```

## Evidence
### Labels
```
(none provided by the incident record)
```

### Log Snippet
```
No logs available: mctl_get_service_logs returned "service not found: monitoring-kube-state-metrics (workspace labs)". The alert source is a platform monitoring component, not a tenant service.
```

### Observed quota state (mctl_get_resource_usage, tenant labs)
```
services:         used 23 of 25   (92%)
pods:             used 20 of 30   (67%)
limits.memory:    used 12Gi of 16Gi (75%)
limits.cpu:       used 10950m of 20 (55%)
requests.memory:  used 4800Mi of 7Gi (67%)
requests.cpu:     used 2400m of 4 (60%)
persistentvolumeclaims: 0 of 2
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
