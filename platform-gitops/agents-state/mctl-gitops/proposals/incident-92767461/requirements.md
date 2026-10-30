# Requirements: incident-92767461

## Incident
- ID: argo-mctl-agents-shepherd-a0e2e018-1792767461
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, workflow mctl-agents-shepherd-74439209)
- Created: 2026-10-23T14:57:42.123756Z

### Summary
```
shepherd shepherd issue-764-spike-runtime-746-slice-2-rust-bridge-cr Failed after 601.828907s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-a0e2e018 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd:mctl-agents:issue-764-spike-runtime-746-slice-2-rust-bridge-cr
```

### Log Snippet
```
[run-shepherd] info: pr=mctlhq/mctl-agents#768 head=3a4106ab merge_state=UNSTABLE checks_green=True codex_findings=11 -> wait
[run-shepherd] === Shepherd summary === ... : wait / nothing to hand off
[post-deploy-verify] Sleeping 300s for ArgoCD to reconcile post-merge...
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-mctl-telegram
[labs/mctl-telegram canary, 2026-10-23T16:10:16Z] probe failed step=list_dialogs err="MCP tool returned isError=true"
[labs/mctl-telegram base-service, 2026-10-23T16:10:16Z] mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
```

## Acceptance Criteria
- WHEN the change is applied THEN the shepherd post-deploy-verify step no longer fails a run for an app unrelated to the service whose PR it handled, and the alert stops firing for this tenant/service.
