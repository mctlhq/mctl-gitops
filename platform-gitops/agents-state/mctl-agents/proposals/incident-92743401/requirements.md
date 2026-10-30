# Requirements: incident-92743401

## Incident
- ID: argo-mctl-agents-shepherd-316d1c4b-1792743401
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-10-23T08:16:41.253874Z

### Summary
```
shepherd shepherd issue-716-refactor-db-replace-logtoolcall-s-positi Failed after 502.935337s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-316d1c4b | post-deploy-verify flagged: argocd/labs-mctl-telegram 
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
workflow_name: mctl-agents-shepherd-ef1ecfff
fingerprint: workflow_failed:shepherd:mctl-telegram:issue-716-refactor-db-replace-logtoolcall-s-positi
occurrence_count: 2
```

### Log Snippet
```
[run-shepherd] pr=mctlhq/mctl-telegram#839 head=d4bff0d8 merge_state=BLOCKED checks_green=True codex_findings=0 ci_required_failed=0 -> wait
[run-shepherd] === Shepherd summary === mctl-telegram/issue-716-refactor-db-replace-logtoolcall-s-positi: wait ; nothing to hand off
[post-deploy-verify] Sleeping 300s for ArgoCD to reconcile post-merge...
[post-deploy-verify] Listing applications that became Degraded after 2026-10-23T08:38:15Z...
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-mctl-telegram
[post-deploy-verify] Threshold (workflow.creationTimestamp): 2026-10-23T08:38:15Z
```

## Acceptance Criteria
- WHEN the shepherd decides "wait" and merges nothing THEN post-deploy-verify does not fail the workflow.
- WHEN the shepherd does merge THEN post-deploy-verify only fails for the ArgoCD application(s) of the service that was merged, not for any app in the cluster.
