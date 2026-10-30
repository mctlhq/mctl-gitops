# Requirements: incident-92766848

## Incident
- ID: argo-mctl-agents-shepherd-9271d56c-1792766848
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, workflow mctl-agents-shepherd-1487d121)
- Created: 2026-10-23T14:47:28.276367Z

### Summary
```
shepherd shepherd issue-716-refactor-db-replace-logtoolcall-s-positi Failed after 504.803852s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-9271d56c | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd:mctl-telegram:issue-716-refactor-db-replace-logtoolcall-s-positi
occurrence_count: 6
```

### Log Snippet
```
[run-shepherd] info: pr=mctlhq/mctl-telegram#839 head=d4bff0d8 merge_state=BEHIND checks_green=True codex_findings=0 -> wait
[run-shepherd] === Shepherd summary === ... : wait / nothing to hand off
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-mctl-telegram
[labs/mctl-telegram canary, 2026-10-23T16:10:03Z] canary run complete ok=false version=0.89.0
[labs/mctl-telegram base-service] tool=get_unread_messages user_id=245 reason=telegram_error err="no active session"
```

## Acceptance Criteria
- WHEN the change is applied THEN the shepherd post-deploy-verify step no longer fails a run that merged nothing, and the alert stops firing for this tenant/service.
