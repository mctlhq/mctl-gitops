# Requirements: incident-90640590

## Incident
- ID: argo-mctl-agents-shepherd-744786f6-1790640590
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-09-29T00:09:51.027861Z

### Summary
```
shepherd shepherd issue-528-feat-context-platform-472-slice-c-produc Failed after 977.672326s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-744786f6 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
occurrence_count: 1
fingerprint: workflow_failed:shepherd:mctl-agents:issue-528-feat-context-platform-472-slice-c-produc
analysis: (empty - no skill matched)
```

### Log Snippet
`post-deploy-verify` step of this shepherd run (mctl_get_workflow_logs,
workflow mctl-agents-shepherd-744786f6):
```
Sleeping 300s for ArgoCD to reconcile post-merge...
Listing applications that became Degraded after 2026-09-28T23:53:27Z...
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-09-28T23:53:27Z
```
This shepherd run merged an unrelated mctl-telegram feature PR
(issue-528-feat-context-platform-472-slice-c-produc) and then failed only
because its own post-deploy-verify step found labs-mctl-telegram already
Degraded and never recovering within its grace window - not because this
PR's change broke anything. `mctl_get_service_status` for labs/mctl-telegram
confirms the app is still Degraded (syncStatus Synced) as of this
investigation (2026-09-29T01:15Z), and labs-mctl-telegram's own service logs
across the same window show only healthy traffic (no errors, canary probes
ok every 10 minutes).

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
