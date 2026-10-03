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
service: (empty in incident record; inferred as mctl-telegram from alert name and summary)
alert: MctlTelegramSessionBorrowSlowBurn
severity: warning
confidence: LOW
occurrence_count: 1
analysis (from mctl-agent): Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
Fetched via mctl_get_service_logs(team=labs, service=mctl-telegram, since=6h),
sampled at 50 and 1000 lines, spanning roughly 2026-09-28T00:59Z through
07:15:22Z (the full 6h alert window plus margin). No line in either sample
contains "borrow" or "pool" (case-insensitive), and no line is at ERROR
level. Two WARN-level lines exist, both from an unrelated subsystem:
```
{"time":"2026-09-28T06:42:41.114847975Z","level":"WARN","msg":"auth failed","err":"JWT expired","provider":"local-jwt","reason":"jwt_expired","route":"/mcp","sub":"tg:6593770447","client_id":"tgmcp_nR1PkNVu76ytr8NLMHRbuQ"}
{"time":"2026-09-28T02:18:45.490579017Z","level":"WARN","msg":"auth failed","err":"JWT expired","provider":"local-jwt","reason":"jwt_expired","route":"/mcp","sub":"tg:6593770447","client_id":"tgmcp_nR1PkNVu76ytr8NLMHRbuQ"}
```
Both entries are the MCP HTTP layer's OAuth bearer-token check (provider
local-jwt, route /mcp) rejecting one client's (tg:6593770447) expired access
token — a distinct mechanism from the Telegram MTProto session pool this
alert measures (mctl_sessions_borrow_total{result}, per mctl-telegram's
internal/metrics/metrics.go), and only two occurrences over ~7h, hours apart,
do not on their own explain a 6x/6h burn. ArgoCD reports the deployment
Healthy/Synced, and the synthetic canary (every 10m, tg_user_id 924671154)
reports ok:true on every run visible in the window, including probes of
oauth_metadata, mcp_init, list_dialogs and get_unread_messages.

This is the same "silent" evidence pattern recorded on every prior
escalation of this exact alert pair: incidents
08255c19-3574-4ce8-95ff-31d6776dd0cd (2026-09-07),
a0693eab-1a7f-4fdd-a900-7578b5d6684e (2026-09-08),
277ec562-431c-4f02-b75a-5cba6670553a fast-burn (2026-09-22),
d685163c-9ba9-4453-b968-38090f966f1f (2026-09-24), and now this one plus its
fast-burn sibling fbca040c-3a52-4b74-b27c-fc6d74fc130c (2026-09-28, same
minute) — the SLO alert fires on
`mctl_sessions_borrow_total{result="error"}`, but the running image (0.69.0)
still emits no corresponding log line, so this responder has no way to
identify which sessions or requests are failing to borrow. At least two
earlier proposals for this same alert (incident-0f966f1f, incident-776dd0cd)
already requested exactly this logging fix; it does not appear to have
landed yet, since the alert keeps recurring with identical silent evidence.

## Acceptance Criteria
- WHEN a future `Pool.Borrow()` failure occurs (any
  `mctl_sessions_borrow_total{result="error"}` increment) THEN it produces a
  log line identifying the reason, so this alert is diagnosable from logs
  without needing raw metrics access.
- WHEN the change is applied THEN it does not alter `Pool.Borrow()` behavior,
  retry logic, or the SLO thresholds themselves — logging only.
