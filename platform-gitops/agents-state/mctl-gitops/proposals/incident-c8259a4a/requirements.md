# Requirements: incident-c8259a4a

## Incident
- ID: 95147091-3ada-43c8-bd57-7ab8c8259a4a
- Tenant: labs
- Service: labs-mctl-telegram
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-13T10:42:20.360326Z

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
analysis: no skill matched this ticket
```

### Log Snippet
```
canary: probe ok step=oauth_metadata, prm_root, prm_mcp, connect_page, authorize_redirect, callback_unknown_state, mcp_root, edge_connector_ua
canary: ERROR probe failed step=mcp_init err="initialize returned HTTP 401"
base-service: WARN auth failed err="worker token revoked" provider=local-jwt reason=token_revoked route=/mcp sub=tg:8745115872
canary: INFO login path run complete ok=true
Pod labs-mctl-telegram-base-service-677cdf5c4c-tkqr2: Running, ready, 0 restarts, image ghcr.io/mctlhq/mctl-telegram:0.137.1
Real user traffic (mcp tool call get_messages) status=ok throughout.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
