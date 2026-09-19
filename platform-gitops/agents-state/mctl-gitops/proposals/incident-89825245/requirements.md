# Requirements: incident-89825245

## Incident
- ID: argo-mctl-agents-shepherd-ac5088f0-1789825245
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-19T13:40:45.686239Z

### Summary
```
shepherd shepherd issue-364-run-implementer-records-a-quota-exhauste Failed after 698.553617s -- https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-ac5088f0 | post-deploy-verify flagged: argocd/labs-agent-worker-preview
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
tenant: admins
service: mctl-agents
severity: warning
fingerprint: workflow_failed:shepherd:mctl-agents:issue-364-run-implementer-records-a-quota-exhauste
workflow: mctl-agents-shepherd-ac5088f0
proposal_being_shepherded: issue-364-run-implementer-records-a-quota-exhauste
step_that_failed: post-deploy-verify (exit code 1)
step_run-shepherd: Succeeded
step_commit-and-push: Succeeded
```

### Log Snippet
Source: Argo Workflow step logs, post-deploy-verify step of mctl-agents-shepherd-ac5088f0.
```
Sleeping 300s for ArgoCD to reconcile post-merge...
Listing applications that became Degraded after 2026-09-19T13:29:02Z...
Newly Degraded apps detected: argocd/labs-agent-worker-preview -- waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-agent-worker-preview
Threshold (workflow.creationTimestamp): 2026-09-19T13:29:02Z
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
