# Requirements: incident-89825049

## Incident
- ID: argo-mctl-agents-shepherd-78067ca0-1789825049
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-19T13:37:29.916624Z

### Summary
```
shepherd shepherd issue-305-add-repository-scoped-declarative-servic Failed after 482.895600s -- https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-78067ca0 | post-deploy-verify flagged: argocd/labs-agent-worker-preview
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
tenant: admins
service: mctl-agents
severity: warning
fingerprint: workflow_failed:shepherd:mctl-agents:issue-305-add-repository-scoped-declarative-servic
workflow: mctl-agents-shepherd-78067ca0
proposal_being_shepherded: issue-305-add-repository-scoped-declarative-servic
step_that_failed: post-deploy-verify (exit code 1)
step_commit-and-push_output: "No .status.yaml updates handed off -- nothing to commit."
```

### Log Snippet
Source: Argo Workflow step logs, post-deploy-verify step of mctl-agents-shepherd-78067ca0.
```
Sleeping 300s for ArgoCD to reconcile post-merge...
Listing applications that became Degraded after 2026-09-19T13:29:22Z...
Newly Degraded apps detected: argocd/labs-agent-worker-preview -- waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-agent-worker-preview
Threshold (workflow.creationTimestamp): 2026-09-19T13:29:22Z
```

Note: unlike the sibling incident-89825245, commit-and-push here reported nothing to commit
("No .status.yaml updates handed off"), meaning run-shepherd made no proposal-state
transition this tick (issue-305's proposal was likely already in a terminal/no-op state, or
this tick found nothing actionable for it). The workflow still failed solely on
post-deploy-verify.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
