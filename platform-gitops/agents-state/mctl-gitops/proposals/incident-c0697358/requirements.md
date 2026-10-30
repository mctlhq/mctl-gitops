# Requirements: incident-c0697358

## Incident
- ID: c580263b-2046-4b83-b499-3e64c0697358
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramOAuthAvailabilityFastBurn (type=generic, source=alertmanager)
- Created: 2026-10-23T22:43:43.945264Z

### Summary
```
mctl-telegram: OAuth token endpoint fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
tenant: labs
severity: critical
status: escalated
```

mctl-agent analysis (escalated): no skill matched this ticket; no diagnostic rule exists for this alert.

### Log Snippet
```
23:11:32 base-service (new pod 7d569fc6b9-t6mvt) INFO listening addr=:8080
23:11:32 base-service INFO oauth issuer enabled issuer=https://tg.mctl.ai auto_approve_clients=true cimd_accept=true
23:11:31 base-service INFO db reachable attempts=1
23:11:29 base-service WARN db not reachable yet, retrying err="dial tcp 10.43.131.86:5432 (shared-pg-rw.platform-db.svc.cluster.local): connect: connection refused" attempt=0
23:11:23 base-service (old pod 7888cbbd5b-9kd5n) INFO shutdown signal received
23:11:13 preview base-service WARN db not reachable yet, retrying (same connection refused error), then db reachable at 23:11:15
23:10:03 canary INFO probe ok steps=oauth_metadata, mcp_init, list_dialogs, get_unread_messages; canary run complete ok=true version=0.92.2
23:10:03 base-service INFO mcp tool call tool=get_unread_messages status=ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
