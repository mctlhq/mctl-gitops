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
tenant: labs
service: (empty on the incident record itself; identified as mctl-telegram from
  the alert name MctlTelegramSessionBorrowSlowBurn and from analysis text)
alert: MctlTelegramSessionBorrowSlowBurn
severity: warning
source: alertmanager
type: generic
occurrence_count: 1
mctl-agent analysis: "Escalated: no skill matched this ticket (type=generic,
  alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the
  agent has no diagnostic rule for this signal, so nothing was analysed. Needs
  a human, or a new skill."
```

### Log Snippet
Sampled from `mctl_get_service_logs(team=labs, service=mctl-telegram, since=6h)`,
which covers the same trailing window the alert's `ratio_rate6h` expression
evaluates. 768 lines were returned for the full 6h window; none contain the
literal strings "session", "borrow", or "error" (case-insensitive), and none
are at level WARN or ERROR — every line sampled is level=INFO. A representative
slice:
```
{"time":"2026-09-07T19:11:30.195676383Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-07T19:11:29.213210767Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-07T19:11:28.647137445Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin"}
{"time":"2026-09-07T19:10:03.59353348Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-07T19:10:03.580044607Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.361729698,"tg_user_id":"924671154","version":"0.62.1"}
{"time":"2026-09-07T19:10:03.579990876Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-07T19:10:03.56890873Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok"}
{"time":"2026-09-07T19:10:03.409357259Z","level":"INFO","msg":"probe start","step":"get_unread_messages","tg_user_id":"924671154"}
{"time":"2026-09-07T19:10:03.409293142Z","level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"time":"2026-09-07T19:10:03.396904874Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok"}
{"time":"2026-09-07T19:10:03.276299545Z","level":"INFO","msg":"probe start","step":"list_dialogs","tg_user_id":"924671154"}
{"time":"2026-09-07T19:10:03.276258814Z","level":"INFO","msg":"probe ok","step":"mcp_init"}
{"time":"2026-09-07T19:10:02.218893141Z","level":"INFO","msg":"probe start","step":"mcp_init","tg_user_id":"924671154"}
{"time":"2026-09-07T19:10:02.218611043Z","level":"INFO","msg":"token lifetime","expires_at":"2026-09-23T20:28:54Z"}
```
The every-10-minute canary (tg_user_id 924671154) reports `ok:true` on every
run visible in the window, and the every-minute-or-so OAuth
`client_registration` requests from client_name `cmg0c9xxt020wec596hjg563i`
all succeed at INFO level. Nothing in the available application logs indicates
which requests, if any, hit `Pool.Borrow()` and returned `result="error"` —
that signal exists only in the `mctl_sessions_borrow_total{result="error"}`
counter the alert reads, with no corresponding log line.

## Acceptance Criteria
- WHEN the change is applied THEN a future `Pool.Borrow()` failure (any
  `mctl_sessions_borrow_total{result="error"}` increment) produces a log line
  identifying the reason, so this alert is diagnosable from logs without
  needing raw metrics access.
- WHEN the change is applied THEN it does not alter `Pool.Borrow()` behavior,
  retry logic, or the SLO thresholds themselves — logging only.
