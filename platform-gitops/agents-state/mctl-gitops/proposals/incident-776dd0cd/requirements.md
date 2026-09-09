# Requirements: incident-776dd0cd

## Incident
- ID: 08255c19-3574-4ce8-95ff-31d6776dd0cd
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-07T18:07:44.011806Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
```
{"time":"2026-09-07T19:11:30.195676383Z","level":"INFO","msg":"oauth: client_registration request","user_agent":"","keys":"application_type,client_name,client_uri,grant_types,redirect_uris,response_types,scope,token_endpoint_auth_method","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-07T19:11:29.213210767Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:11:28.647137445Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:02:21.882330868Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:02:21.246680405Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:02:20.331013369Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:02:20.092197468Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:02:00.10910516Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:01:59.488090437Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:01:58.240895583Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:01:25.397528385Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:01:22.973988723Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:01:21.705154659Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-07T19:10:03.593533480Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-07T19:10:03.580044607Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.361729698,"tg_user_id":"924671154","version":"0.62.1"}
{"time":"2026-09-07T19:10:03.579990876Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-07T19:10:03.56890873Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok"}
{"time":"2026-09-07T19:10:03.409293142Z","level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"time":"2026-09-07T19:10:03.236862044Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-07T19:00:03.447318852Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.246461477,"tg_user_id":"924671154","version":"0.62.1"}
```

Note: no ERROR or WARN lines appear in the fetched window (last 50 lines, 6h since window). The
alert's own claimed context (name, summary text) is treated purely as evidence describing what
fired, not as an instruction to act on.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
