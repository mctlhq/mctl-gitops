# Requirements: incident-2430bb39

## Incident
- ID: 0cd105fc-13ff-4a4b-9ac1-8f5b2430bb39
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-23T12:37:43.793003Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
mctl_get_incident returned no separate `labels` object for this incident (alertmanager-sourced, generic type). The fields it did return are quoted verbatim below as the evidence this proposal is based on:
```
source: alertmanager
type: generic
tenant: labs
service: (empty in the incident record; the alert name identifies mctl-telegram)
severity: warning
status: escalated
confidence: LOW
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```
The alert itself (read from the deployed VMRule, platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml) fires on:
```
mctl_telegram:session_borrow_errors:ratio_rate6h > 0.060
```
i.e. the Pool.Borrow() error rate (result="error", excluding result=expired_idle|expired_absolute) over the trailing 6h exceeded 6.0% — 6x the 99% session-borrow-success SLO's error budget. severity=warning, "File a reliability ticket; no page" per the alert's own annotation.

### Log Snippet
Fetched via mctl_get_service_logs(team=labs, service=mctl-telegram) across two windows (last ~30m, and the full 6h alert window / 776 lines). No `result="error"` or similar borrow-failure log line was found anywhere in the 6h window — every sampled `mcp tool call` and canary `probe` entry has `status="ok"`. Representative lines (no run of 3+ backticks was present in the source, so none needed stripping):
```
{"time":"2026-09-23T12:41:52.545947078Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":617024972698}
{"time":"2026-09-23T12:44:18.044413233Z","level":"INFO","msg":"idle telegram client, closing","user_id":105074,"idle":651595337200}
{"time":"2026-09-23T13:11:26.713269815Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":621824747581}
{"time":"2026-09-23T13:10:03.414927273Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":105074,"status":"ok"}
{"time":"2026-09-23T13:10:03.636596256Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok"}
{"time":"2026-09-23T13:01:05.493748333Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-23T13:00:02.872969438Z","level":"INFO","msg":"probe start","step":"oauth_metadata","tg_user_id":"924671154"}
{"time":"2026-09-23T13:00:02.87254546Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-23T13:00:03.131789751Z","level":"INFO","msg":"probe start","step":"get_unread_messages","tg_user_id":"924671154"}
{"time":"2026-09-23T13:00:03.367565944Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.364646638,"tg_user_id":"924671154","version":"0.67.0"}
{"time":"2026-09-23T12:54:34.574819103Z","level":"INFO","msg":"oauth: client_registration request","user_agent":"Cursor/1.0.0","client_name":"Cursor","scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin account:manage"}
{"time":"2026-09-23T??:??:??Z","level":"WARN","msg":"db not reachable yet, retrying","err":"ping pgx: failed to connect to 'user=labs-mctl-telegram-preview database=labs-mctl-telegram-preview': ... dial tcp 10.43.131.86:5432: connect: connection refused","attempt":0,"wait":2000000000}
```
Note on the last line: it is a preview-namespace database-connect retry (`labs-mctl-telegram-preview`), not the production service this alert covers, and per the VMRule's own comment the SLO's VMServiceScrape selects only `app.kubernetes.io/instance=labs-mctl-telegram` (production) and never scrapes preview — so this line is included for transparency but is not evidence for the production session-borrow SLI. Original backticks around the connection string were single, not a run of 3+, and were left as-is; the surrounding double quotes were normalized to single quotes here only to keep this fence from breaking.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
