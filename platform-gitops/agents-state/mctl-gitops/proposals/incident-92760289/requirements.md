# Requirements: incident-92760289

## Incident
- ID: argo-mctl-agents-shepherd-e81b12a9-1792760289
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, mctl-agents issue-758)
- Created: 2026-10-23T12:58:09.343276Z

### Summary
```
shepherd shepherd issue-758-fix-directives-reinvestigate-submits-inv Failed after 1254.032863s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-e81b12a9 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
fingerprint: workflow_failed:shepherd:mctl-agents:issue-758-fix-directives-reinvestigate-submits-inv
workflow_name: mctl-agents-shepherd-45b8edd1
occurrence_count: 3
```

### Log Snippet
```
[post-deploy-verify] Sleeping 300s for ArgoCD to reconcile post-merge…
[post-deploy-verify] Listing applications that became Degraded after 2026-10-23T13:37:16Z…
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-mctl-telegram  — waiting 120s to confirm (rolling-update grace)…
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-mctl-telegram
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the shepherd run touched only mctl-agents THEN a Degraded labs-mctl-telegram app is not attributed to it.
