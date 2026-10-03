# Requirements: incident-5ae3a90e

## Incident
- ID: f79e783d-3400-4fd1-9656-09125ae3a90e
- Tenant: labs
- Service: labs-mctl-telegram
- Alert: argocd_app_degraded / ArgoCDApplicationDegraded
- Created: 2026-09-22T00:23:19.950545Z

### Summary
```
ArgoCD application labs-mctl-telegram has been Degraded for 30m
```

## Evidence
### Labels
```
source: alertmanager
type: argocd_app_degraded
severity: warning
confidence: LOW
occurrence_count: 1
escalation_reason: no skill matched (type=argocd_app_degraded, alert=ArgoCDApplicationDegraded); evidence collected but no diagnostic rule exists for this signal
```

### Log Snippet
```
mctl_get_service_status(labs, mctl-telegram) at 2026-09-22T01:15Z:
  argocd.health = "Degraded", argocd.syncStatus = "Synced", argocd.updatedAt = "2026-09-22T01:10:00Z"
  service.imageTag = "0.67.0"

labs-mctl-telegram-local-mode-flip-1-g9q8x (one-shot Job, container "flip"), pod log timestamps:
  2026-09-21T23:51:20.440347438Z  "Flipping telegram id 8745115872 to Local Bridge mode..."   (attempt 0)
  2026-09-21T23:51:20.461562188Z  "Is the server running on that host and accepting TCP/IP connections?"
  2026-09-21T23:51:21.189463226Z  "Flipping telegram id 8745115872 to Local Bridge mode..."   (attempt 1)
  2026-09-21T23:51:21.199428011Z  "Is the server running on that host and accepting TCP/IP connections?"
  (both attempts above also logged: psql: error: connection to server at
  "shared-pg-rw.platform-db.svc.cluster.local" (10.43.131.86), port 5432
  failed: Connection refused)
  2026-09-21T23:51:37.17671812Z   "Flipping telegram id 8745115872 to Local Bridge mode..."   (attempt 2)
  2026-09-21T23:51:37.334155655Z  "Flipped row id(s): 43"
  2026-09-21T23:51:37.334217458Z  "UPDATE 1"
  (query output confirmed: id=43, mode=local, send_enabled=f, revoked_at=NULL,
  last_used_at=2026-09-01 23:45:41.666518+00)

Base-service and canary logs for the same window (00:40-01:15Z) show only
successful probe/tool-call activity ("probe ok", "canary run complete" ok=true,
"mcp tool call" status=ok) — no application-level errors.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
