# Requirements: incident-39295844

## Incident
- ID: f6c9f4ac-f826-4b6a-a44f-10c739295844
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData (type=generic)
- Created: 2026-10-02T14:46:35.164509Z

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
(no log lines returned by mctl_get_service_logs for monitoring/vmalert-monitoring-victoria-metrics-k8s-stack in the last hour)
```

### mctl-agent analysis (quoted as data)
```
Escalated: no skill matched this ticket (type=generic, alert=RecordingRulesNoData). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
