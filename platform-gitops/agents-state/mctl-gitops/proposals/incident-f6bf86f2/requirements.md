# Requirements: incident-f6bf86f2

## Incident
- ID: 0fa87f08-1b2d-4e16-973f-359df6bf86f2
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData (type=generic)
- Created: 2026-10-04T20:03:24.250901Z

### Summary
```
Recording rule mctl_telegram:oauth_5xx:ratio_rate1h (mctl-telegram-slo-sli) produces no data
```

## Evidence
### Labels
```
(none provided by the incident record)
```

### Log Snippet
```
(service logs for monitoring/vmalert-monitoring-victoria-metrics-k8s-stack returned zero lines)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
