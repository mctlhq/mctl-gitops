# Requirements: incident-09094f4f

## Incident
- ID: 56c2fab8-7f39-4ac6-a47c-674e09094f4f
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilitySlowBurn (type=generic)
- Created: 2026-11-07T20:57:43.941616Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
confidence: LOW
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramToolAvailabilitySlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed.
```

### Log Snippet
```
2026-11-07T22:10:08Z canary: probe ok steps oauth_metadata, mcp_init, list_dialogs, get_unread_messages, prm_root, prm_mcp, connect_page, authorize_redirect, callback_unknown_state, mcp_root, edge_connector_ua
2026-11-07T22:10:08Z canary run complete ok=true duration_seconds=1.14 version=0.133.0
2026-11-07T22:10:08Z mcp tool call tool=list_dialogs status=ok
2026-11-07T22:10:08Z mcp tool call tool=get_unread_messages status=ok
2026-11-07T22:02:03Z mcp tool call tool=send_message:sent status=ok
2026-11-07T22:01:38Z mcp tool call tool=get_messages status=ok
2026-11-07T22:11:02Z WARN auth failed err="JWT expired" reason=jwt_expired route=/telegram/connect/broadcasts client_id=mctl_self_connect
2026-11-07T22:10:08Z WARN oauth: callback request rejected reason=unknown_state (deliberate canary probe, followed by probe ok callback_unknown_state)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
