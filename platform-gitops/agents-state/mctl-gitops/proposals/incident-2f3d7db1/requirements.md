# Requirements: incident-2f3d7db1

## Incident
- ID: a16114bc-94eb-4138-be0a-d7112f3d7db1
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilitySlowBurn (type=generic)
- Created: 2026-10-27T08:17:43Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
alertname: MctlTelegramToolAvailabilitySlowBurn
tenant: labs
severity: warning
```

### Log Snippet
```
09:02:33 WARN mcp tool call tool=search_messages user_id=154537 status=error peer=channel:<id> reason=telegram_error slo_status=caller_error err="MessagesSearch: rpcDoRequest: rpc error code 400: CHANNEL_INVALID"
09:02:33 WARN mcp mtproto error tool=search_messages mtproto_code=CHANNEL_INVALID http_code=400
(the pair above repeats 3 more times within the same second)
09:03:31 INFO mcp tool call tool=search_messages user_id=154537 status=ok
09:10:03 INFO canary run complete ok=true duration_seconds=1.25 version=0.94.0
(all canary probes mcp_init, list_dialogs, get_unread_messages ok at 09:00 and 09:10)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
