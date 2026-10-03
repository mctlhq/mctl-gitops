# Requirements: incident-421f37e6

## Incident
- ID: eb1bc493-0891-46ee-9634-cbaf421f37e6
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData (type=generic)
- Created: 2026-10-01T18:26:35.047159Z

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
(no log lines returned for monitoring/vmalert-monitoring-victoria-metrics-k8s-stack)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
