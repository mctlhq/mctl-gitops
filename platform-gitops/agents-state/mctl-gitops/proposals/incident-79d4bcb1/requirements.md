# Requirements: incident-79d4bcb1

## Incident
- ID: 87d729b8-10d6-4db4-8130-aba579d4bcb1
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData
- Created: 2026-09-14T09:21:04.183282Z

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
`mctl_get_service_logs` for tenant=monitoring, service=vmalert-monitoring-victoria-metrics-k8s-stack
(24h window) returned 0 lines — vmalert does not log per-rule evaluation
results to stdout, so no direct evidence lives there. The recording rule
in question (`mctl_telegram:oauth_5xx:ratio_rate1h`, defined in
platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml)
belongs to mctl-telegram's SLO group, so its own logs (team=labs,
service=mctl-telegram, last ~40 min) were pulled instead as supporting
evidence for the diagnosis:
```
{"time":"2026-09-14T10:11:34.156068884Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":607286293083}
{"time":"2026-09-14T10:10:03.435570463Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.453663388,"tg_user_id":"924671154","version":"0.67.0"}
{"time":"2026-09-14T10:10:03.435514369Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-14T10:10:03.398352424Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok","edge_route":"direct"}
{"time":"2026-09-14T10:10:03.217310504Z","level":"INFO","msg":"probe start","step":"get_unread_messages","tg_user_id":"924671154"}
{"time":"2026-09-14T10:10:03.217278793Z","level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"time":"2026-09-14T10:10:03.179682512Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok","edge_route":"direct"}
{"time":"2026-09-14T10:10:02.976587257Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-14T10:10:01.982424865Z","level":"INFO","msg":"probe start","step":"oauth_metadata","tg_user_id":"924671154"}
{"time":"2026-09-14T10:10:01.982135984Z","level":"INFO","msg":"token lifetime","expires_at":"2026-10-13T20:30:02Z"}
{"time":"2026-09-14T10:01:27.202100814Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-14T10:01:26.910534923Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"user:<id>"}
{"time":"2026-09-14T10:01:07.788890794Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"username:len=13"}
{"time":"2026-09-14T10:00:03.422679888Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-14T10:00:03.407722908Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.438590233,"tg_user_id":"924671154","version":"0.67.0"}
{"time":"2026-09-14T10:00:02.991848888Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-14T09:50:03.517734595Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.399978616,"tg_user_id":"924671154","version":"0.67.0"}
{"time":"2026-09-14T09:43:47.183456745Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":614174884211}
{"time":"2026-09-14T09:40:03.157611982Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-14T09:33:33.427257148Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-14T09:30:03.204382945Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
```
None of the sampled lines across this window show an HTTP request to
`/oauth/token` or `/oauth/telegram/callback` — the two routes the SLI
recording rule filters on. The canary's `oauth_metadata` / `token
lifetime` steps are MCP-layer checks against a long-lived cached token,
not HTTP calls to those two routes, so they do not feed
`mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}`.
Meanwhile `mctl-telegram` itself is Healthy/Synced in ArgoCD and serving
constant traffic on other tools, so the service is not down.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
