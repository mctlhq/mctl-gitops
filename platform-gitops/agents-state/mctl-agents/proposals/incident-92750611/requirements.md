# Requirements: incident-92750611

## Incident
- ID: argo-mctl-agents-shepherd-22a6fb37-1792750611
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, issue-716-refactor-db-replace-logtoolcall-s-positi)
- Created: 2026-10-23T10:16:51.496825Z

### Summary
```
shepherd shepherd issue-716-refactor-db-replace-logtoolcall-s-positi Failed after 502.369606s - workflow mctl-agents-shepherd-ad69e375 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
occurrence_count: 2
```

### Log Snippet
```
post-deploy-verify: Sleeping 300s for ArgoCD to reconcile post-merge
Listing applications that became Degraded after 2026-10-23T10:38:27Z
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-10-23T10:38:27Z
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
