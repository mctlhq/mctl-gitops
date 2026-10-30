# Requirements: incident-92747073

## Incident
- ID: argo-mctl-agents-shepherd-bef5deb9-1792747073
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, workflow mctl-agents-shepherd-be2c272f)
- Created: 2026-10-23T09:17:53Z

### Summary
```
shepherd shepherd issue-209-spike-security-continuous-finding-lifecy Failed after 527.831948s | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd:.github:issue-209-spike-security-continuous-finding-lifecy
occurrence_count: 4
```

### Log Snippet
```
run-shepherd: pr=mctlhq/.github#213 merge_state=CLEAN checks_green=True -> defer-merge (merge owned by human-codeowner)
run-shepherd: nothing to hand off
post-deploy-verify: Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm
post-deploy-verify: Still Degraded after 120s grace: argocd/labs-mctl-telegram
post-deploy-verify: Threshold (workflow.creationTimestamp): 2026-10-23T09:54:05Z
labs/mctl-telegram canary: probe failed step=list_dialogs / get_unread_messages, err="no active session" (user_id 245)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
