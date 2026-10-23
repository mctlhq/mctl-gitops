# Requirements: incident-bfe41a4c

## Incident
- ID: 826783a6-9c1c-489b-bfa0-b8d2bfe41a4c
- Tenant: monitoring
- Service: prometheus-pushgateway
- Alert: MctlTelegramCanaryFailing (type generic)
- Created: 2026-10-23T07:51:32.245139Z

### Summary
```
mctl-telegram canary probe has been failing for ~25 minutes
```

## Evidence
### Labels
```
source: alertmanager
severity: critical
status: escalated
analysis: no skill matched this ticket (type=generic)
```

### Log Snippet
```
2026-10-23T09:10:16Z canary INFO probe ok step=oauth_metadata
2026-10-23T09:10:16Z canary INFO probe ok step=mcp_init
2026-10-23T09:10:16Z canary ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
2026-10-23T09:10:16Z base-service WARN tool=list_dialogs user_id=245 status=error err="no active session"
2026-10-23T09:10:16Z canary ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true"
2026-10-23T09:10:16Z canary INFO canary run complete ok=false tg_user_id=924671154 version=0.88.3
2026-10-23T09:10:16Z canary INFO metrics pushed to pushgateway
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
