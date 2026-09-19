# Requirements: incident-a2c2e080

## Incident
- ID: d404ecb3-48c4-4a53-9c0d-7ac2a2c2e080
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilityFastBurn
- Created: 2026-09-19T20:34:43.75191Z

### Summary
```
mctl-telegram: MCP tool availability fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
(none returned by mctl_get_incident for this incident — the incident record
carries no separate labels field; tenant/service/alert above were taken from
the top-level incident fields.)
```

### Log Snippet
Source: mctl_get_service_logs(team=labs, service=mctl-telegram, since=1h).
Timestamps are from the base-service container unless noted.
```
2026-09-19T20:30:03Z  canary run complete ok=true (probe cycle, all steps ok)
2026-09-19T20:31:51Z  mcp tool call tool=send_message:sent status=ok
2026-09-19T20:33:01.031147355Z  WARN mcp tool call tool=search_messages user_id=1 status=error
  peer=chat:<id> edge_route=portal
  err="MessagesSearch: rpcDoRequest: rpc error code 400: PEER_ID_INVALID"
2026-09-19T20:33:01.031765668Z  WARN mcp mtproto error tool=search_messages mtproto_code=PEER_ID_INVALID http_code=400
2026-09-19T20:33:01.070782131Z  WARN mcp tool call tool=get_messages user_id=1 status=error
  peer=chat:<id> edge_route=portal
  err="peer \"chat:-[redacted]\" could not be accessed (PEER_ID_INVALID): it is
  not in your dialog list; call list_dialogs and use an id exactly as returned
  there"
2026-09-19T20:33:10Z  mcp tool call tool=list_dialogs user_id=1 status=ok
2026-09-19T20:33:15Z  mcp tool call tool=search_messages user_id=1 status=ok
2026-09-19T20:33:18Z  mcp tool call tool=get_messages user_id=1 status=ok
2026-09-19T20:40:03Z through 2026-09-19T21:10:03Z  every /10-min canary probe
  cycle (mcp_init, oauth_metadata, list_dialogs, get_unread_messages) and every
  other portal/direct mcp tool call in the window returned status=ok.
```

## Acceptance Criteria
- WHEN the change is applied THEN future occurrences of this exact signature
  (MctlTelegramToolAvailabilityFastBurn caused by a small number of
  PEER_ID_INVALID tool-call errors in a low-traffic window) are triaged faster
  by whoever (human or agent) handles the next occurrence, without needing to
  re-derive this investigation from scratch.

## Confidence: LOW
No code or configuration defect was found in mctl-telegram. This proposal adds
documentation only; see design.md for why a threshold/behavior change was
deliberately not proposed.
