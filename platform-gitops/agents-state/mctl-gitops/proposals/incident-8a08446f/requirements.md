# Requirements: incident-8a08446f

## Incident
- ID: af408887-3563-4b07-b901-9f9a5a08446f
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData
- Created: 2026-09-07T17:25:17.309215Z

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
```

### Log Snippet
mctl-telegram (team labs) logs over the incident window show the service healthy:
repeated successful oauth client_registration requests, successful mcp tool
calls, and passing canary probes (oauth_metadata, mcp_init, list_dialogs,
get_unread_messages) with zero 5xx or error-level lines observed.

```
{"time":"2026-09-07T18:11:29.681067688Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-07T18:11:27.670045843Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-07T18:10:03.573747041Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-07T18:10:03.562164027Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.328344943,"tg_user_id":"924671154","version":"0.62.1"}
{"time":"2026-09-07T18:10:03.562088859Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-07T18:10:03.539129859Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok"}
{"time":"2026-09-07T18:10:03.36948253Z","level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"time":"2026-09-07T18:10:03.35803779Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok"}
{"time":"2026-09-07T18:10:03.263836875Z","level":"INFO","msg":"probe ok","step":"mcp_init"}
{"time":"2026-09-07T18:10:03.19501372Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-07T18:10:02.249250818Z","level":"INFO","msg":"token lifetime","expires_at":"2026-09-23T20:28:54Z"}
{"time":"2026-09-07T18:02:17.231359149Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-07T18:00:05.058944776Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":641114749734}
{"time":"2026-09-07T18:00:03.887076568Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.5798587309999998,"tg_user_id":"924671154","version":"0.62.1"}
{"time":"2026-09-07T17:51:34.11443628Z","level":"INFO","msg":"mcp tool call","tool":"delete_messages","user_id":1,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-07T17:51:24.555862306Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-07T17:49:24.092682481Z","level":"INFO","msg":"mcp tool call","tool":"send_media:sent","user_id":9980,"status":"ok","peer":"username:len=17"}
```

No lines in this window reference `/oauth/token`, `/oauth/telegram/callback`, or any 5xx status code — consistent with the OAuth token endpoint being healthy, not failing.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
