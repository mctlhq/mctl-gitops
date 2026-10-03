# Requirements: incident-667dd951

## Incident
- ID: d25dd4fd-1f11-4dbd-8d69-59f8667dd951
- Tenant: labs
- Service: monitoring-kube-state-metrics
- Alert: KubeQuotaAlmostFull
- Created: 2026-09-18T20:18:44.553966Z

### Summary
```
Namespace quota is going to be full.
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: labs
service: monitoring-kube-state-metrics
severity: warning
status: escalated
analysis: Escalated: no skill matched this ticket (type=generic, alert=KubeQuotaAlmostFull). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
confidence: LOW
occurrence_count: 1
```

### Log Snippet
No log lines were available: `mctl_get_service_logs` for tenant `labs`, service
`monitoring-kube-state-metrics` returned zero entries (this is a metrics
exporter, not an application with request logs). Diagnosis below is based on
the tenant's live ResourceQuota usage instead, via `mctl_get_resource_usage`.

```
(no log lines returned)
```

### ResourceQuota snapshot (tenant: labs, via mctl_get_resource_usage)
```
limits.cpu:        11300m used / 12000m (12) allocated  =  94.2%
limits.memory:      8736Mi used / 10.5Gi (10752Mi) allocated = 81.2%
services:              17 used / 20 allocated            = 85.0%
requests.memory:    3792Mi used / 5Gi (5120Mi) allocated  = 74.1%
requests.cpu:        1935m used / 3000m allocated         = 64.5%
pods:                  16 used / 25 allocated             = 64.0%
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
