# Requirements: incident-90035494

## Incident
- ID: argo-mctl-agents-shepherd-1790033940-1790035494
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (type=workflow_failed)
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
status: analyzing
analysis: (empty -- no skill matched this ticket)
confidence: (empty)
fingerprint: workflow_failed:shepherd::
occurrence_count: 1
```

### Log Snippet
```
mctl-agents-shepherd-1790033940 workflow steps:
  run-shepherd: merged mctlhq/mctl-agents#442; left mctlhq/mctl-gitops#1286
    waiting (codex findings, not merge-clean); left mctlhq/mctl-telegram#652
    waiting (BEHIND, ci_required_failed=1, sent to address-review). No merge
    touched the labs-mctl-telegram deployment or its GitOps values in this run.

  post-deploy-verify step (main.log):
    Sleeping 300s for ArgoCD to reconcile post-merge...
    Listing applications that became Degraded after 2026-09-21T23:40:39Z...
    Newly Degraded apps detected: argocd/labs-mctl-telegram -- waiting 120s
      to confirm (rolling-update grace)...
    Still Degraded after 120s grace: argocd/labs-mctl-telegram
    Threshold (workflow.creationTimestamp): 2026-09-21T23:40:39Z

  This is the same ArgoCD Degraded condition reported independently by
  mctl incident f79e783d-3400-4fd1-9656-09125ae3a90e (alert
  ArgoCDApplicationDegraded, escalated), diagnosed in
  mctl-gitops/proposals/incident-5ae3a90e: a one-shot Job
  (labs-mctl-telegram-local-mode-flip-1, extraObjects in
  platform-gitops/services/labs/mctl-telegram/values.yaml) failed twice
  against shared-pg-rw at 2026-09-21T23:51:20Z ("Connection refused") and,
  lacking an ArgoCD hook annotation, pins the Application's health as
  Degraded even though the mctl-telegram service itself is healthy.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
