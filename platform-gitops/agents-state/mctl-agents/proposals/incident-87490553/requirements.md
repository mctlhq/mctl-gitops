# Requirements: incident-87490553

## Incident
- ID: argo-mctl-agents-shepherd-1787490000-1787490553
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-23T13:09:13.815832Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 526.829277s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1787490000 | post-deploy-verify flagged: unknown (verification did not complete)
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
status: analyzing
fingerprint: workflow_failed:shepherd::
```

### Log Snippet
```
Sleeping 300s for ArgoCD to reconcile post-merge…
Listing applications that became Degraded after 2026-08-23T13:00:00Z…
Newly Degraded apps detected: argocd/labs-mctl-telegram — waiting 120s to confirm (rolling-update grace)…
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-08-23T13:00:00Z
```

The shepherd workflow successfully ran and merged changes, but post-deploy-verify step detected a Degraded ArgoCD application (labs-mctl-telegram) after the merge. The grace period of 120 seconds was insufficient for the application to recover from the deployment change.

## Acceptance Criteria
- WHEN the grace period in post-deploy-verify is increased OR retry logic is added THEN degraded apps that recover within the extended window will allow the shepherd workflow to complete successfully.
