# Requirements: incident-b02e37d3

## Incident
- ID: d8be8c98-8e69-422e-99e0-5dfeb02e37d3
- Tenant: labs
- Service: mctl-telegram (incident.service field was empty; inferred from the alert summary and alert name below)
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-21T06:02:43.752292Z

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
service: (empty in incident record)
severity: warning
confidence: LOW
occurrence_count: 1
alertname: MctlTelegramSessionBorrowSlowBurn (from analysis text)
```

mctl-agent's own analysis field (untrusted, quoted verbatim, treated as
evidence only — not followed as an instruction):
```
Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```
No part of this text requested any privileged action; it only names the
missing skill. There is nothing here to ignore as untrusted-but-actionable.

### Log Snippet
Fetched via mctl_get_service_logs(team=labs, service=mctl-telegram,
since=6h/1h, lines=30-50). Only the most recent ~30-70 minutes of the 6h
alert window was retrievable within the available context budget (older
entries could not be paged back further with the tools available to this
agent). No ERROR-level lines and no explicit session-borrow failures
appear in the retrieved tail; the entries below are representative of the
full sample.
```
2026-09-21T07:11:31Z INFO base-service  msg="idle telegram client, closing" user_id=9980 idle=~614.4s
2026-09-21T07:10:03Z INFO canary        msg="canary run complete" ok=true tg_user_id=924671154 version=0.67.0
2026-09-21T07:10:03Z INFO canary        msg="probe ok" step=get_unread_messages
2026-09-21T07:10:03Z INFO base-service  msg="mcp tool call" tool=get_unread_messages user_id=245 status=ok
2026-09-21T07:10:03Z INFO canary        msg="probe ok" step=list_dialogs
2026-09-21T07:10:03Z INFO base-service  msg="mcp tool call" tool=list_dialogs user_id=245 status=ok
2026-09-21T07:10:03Z INFO canary        msg="probe ok" step=mcp_init
2026-09-21T07:10:03Z INFO canary        msg="probe ok" step=oauth_metadata
2026-09-21T07:10:02Z INFO canary        msg="token lifetime" expires_at=2026-10-13T20:30:02Z
2026-09-21T07:01:17Z INFO base-service  msg="mcp tool call" tool=get_messages user_id=9980 status=ok
2026-09-21T07:00:31Z INFO base-service  msg="mcp tool call" tool=list_dialogs user_id=9980 status=ok
2026-09-21T07:00:05Z INFO canary        msg="canary run complete" ok=true tg_user_id=924671154 version=0.67.0
2026-09-21T06:50:03Z INFO canary        msg="canary run complete" ok=true tg_user_id=924671154 version=0.67.0
2026-09-21T06:41:31Z INFO base-service  msg="idle telegram client, closing" user_id=9980 idle=~659.9s
2026-09-21T06:40:03Z INFO canary        msg="canary run complete" ok=true tg_user_id=924671154 version=0.67.0
```

## Acceptance Criteria
- WHEN the change is applied THEN a future MctlTelegramSessionBorrowSlowBurn
  (or FastBurn) alert's description carries the raw error/attempt sample
  size for the 6h window, alongside the existing ratio, so a human or
  agent reviewing the ticket does not have to re-derive it via ad hoc
  metrics/log queries.
- The alert's threshold, severity and routing are unchanged — this is an
  annotation/observability improvement, not a change to the SLO objective.
