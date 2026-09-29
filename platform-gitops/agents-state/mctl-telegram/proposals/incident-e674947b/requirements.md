# Requirements: incident-e674947b

## Incident
- ID: cdb5cf09-b1c9-4708-91e6-117be674947b
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-29T14:02:43.922936Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: labs
service: (empty in incident payload; alert name identifies mctl-telegram)
severity: warning
occurrence_count: 1
```

### Log Snippet
Sampled from `mctl_get_service_logs(team=labs, service=mctl-telegram, since=6h)`.
No ERROR- or WARN-level lines, and no lines mentioning "borrow", "duplicate", or
"AUTH_KEY_DUPLICATED", were found in the ~1000 most recent log lines covering
this window — the alert is metric-driven (VMRule expression below) and leaves
no corresponding application-log trail at INFO level.
```
{"time":"2026-09-29T15:10:03.762338880Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"} (canary, stable)
{"time":"2026-09-29T15:10:03.752207390Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.452473192,"tg_user_id":"924671154","version":"0.71.0"} (canary, stable)
{"time":"2026-09-29T15:10:03.714178297Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok","edge_route":"direct"} (base-service, stable)
{"time":"2026-09-29T15:09:10.049287751Z","level":"INFO","msg":"event outbox purged","rows":4} (base-service, PREVIEW)
{"time":"2026-09-29T15:06:42.595150729Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok","peer":"user:<id>","edge_route":"direct"} (base-service, PREVIEW)
{"time":"2026-09-29T15:05:11.991261390Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok","peer":"user:<id>","edge_route":"direct"} (base-service, PREVIEW)
{"time":"2026-09-29T15:04:33.782351801Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok","peer":"user:<id>","edge_route":"direct"} (base-service, PREVIEW)
{"time":"2026-09-29T15:00:04.007448094Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.719528867,"tg_user_id":"924671154","version":"0.71.0"} (canary, stable)
{"time":"2026-09-29T14:40:24.435651602Z","level":"INFO","msg":"idle telegram client, closing","user_id":113709,"idle":637464619810} (base-service, stable)
```
Note: log lines above with `(stable)` came from pods
`labs-mctl-telegram-*` / `labs-mctl-telegram-canary-*`; lines marked
`(PREVIEW)` came from `labs-mctl-telegram-preview-base-service-*`, confirming
both deployments were handling live MTProto traffic concurrently in this
window.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this
  tenant/service, i.e. `mctl_telegram:session_borrow_errors:ratio_rate6h`
  (excluding `expired_idle`/`expired_absolute` results) stays at or below the
  6.0% slow-burn threshold defined in
  `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`.
