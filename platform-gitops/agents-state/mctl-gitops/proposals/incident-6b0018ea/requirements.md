# Requirements: incident-6b0018ea

## Incident
- ID: f0f433c3-841d-4d40-a955-ac5b6b0018ea
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramOAuthAvailabilitySlowBurn
- Created: 2026-10-24T02:14:43.853518Z

### Summary
```
mctl-telegram: OAuth token endpoint slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
tenant: labs
status: escalated
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramOAuthAvailabilitySlowBurn). No diagnostic rule for this signal.
```

### Log Snippet
```
{"level":"INFO","msg":"token lifetime","expires_at":"2026-11-22T20:50:03Z"}   (canary)
{"level":"INFO","msg":"probe ok","step":"oauth_metadata"}   (canary)
{"level":"INFO","msg":"probe ok","step":"mcp_init"}   (canary)
{"level":"INFO","msg":"probe ok","step":"list_dialogs"}   (canary)
{"level":"INFO","msg":"probe ok","step":"get_unread_messages"}   (canary)
{"level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.017,"version":"0.93.0"}   (canary, 03:10:03Z)
{"level":"INFO","msg":"mcp tool call","tool":"list_dialogs","status":"ok"}   (labs-mctl-telegram prod pod)
{"level":"WARN","msg":"agent saved command history poll failed","user_id":1,"err":"get Saved Messages history: rpcDoRequest: rpc error code 401: AUTH_KEY_UNREGISTERED"}   (repeated every 5s, pod labs-mctl-telegram-preview-base-service-6c8b7b6ff6-vgwp8)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
