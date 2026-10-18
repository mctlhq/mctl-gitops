# Requirements: incident-92337584

## Incident
- ID: argo-mctl-agents-shepherd-366d3148-1792337584
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-10-18T15:33:04.495676Z

### Summary
```
shepherd shepherd issue-199-retry-spike-execute-182-governance-audit Failed after 542.096935s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-366d3148 | post-deploy-verify flagged: argocd/root-app
```

## Evidence
### Labels
```
fingerprint: workflow_failed:shepherd:.github:issue-199-retry-spike-execute-182-governance-audit
workflow_name: mctl-agents-shepherd-366d3148
source: argo-workflows
severity: warning
```

### Log Snippet
```
Sleeping 300s for ArgoCD to reconcile post-merge…
Listing applications that became Degraded after 2026-10-18T15:23:55Z…
Newly Degraded apps detected: argocd/root-app  — waiting 120s to confirm (rolling-update grace)…
Still Degraded after 120s grace: argocd/root-app
Threshold (workflow.creationTimestamp): 2026-10-18T15:23:55Z
```

## Acceptance Criteria
- WHEN the change is applied THEN the shepherd workflow no longer fails on a post-deploy-verify result that is not attributable to a change it merged.
