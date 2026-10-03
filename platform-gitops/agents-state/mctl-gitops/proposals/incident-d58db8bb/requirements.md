# Requirements: incident-d58db8bb

## Incident
- ID: 1301d1cf-282e-4e87-9c91-8280d58db8bb
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData
- Created: 2026-09-11T10:32:21.393021Z

### Summary
```
Recording rule mctl_telegram:oauth_5xx:ratio_rate1h (mctl-telegram-slo-sli) produces no data
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: monitoring
service: vmalert-monitoring-victoria-metrics-k8s-stack
severity: warning
alertname: RecordingRulesNoData
occurrence_count: 1
recording (inferred from summary text): mctl_telegram:oauth_5xx:ratio_rate1h
rule_group (inferred from summary text): mctl-telegram-slo-sli
analysis: Escalated: no skill matched this ticket (type=generic, alert=RecordingRulesNoData). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
`mctl_get_service_logs` for team=monitoring, service=vmalert-monitoring-victoria-metrics-k8s-stack
returned zero lines for the last 6h. This is a vmalert rule-evaluation
component, not an application emitting request logs, so an empty result here
is expected and is evidence about the alert's nature (a metrics/rule-data
gap, not a crashing pod) rather than a log line to inspect.
```
(no log lines returned)
```

## Acceptance Criteria
- WHEN the change is applied THEN RecordingRulesNoData stops firing for the
  `mctl_telegram:oauth_5xx:ratio_rate1h` recording rule specifically, without
  suppressing RecordingRulesNoData for any other recording rule.
