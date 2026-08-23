# Requirements: incident-6aae5df3

## Incident
- ID: 5f4cdb7524bd45e4ac95beec6aae5df3
- Tenant: monitoring
- Service: prometheus-pushgateway
- Alert: MctlTelegramCanaryFailing
- Created: 2026-08-23T02:11:22Z

### Summary
mctl-telegram canary probe has been failing for approximately 25 minutes

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
```

### Log Snippet
Canary probe runs in labs/mctl-telegram consistently report probe failures:

```
ERROR probe failed step=list_dialogs err='MCP tool returned isError=true' flood_wait=false
ERROR probe failed step=get_unread_messages err='MCP tool returned isError=true' flood_wait=false
WARN mcp tool call tool=list_dialogs user_id=1 status=error err='no active session'
WARN mcp tool call tool=get_unread_messages user_id=1 status=error err='no active session'
INFO canary run complete ok=false duration_seconds=0.9 version=0.50.1
INFO metrics pushed to pushgateway url='http://prometheus-pushgateway.monitoring.svc.cluster.local:9091'
```

Pattern observed: MCP tool calls fail with 'no active session' error. Canary probe is able to reach oauth_metadata and mcp_init steps successfully, indicating the service and MCP integration are reachable. But user session operations fail consistently.

## Acceptance Criteria
- WHEN the underlying session state loss in labs-mctl-telegram is resolved THEN the canary probe resumes passing THEN the alert ceases firing.
