# Requirements: incident-fa439507

## Incident
- ID: 93397112-4e5f-4156-b7e0-138dfa439507
- Tenant: labs
- Service: monitoring-kube-state-metrics
- Alert: KubeQuotaAlmostFull
- Created: 2026-09-20T11:36:44.55567Z

### Summary
```
Namespace quota is going to be full.
```

## Evidence
### Labels
```
(none returned by mctl_get_incident for this incident)
```

### Log Snippet
```
mctl_get_service_logs(team=labs, service=monitoring-kube-state-metrics, since=6h, lines=100) returned zero lines (count: 0, lines: null). This is a metrics-exporter target of the alert, not a service that emits its own application logs, so no log evidence is available. Diagnosis below is instead based on the labs tenant's live ResourceQuota usage (mctl_get_resource_usage) and its GitOps quota history.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
