# Requirements: incident-90639911

## Incident
- ID: argo-mctl-agents-shepherd-92f3bc8a-1790639911
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-09-28T23:58:31.944232Z

### Summary
```
shepherd shepherd issue-705-media-responses-amplify-memory-10x-fetch Failed after 1597.182852s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-92f3bc8a | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
occurrence_count: 1
fingerprint: workflow_failed:shepherd:mctl-telegram:issue-705-media-responses-amplify-memory-10x-fetch
analysis: (empty - no skill matched)
```

### Log Snippet
`post-deploy-verify` step of this shepherd run (mctl_get_workflow_logs,
workflow mctl-agents-shepherd-92f3bc8a):
```
Sleeping 300s for ArgoCD to reconcile post-merge...
Listing applications that became Degraded after 2026-09-28T23:31:49Z...
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-09-28T23:31:49Z
```
This is the earlier of two shepherd runs (this one at 23:31:49, the other -
incident-90640590 - at 23:53:27) that each independently found
labs-mctl-telegram already Degraded and never recovering within their grace
window, before either PR's own merge could plausibly be the cause.
`mctl_get_service_status` for labs/mctl-telegram confirms the app is still
Degraded (syncStatus Synced) as of this investigation (2026-09-29T01:15Z),
and labs-mctl-telegram's own service logs across the same window show only
healthy traffic (no errors, canary probes ok every 10 minutes).

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
