# Requirements: incident-620ee5f4

## Incident
- ID: eb51f2c9-7344-4b38-bead-eb7c620ee5f4
- Tenant: labs
- Service: labs-mctl-telegram
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-10-23T07:52:21.992196Z

### Summary
```
ArgoCD application labs-mctl-telegram has been Degraded for 30m
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
analysis: no skill matched this ticket (type=argocd_app_degraded)
```

### Log Snippet
```
2026-10-23T09:10:16Z canary ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
2026-10-23T09:10:16Z base-service WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
2026-10-23T09:10:16Z canary ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true"
2026-10-23T09:10:16Z base-service WARN mcp tool call tool=get_unread_messages user_id=245 status=error err="no active session"
2026-10-23T09:10:16Z canary INFO canary run complete ok=false version=0.88.3
2026-10-23T09:11:08Z base-service WARN mtproto error tool=search_messages mtproto_code=CHANNEL_INVALID http_code=400 (user_id=183623, slo_status=caller_error)
2026-10-23T09:11:30Z base-service INFO mcp tool call tool=get_messages user_id=183623 status=ok
```
ArgoCD status at 09:11Z: health=Degraded, sync=Synced, imageTag=0.88.3.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
