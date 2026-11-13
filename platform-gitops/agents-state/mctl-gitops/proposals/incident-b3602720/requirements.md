# Requirements: incident-b3602720

## Incident
- ID: ca2c0335-476c-4e3c-a81d-a733b3602720
- Tenant: monitoring
- Service: prometheus-pushgateway
- Alert: MctlTelegramCanaryFailing (type generic)
- Created: 2026-11-13T10:41:22.548319Z

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
analysis: no skill matched this ticket
```

### Log Snippet
```
canary: probe ok step=oauth_metadata, prm_root, prm_mcp, connect_page, authorize_redirect, callback_unknown_state, mcp_root, edge_connector_ua
canary: ERROR probe failed step=mcp_init err="initialize returned HTTP 401"
base-service: WARN auth failed err="worker token revoked" provider=local-jwt reason=token_revoked route=/mcp sub=tg:8745115872
canary: INFO token lifetime expires_at=2026-11-29T11:42:56Z
canary: INFO metrics pushed to pushgateway
Real user traffic (mcp tool call get_messages) status=ok throughout.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
