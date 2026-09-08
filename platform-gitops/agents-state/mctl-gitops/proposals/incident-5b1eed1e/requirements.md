# Requirements: incident-5b1eed1e

## Incident
- ID: e9ec9774-c5ef-4736-95ca-29d75b1eed1e
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData (type=generic)
- Created: 2026-09-08T18:15:17.536822Z

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
occurrence_count: 1
analysis (from mctl-agent): Escalated: no skill matched this ticket (type=generic, alert=RecordingRulesNoData). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
`mctl_get_service_logs` for tenant=monitoring, service=vmalert-monitoring-victoria-metrics-k8s-stack
returned zero lines (vmalert itself logs nothing evaluation-relevant via Loki).
The lines below are from the upstream service the SLI covers, tenant=labs,
service=mctl-telegram (last ~50 lines, 6h window), which is what the recording
rule's underlying counters (mctl_http_requests_total) are scraped from:
```
{"time":"2026-09-08T19:11:28.939763774Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-08T19:11:27.732678785Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:11:27.29013597Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:10:03.27997274Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-08T19:10:03.268646236Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.22763059,"tg_user_id":"924671154","version":"0.62.2"}
{"time":"2026-09-08T19:10:03.268615473Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-08T19:10:03.102187937Z","level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"time":"2026-09-08T19:10:02.90206785Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-08T19:10:02.041126113Z","level":"INFO","msg":"token lifetime","expires_at":"2026-09-23T20:28:54Z"}
{"time":"2026-09-08T19:07:39.966490705Z","level":"INFO","msg":"mcp tool call","tool":"send_message:sent","user_id":85352,"status":"ok"}
{"time":"2026-09-08T19:07:00.070252809Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":85352,"status":"ok"}
{"time":"2026-09-08T19:03:00.4385836Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:02:58.218014537Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:02:57.685953599Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:02:33.247463978Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:01:10.972583847Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:01:09.584799811Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T19:00:56.682180594Z","level":"INFO","msg":"mcp tool call","tool":"send_message:sent","user_id":85352,"status":"ok"}
{"time":"2026-09-08T19:00:03.977517533Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.713545809,"tg_user_id":"924671154","version":"0.62.2"}
```
Note: the canary and traffic above repeatedly exercise `oauth_metadata`,
`client_registration`, and the MCP tool routes, but no `/oauth/token` or
`/oauth/telegram/callback` request is visible logging a status code in this
window — consistent with the diagnosis below (the recording rule's numerator
selector has no matching series when the OAuth 5xx count is genuinely zero).

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
