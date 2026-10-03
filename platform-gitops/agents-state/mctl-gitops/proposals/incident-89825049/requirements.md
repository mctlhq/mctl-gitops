# Requirements: incident-89825049

## Incident
- ID: argo-mctl-agents-shepherd-78067ca0-1789825049
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd shepherd issue-305-add-repository-scoped-declarative-servic)
- Created: 2026-09-19T13:37:29.916624Z

### Summary
```
shepherd shepherd issue-305-add-repository-scoped-declarative-servic Failed after 482.895600s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-78067ca0 | post-deploy-verify flagged: argocd/labs-agent-worker-preview
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
```

### Log Snippet
```
post-deploy-verify step (mctl-agents-shepherd-78067ca0-post-deploy-verify-1765007591):
Sleeping 300s for ArgoCD to reconcile post-merge...
Listing applications that became Degraded after 2026-09-19T13:29:22Z...
Newly Degraded apps detected: argocd/labs-agent-worker-preview - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-agent-worker-preview
Threshold (workflow.creationTimestamp): 2026-09-19T13:29:22Z

mctl_get_service_status(team=labs, service=agent-worker-preview):
  argocd.health: Degraded, syncStatus: Synced (still Degraded when re-checked
  at diagnosis time, 2026-09-19T14:15:50Z)

mctl_get_resource_usage(team=labs), queried at diagnosis time:
  limits.cpu: used=11300m allocated=12000m (94% used, ~700m headroom)

This workflow's own post-deploy-verify step flagged labs-agent-worker-preview
as Degraded, but this shepherd run made no change to that service — its
change was for a different proposal (issue-305, mctl-agents). The Degraded
app is a pre-existing, unrelated condition being surfaced by an
environment-wide health check. See sibling incident
b1eb40f5-a589-4745-a720-5b64cc221e40 (the direct ArgoCD-degraded alert for
labs-agent-worker-preview) for the root-cause diagnosis, and sibling incident
argo-mctl-agents-shepherd-ac5088f0-1789825245 for a second, independent
shepherd run that observed the identical symptom minutes later.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
