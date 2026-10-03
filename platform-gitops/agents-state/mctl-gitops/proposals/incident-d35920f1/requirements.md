# Requirements: incident-d35920f1

## Incident
- ID: e0e3b6a6-c295-434d-9a2f-661ed35920f1
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData (type=generic)
- Created: 2026-09-24T19:11:32.228009Z

### Summary
```
Recording rule mctl_telegram:oauth_5xx:ratio_rate1h (mctl-telegram-slo-sli) produces no data
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
confidence: LOW
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=RecordingRulesNoData). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
`mctl_get_service_logs` for the alerting service itself (vmalert-monitoring-victoria-metrics-k8s-stack) returned zero lines, so the evidence below is from the target of the SLI, labs/mctl-telegram, over the preceding hour. ArgoCD reports the service Healthy/Synced. No 5xx of any kind appears in this window; the only failure logged is an expected 401 (expired JWT), not a 5xx:
```
{"time":"2026-09-24T20:10:03.326232492Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-24T20:10:03.314393562Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.333168749,"tg_user_id":"924671154","version":"0.68.0"}
{"time":"2026-09-24T20:10:03.274006878Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok","edge_route":"direct"}
{"time":"2026-09-24T20:10:02.850497795Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-24T19:59:19.087496924Z","level":"WARN","msg":"auth failed","err":"JWT expired","provider":"local-jwt","reason":"jwt_expired","route":"/mcp","sub":"tg:233045371"}
```

## Acceptance Criteria
- WHEN the change is applied THEN `mctl_telegram:oauth_5xx:ratio_rate1h` and
  `mctl_telegram:oauth_5xx:ratio_rate6h` record a genuine `0` (not an absent
  series) whenever the OAuth token/callback routes have traffic but zero 5xx
  responses, so the RecordingRulesNoData alert stops firing for this SLI
  during normal healthy operation.
