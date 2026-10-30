# Requirements: incident-92746868

## Incident
- ID: argo-mctl-agents-shepherd-6ef82acd-1792746868
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, workflow mctl-agents-shepherd-2bf661a8)
- Created: 2026-10-23T09:14:28Z

### Summary
```
shepherd shepherd issue-759-spike-runtime-746-slice-1-portable-runti Failed after 563.377125s | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd:mctl-agents:issue-759-spike-runtime-746-slice-1-portable-runti
occurrence_count: 3
```

### Log Snippet
```
run-shepherd: pr=mctlhq/mctl-agents#761 merge_state=UNSTABLE checks_green=True -> merge
run-shepherd: gh pr merge --merge --delete-branch --match-head-commit 48e98768 (mctl-agents#761)
post-deploy-verify: Still Degraded after 120s grace: argocd/labs-mctl-telegram
labs/mctl-telegram canary: probe failed step=list_dialogs / get_unread_messages, err="no active session" (user_id 245)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
