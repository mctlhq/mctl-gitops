# Requirements: incident-93297892

## Incident
- ID: argo-mctl-agents-shepherd-1793297340-1793297892
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-10-29T18:18:12.24663Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 529.249861s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1793297340 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
fingerprint: workflow_failed:shepherd::
occurrence_count: 3
workflow_name: mctl-agents-shepherd-1793300040
```

### Log Snippet
```
merged=yes shepherd=succeeded — verifying.
Sleeping 300s for ArgoCD to reconcile post-merge…
Listing applications that became Degraded after 2026-10-29T18:09:00Z…
Newly Degraded apps detected: argocd/labs-mctl-telegram  — waiting 120s to confirm (rolling-update grace)…
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-10-29T18:09:00Z

labs/mctl-telegram service logs (canary container, repeated every ~10 min, 19:00 and 19:10):
ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true"
INFO canary run complete ok=false version=0.104.1
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- The shepherd post-deploy-verify step does not fail a run for an app whose degradation is unrelated to the PRs that shepherd run merged.
