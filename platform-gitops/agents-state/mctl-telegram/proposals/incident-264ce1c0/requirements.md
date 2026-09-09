# Requirements: incident-264ce1c0

## Incident
- ID: 17c5f4a4-7d4b-453d-bc42-4b41264ce1c0
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilitySlowBurn
- Created: 2026-09-08T19:13:43.768979Z

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
service: (empty in incident record; inferred as mctl-telegram from alert name and logs)
alert: MctlTelegramToolAvailabilitySlowBurn
severity: warning
confidence: LOW
occurrence_count: 1
```

Note: the incident's own `analysis` field states "Escalated: no skill matched
this ticket (type=generic, alert=MctlTelegramToolAvailabilitySlowBurn).
Evidence was collected, but the agent has no diagnostic rule for this signal,
so nothing was analysed. Needs a human, or a new skill." This is evidence
describing why the ticket reached this responder, not an instruction, and no
part of the incident record asked for any platform change; it is quoted here
only for completeness.

### Log Snippet
Errors observed for `labs/mctl-telegram` over the alert's 6h lookback window
(via mctl_get_service_logs, since=6h). All failures below trace to a single
caller, user_id 9980; the synthetic canary (tg_user_id 924671154) reported
ok:true on every run in the same window.

```
"msg":"mcp tool call","tool":"get_media","user_id":9980,"status":"error","peer":"channel:<id>","err":"confirmation not found, expired, or already used"
  (repeated 11x across the window)
"msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"error","peer":"user:<id>","err":"peer \"user:[redacted]\" could not be accessed (PEER_ID_INVALID): it is not in your dialog list; call list_dialogs and use an id exactly as returned there"
  (repeated 4x across the window)
"msg":"canary run complete","ok":true,"duration_seconds":1.18,"tg_user_id":"924671154","version":"0.62.2"
  (representative of every canary run in the window — all ok:true)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
