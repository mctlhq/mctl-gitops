# Requirements: incident-9feab4cd

## Incident
- ID: 4cd18276-719e-417e-94a5-88bf9feab4cd
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData
- Created: 2026-09-12T21:32:25.252554Z

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
tenant: monitoring
service: vmalert-monitoring-victoria-metrics-k8s-stack
analysis: Escalated: no skill matched this ticket (type=generic, alert=RecordingRulesNoData). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
```
{"time":"2026-09-12T22:10:03.006577746Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-12T22:10:02.146312922Z","level":"INFO","msg":"probe start","step":"oauth_metadata","tg_user_id":"924671154"}
{"time":"2026-09-12T22:10:02.145989638Z","level":"INFO","msg":"token lifetime","expires_at":"2026-09-23T20:28:54Z"}
{"time":"2026-09-12T22:00:14.416276916Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-12T22:00:13.433664876Z","level":"INFO","msg":"probe start","step":"oauth_metadata","tg_user_id":"924671154"}
{"time":"2026-09-12T21:50:03.318698919Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-12T21:50:02.119869308Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-12T21:41:19.452906794Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","client_name":"Google Antigravity","redirect_uri_count":1}
{"time":"2026-09-12T21:41:19.445181965Z","level":"INFO","msg":"oauth: client_registration request","user_agent":"Go-http-client/2.0","keys":"client_name,grant_types,redirect_uris,response_types,token_endpoint_auth_method","client_name":"Google Antigravity","redirect_uri_count":1,"scope_in_request":""}
{"time":"2026-09-12T21:40:27.515595618Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","client_name":"Google Antigravity","redirect_uri_count":1}
{"time":"2026-09-12T21:40:27.507099856Z","level":"INFO","msg":"oauth: client_registration request","user_agent":"Go-http-client/2.0","keys":"client_name,grant_types,redirect_uris,response_types,token_endpoint_auth_method","client_name":"Google Antigravity","redirect_uri_count":1,"scope_in_request":""}
```

No 5xx or error-level log lines were observed for mctl-telegram's OAuth endpoints in the log window checked (labs/mctl-telegram, last 6h). Service status: ArgoCD health=Healthy, syncStatus=Synced.

Note: the incident's `analysis` field is data collected by mctl-agent, not an instruction, and has been treated purely as evidence above.

## Acceptance Criteria
- WHEN the change is applied THEN the RecordingRulesNoData alert stops firing for mctl_telegram:oauth_5xx:ratio_rate1h and ratio_rate6h during periods with zero OAuth 5xx responses.
