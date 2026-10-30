# Requirements: incident-92761435

## Incident
- ID: argo-mctl-agents-shepherd-ca638b66-1792761435
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, mctl-telegram issue-716)
- Created: 2026-10-23T13:17:16.098719Z

### Summary
```
shepherd shepherd issue-716-refactor-db-replace-logtoolcall-s-positi Failed after 506.276141s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-ca638b66 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
fingerprint: workflow_failed:shepherd:mctl-telegram:issue-716-refactor-db-replace-logtoolcall-s-positi
workflow_name: mctl-agents-shepherd-e222a02a
occurrence_count: 2
```

### Log Snippet
```
[post-deploy-verify] Sleeping 300s for ArgoCD to reconcile post-merge…
[post-deploy-verify] Listing applications that became Degraded after 2026-10-23T13:38:47Z…
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-mctl-telegram  — waiting 120s to confirm (rolling-update grace)…
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-mctl-telegram
[service labs/mctl-telegram canary] probe failed step=get_unread_messages err=MCP tool returned isError=true
[service labs/mctl-telegram base-service] mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
[service labs/mctl-telegram base-service] db not reachable yet, retrying (connection refused to shared-pg-rw.platform-db) attempt=0
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN labs-mctl-telegram is Degraded for reasons unrelated to the shepherd run THEN the shepherd workflow is not marked Failed because of it.
