# Requirements: incident-5ae3a90e

## Incident
- ID: f79e783d-3400-4fd1-9656-09125ae3a90e
- Tenant: labs
- Service: labs-mctl-telegram
- Alert: ArgoCDApplicationDegraded (type=argocd_app_degraded)
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
status: escalated
analysis: Escalated: no skill matched this ticket (type=argocd_app_degraded, alert=ArgoCDApplicationDegraded). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
confidence: LOW
occurrence_count: 1
argocd.health: Degraded
argocd.syncStatus: Synced
```

### Log Snippet
```
mctl_get_service_status(labs, mctl-telegram):
  argocd.health = Degraded, syncStatus = Synced, revision unset, updatedAt 2026-09-22T01:10:00Z

labs-mctl-telegram base-service and canary logs (2026-09-21T23:40Z - 2026-09-22T01:10Z):
  All base-service MCP tool calls (list_dialogs, get_unread_messages) succeeded.
  All canary CronJob runs ("canary run complete", ok=true) succeeded on schedule,
  before, during and after the failure window below.

Failing resource (distinct pod, not the main service):
  pod: labs-mctl-telegram-local-mode-flip-1-g9q8x
  2026-09-21T23:51:20.461462885Z  psql: error: connection to server at
    "shared-pg-rw.platform-db.svc.cluster.local" (10.43.131.86), port 5432
    failed: Connection refused
  2026-09-21T23:51:21.199380963Z  psql: error: connection to server at
    "shared-pg-rw.platform-db.svc.cluster.local" (10.43.131.86), port 5432
    failed: Connection refused

mctl-agents-shepherd-1790033940 post-deploy-verify step (independent corroboration,
same window):
  Sleeping 300s for ArgoCD to reconcile post-merge...
  Listing applications that became Degraded after 2026-09-21T23:40:39Z...
  Newly Degraded apps detected: argocd/labs-mctl-telegram -- waiting 120s
    to confirm (rolling-update grace)...
  Still Degraded after 120s grace: argocd/labs-mctl-telegram
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
