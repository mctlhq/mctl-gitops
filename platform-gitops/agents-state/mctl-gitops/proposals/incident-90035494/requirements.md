# Requirements: incident-90035494

## Incident
- ID: argo-mctl-agents-shepherd-1790033940-1790035494
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-09-22T00:04:54.869748Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 1450.711567s -- https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1790033940 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd::
analysis: (empty -- no skill matched, incident reached mctl-api directly and sat in analyzing past the age threshold)
```

### Log Snippet
```
Argo Workflow mctl-agents-shepherd-1790033940, step post-deploy-verify-1238006181:
  Sleeping 300s for ArgoCD to reconcile post-merge...
  Listing applications that became Degraded after 2026-09-21T23:40:39Z...
  Newly Degraded apps detected: argocd/labs-mctl-telegram -- waiting 120s to confirm (rolling-update grace)...
  Still Degraded after 120s grace: argocd/labs-mctl-telegram
  Threshold (workflow.creationTimestamp): 2026-09-21T23:40:39Z

Cross-reference (mctl incident f79e783d-3400-4fd1-9656-09125ae3a90e, proposal
mctl-gitops/proposals/incident-5ae3a90e): the labs-mctl-telegram ArgoCD
Application's health went Degraded within this same window. Its one-shot
migration Job (labs-mctl-telegram-local-mode-flip-1) recorded two failed pod
attempts at 2026-09-21T23:51:20Z and 23:51:21Z (psql Connection refused
against shared-pg-rw.platform-db.svc.cluster.local) before succeeding on a
third attempt at 23:51:37Z -- inside the 23:40:39Z-00:04Z verification
window this shepherd run's post-deploy-verify step was checking.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
