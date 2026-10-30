# Requirements: incident-92756025

## Incident
- ID: argo-mctl-agents-shepherd-bde5752e-1792756025
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, fingerprint workflow_failed:shepherd:mctl-telegram:issue-716-refactor-db-replace-logtoolcall-s-positi)
- Created: 2026-10-23T11:47:05.218354Z

### Summary
```
shepherd shepherd issue-716-refactor-db-replace-logtoolcall-s-positi Failed after 502.791446s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-bde5752e | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
workflow_name: mctl-agents-shepherd-0f4f644c
occurrence_count: 3
```

### Log Snippet
```
[workflow mctl-agents-shepherd-0f4f644c / post-deploy-verify]
Sleeping 300s for ArgoCD to reconcile post-merge...
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-10-23T12:38:41Z

[workflow / run-shepherd]
pr=mctlhq/mctl-telegram#839 merge_state=BEHIND checks_green=True codex_findings=0 -> wait
nothing to hand off

[labs/mctl-telegram canary, 13:10 UTC]
level=ERROR msg="probe failed" step=list_dialogs err="MCP tool returned isError=true"
level=ERROR msg="probe failed" step=get_unread_messages err="MCP tool returned isError=true"
level=INFO msg="canary run complete" ok=false version=0.89.0

[labs/mctl-telegram base-service, 13:10 UTC]
level=WARN msg="mcp tool call" tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
level=WARN msg="mcp tool call" tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
