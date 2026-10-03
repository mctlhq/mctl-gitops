# Requirements: incident-4ba4af46

## Incident
- ID: 1d227c4c-39e4-4e3e-8490-3e014ba4af46
- Tenant: monitoring
- Service: vmalert-monitoring-victoria-metrics-k8s-stack
- Alert: RecordingRulesNoData
- Created: 2026-09-29T18:31:34.168158Z

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
mctl-agent's own log tooling returned zero lines for the alerting service
itself (vmalert has no application logs to fetch). The relevant evidence
instead comes from the mctl-telegram service (labs/mctl-telegram), whose
traffic feeds the recording rule in question, and from the recording-rule
source file. Recent mctl-telegram activity, all healthy, none of it hitting
the /oauth/token or /oauth/telegram/callback routes the recording rule reads:
```
2026-09-29T19:10:38Z INFO mcp tool call tool=get_messages status=ok
2026-09-29T19:10:31Z INFO event outbox purged rows=8
2026-09-29T19:10:04Z INFO canary run complete ok=true version=0.71.0
2026-09-29T19:10:04Z INFO probe ok step=get_unread_messages
2026-09-29T19:10:03Z INFO probe ok step=list_dialogs
2026-09-29T19:10:03Z INFO mcp tool call tool=list_dialogs status=ok
2026-09-29T19:10:02Z INFO probe ok step=oauth_metadata
2026-09-29T19:10:02Z INFO token lifetime expires_at=2026-10-13T20:30:02Z
2026-09-29T19:08:03Z INFO mcp tool call tool=get_messages status=ok
2026-09-29T19:00:03Z INFO canary run complete ok=true version=0.71.0
```
The canary CronJob (labs-mctl-telegram-canary, */10) probes oauth_metadata,
mcp_init, list_dialogs and get_unread_messages only — it never calls
/oauth/token or /oauth/telegram/callback, so it generates no samples for the
metric this recording rule reads.

The recording rule source
(platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml)
defines mctl_telegram:oauth_5xx:ratio_rate1h as a bare
`errors / total` division over `mctl_http_requests_total`, with no
zero-fill guard on the numerator — see Design for why that is the root
cause.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
