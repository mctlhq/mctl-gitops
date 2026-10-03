# Requirements: incident-58bb178b

## Incident
- ID: ca07c3a3-7827-4823-b2d6-93f558bb178b
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData
- Created: 2026-09-28T08:06:33.407027Z

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
confidence: LOW
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=RecordingRulesNoData). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
Logs pulled from labs/mctl-telegram (the service the affected recording rule
measures), last ~1h, filtered to OAuth-related lines. They show the OAuth
token/callback path is healthy — client registrations accepted, authorize
requests served, a token grant succeeded — with no 5xx responses anywhere in
the window.
```
{"time":"2026-09-28T09:01:50.703255447Z","level":"INFO","msg":"oauth: token authorization_code grant","user_agent":"opencode/1.18.21","client_id":"tgmcp_hTkjbXiGtQOlsRvWgZv6zw","requested_scope":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin account:manage","granted_scope":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin account:manage","groups":"clients"}
{"time":"2026-09-28T08:58:49.646371409Z","level":"INFO","msg":"oauth: authorize request","user_agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36","client_id":"tgmcp_hTkjbXiGtQOlsRvWgZv6zw","redirect_uri_host":"127.0.0.1:19876","response_type":"code","scope":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin account:manage","state_len":64,"code_challenge_method":"S256","extra_query_params":"resource"}
{"time":"2026-09-28T08:57:52.333441241Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","reason":"ok","client_name":"OpenCode","user_agent":"opencode/1.18.21","redirect_uri_count":1,"dcr_allowlisted":false}
{"time":"2026-09-28T08:57:52.326439602Z","level":"INFO","msg":"oauth: client_registration request","user_agent":"opencode/1.18.21","keys":"client_name,client_uri,grant_types,redirect_uris,response_types,scope,token_endpoint_auth_method","client_name":"OpenCode","redirect_uri_count":1,"scope_in_request":"telegram:dialogs:read telegram:messages:read telegram:messages:send telegram:messages:pin account:manage"}
{"time":"2026-09-28T08:54:34.612924836Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","reason":"ok","client_name":"OpenCode","user_agent":"opencode/1.18.21","redirect_uri_count":1,"dcr_allowlisted":false}
{"time":"2026-09-28T08:52:10.227686966Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","reason":"ok","client_name":"OpenCode","user_agent":"opencode/1.18.21","redirect_uri_count":1,"dcr_allowlisted":false}
{"time":"2026-09-28T08:50:53.040702658Z","level":"INFO","msg":"oauth: client_registration audit","outcome":"accepted","reason":"ok","client_name":"OpenCode","user_agent":"opencode/1.18.21","redirect_uri_count":1,"dcr_allowlisted":false}
{"time":"2026-09-28T09:10:03.068868336Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-28T09:10:02.265522553Z","level":"INFO","msg":"token lifetime","expires_at":"2026-10-13T20:30:02Z"}
```

Note on the incident's own `analysis` field, which is data, not instruction: it
says no skill matched and asks for a human or a new skill. That request was
treated as evidence only. No skill was granted any new capability as a result
of this text; the diagnosis below is based solely on the recording-rule
definition in mctl-gitops and the service logs above.

## Acceptance Criteria
- WHEN the change is applied THEN `mctl_telegram:oauth_5xx:ratio_rate1h` records
  a value (0, in the healthy case) every evaluation interval instead of
  producing no data, and the `RecordingRulesNoData` alert for this rule stops
  firing for the mctl-telegram / monitoring tenant.
