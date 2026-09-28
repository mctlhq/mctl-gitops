# Requirements: incident-4331f490

## Incident
- ID: 9204d14c-ac54-48e9-b0f6-e29e4331f490
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-28T06:03:43.747507Z

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
service: (empty in incident payload; alert is scoped to job=labs-mctl-telegram per the recording rule)
severity: warning
confidence: LOW
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
mctl_get_service_logs for team=labs, service=mctl-telegram was queried over
multiple windows (10m, 1h, 2h; a 24h query timed out at the Loki backend).
No log line in any sampled window contains "borrow", "session", "pool", or
level=ERROR. Only two WARN lines were found in the ~2h window preceding the
incident's report time, neither naming session borrow:
```
{"time":"2026-09-28T06:51:19.519227486Z","level":"WARN","msg":"db not reachable yet, retrying","err":"ping pgx: failed to connect to `user=labs-mctl-telegram-preview database=labs-mctl-telegram-pr[...]"}
{"time":"2026-09-28T06:42:41.114847975Z","level":"WARN","msg":"auth failed","err":"JWT expired","provider":"local-jwt","reason":"jwt_expired","edge_request_id":"a420c4fe59c13267-BEG"}
```
The first WARN is from the preview deployment's own DB connectivity retry
(labs-mctl-telegram-preview pod) and the second is an HTTP local-jwt auth
failure — neither is on the mctl_sessions_borrow_total series this alert's
SLI is built from (metric provenance: internal/metrics/metrics.go,
mctl-telegram-slo.yaml). All sampled MCP tool-call log lines in the same
window report status="ok". This alert's SLI is a Prometheus/VictoriaMetrics
ratio (mctl_sessions_borrow_total{result="error"} over
{result=~"ok|error"}), not something the application logs as text, which is
why no direct evidence appears in Loki even though the metric crossed
threshold.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
