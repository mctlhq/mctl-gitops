# Requirements: incident-2e51a0a1

## Incident
- ID: b933db63-cb2c-4843-8867-d9962e51a0a1
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData (type=generic)
- Created: 2026-10-20T00:30:37.81077Z

### Summary
```
Recording rule mctl_telegram:oauth_5xx:ratio_rate1h (mctl-telegram-slo-sli) produces no data
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: monitoring
```

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for monitoring/vmalert-monitoring-victoria-metrics-k8s-stack)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
