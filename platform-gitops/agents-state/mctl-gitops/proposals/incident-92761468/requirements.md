# Requirements: incident-92761468

## Incident
- ID: argo-mctl-agents-shepherd-1792760940-1792761468
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, all open PRs)
- Created: 2026-10-23T13:17:48.880371Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 523.288685s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1792760940 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
fingerprint: workflow_failed:shepherd::
workflow_name: mctl-agents-shepherd-1792763640
occurrence_count: 4
```

### Log Snippet
```
[post-deploy-verify] Sleeping 300s for ArgoCD to reconcile post-merge…
[post-deploy-verify] Listing applications that became Degraded after 2026-10-23T13:54:00Z…
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-mctl-telegram  — waiting 120s to confirm (rolling-update grace)…
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-mctl-telegram
[run-shepherd] info: mctl-agents/issue-758-... is driven by a running DevLoopWorkflow — skipping (sweeper mode, #213)
[run-shepherd] info: mctl-telegram/issue-716-... is driven by a running DevLoopWorkflow — skipping (sweeper mode, #213)
[run-shepherd] info: no implemented/review-fixing proposals with a PR found.
[run-shepherd] nothing to hand off
[service labs/mctl-telegram canary] probe failed step=list_dialogs err=MCP tool returned isError=true
[service labs/mctl-telegram base-service] mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the shepherd merged nothing THEN post-deploy-verify does not fail the shepherd workflow.
