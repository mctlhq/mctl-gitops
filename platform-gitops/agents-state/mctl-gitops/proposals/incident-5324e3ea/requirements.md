# Requirements: incident-5324e3ea

## Incident
- ID: 425c00a3-2e09-48ab-9fdd-d8935324e3ea
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData (type=generic)
- Created: 2026-10-05T18:18:24.418713Z

### Summary
```
Recording rule mctl_telegram:oauth_5xx:ratio_rate1h (mctl-telegram-slo-sli) produces no data
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
```

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for monitoring/vmalert-monitoring-victoria-metrics-k8s-stack)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
