# Requirements: incident-92747006

## Incident
- ID: argo-mctl-agents-shepherd-64009681-1792747006
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, workflow mctl-agents-shepherd-9fcc4892)
- Created: 2026-10-23T09:16:47Z

### Summary
```
shepherd shepherd issue-716-refactor-db-replace-logtoolcall-s-positi Failed after 502.165483s | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd:mctl-telegram:issue-716-refactor-db-replace-logtoolcall-s-positi
occurrence_count: 2
```

### Log Snippet
```
run-shepherd: pr=mctlhq/mctl-telegram#839 merge_state=BLOCKED checks_green=True -> wait
run-shepherd: nothing to hand off (no merge performed by this run)
post-deploy-verify: Still Degraded after 120s grace: argocd/labs-mctl-telegram
labs/mctl-telegram canary: probe failed step=list_dialogs / get_unread_messages, err="no active session" (user_id 245)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
