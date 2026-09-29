# Requirements: incident-90640590

## Incident
- ID: argo-mctl-agents-shepherd-744786f6-1790640590
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-09-29T00:09:51.027861Z

### Summary
```
shepherd shepherd issue-528-feat-context-platform-472-slice-c-produc Failed after 977.672326s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-744786f6 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
tenant: admins
service: mctl-agents
severity: warning
fingerprint: workflow_failed:shepherd:mctl-agents:issue-528-feat-context-platform-472-slice-c-produc
status (at pickup): analyzing (no skill match — analysis field was empty)
```

### Log Snippet
`post-deploy-verify` step log for this run (`mctl_get_workflow_logs`,
workflow `mctl-agents-shepherd-744786f6`, step `post-deploy-verify`):
```
Sleeping 300s for ArgoCD to reconcile post-merge...
Listing applications that became Degraded after 2026-09-28T23:53:27Z...
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-09-28T23:53:27Z
```
The `commit-and-push` step for this same run completed successfully (the
proposal's own change merged cleanly); only `post-deploy-verify` failed, and
only because of an application unrelated to this run's own target service.

## Acceptance Criteria
- WHEN the change is applied THEN operators reading a shepherd
  `workflow_failed` alert that names `post-deploy-verify flagged:
  argocd/<app>` can immediately tell whether it is a new problem or a known
  collateral effect of an already-tracked `argocd_app_degraded` incident.
