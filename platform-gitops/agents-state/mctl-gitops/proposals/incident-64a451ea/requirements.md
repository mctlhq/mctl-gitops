# Requirements: incident-64a451ea

## Incident
- ID: 6526ab09-d2bb-4f8e-94e9-a25064a451ea
- Tenant: labs
- Service: mctl-telegram (preview track: labs-mctl-telegram-preview)
- Alert: MctlTelegramToolAvailabilitySlowBurn
- Created: 2026-09-14T20:08:43.734121Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: labs
service: (not set on the incident record; alert is scoped to job=labs/base-service, which spans both the stable and preview mctl-telegram tracks)
severity: warning
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramToolAvailabilitySlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
Logs pulled from `mctl_get_service_logs(team=labs, service=mctl-telegram, since=6h)`. The
stable track (pod labs-mctl-telegram-*, instance=labs-mctl-telegram) is healthy throughout:
every canary run and every `mcp tool call` log line shows `status:ok`. The preview track
(pod labs-mctl-telegram-preview-*, instance=labs-mctl-telegram-preview) shows a repeating
failure cycle, roughly once per minute, for the entire window:
```
{"time":"2026-09-14T21:03:07.781249361Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","client_name":"Google Antigravity","redirect_uri_count":1}
{"time":"2026-09-14T21:03:07.775561097Z","level":"INFO","msg":"oauth: client_registration request","user_agent":"Go-http-client/2.0","keys":"client_name,grant_types,redirect_uris,response_types,token_endpoint_auth_method","client_name":"Google Antigravity","redirect_uri_count":1,"scope_in_request":""}
{"time":"2026-09-14T21:03:07.574436873Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
{"time":"2026-09-14T21:03:07.52194032Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
{"time":"2026-09-14T21:00:55.669634928Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","client_name":"Google Antigravity","redirect_uri_count":1}
{"time":"2026-09-14T21:00:55.431329321Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
{"time":"2026-09-14T21:00:55.373275124Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
{"time":"2026-09-14T20:56:18.003654124Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
{"time":"2026-09-14T20:56:17.897647553Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
{"time":"2026-09-14T20:59:50.760815528Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
{"time":"2026-09-14T20:59:50.688615849Z","level":"WARN","msg":"auth failed","err":"invalid JWT signature"}
```
This same cycle (client re-registers as "Google Antigravity", then two auth attempts fail
signature verification, then it re-registers again roughly a minute later) repeats for the
full 6-hour window covered by the alert name ("slow burn ... 6h"), consistent with a client
that never obtains a usable token and keeps retrying.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
