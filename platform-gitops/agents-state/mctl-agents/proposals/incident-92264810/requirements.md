# Requirements: incident-92264810

## Incident
- ID: argo-mctl-agents-shepherd-909bd184-1792264810
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-10-17T19:20:10.943608Z

### Summary
```
shepherd shepherd issue-413-detect-orphans-cannot-see-a-proposal-who Failed after 554.647321s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-909bd184 | post-deploy-verify flagged: argocd/labs-portfolio
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
workflow_name: mctl-agents-shepherd-909bd184
fingerprint: workflow_failed:shepherd:mctl-agents:issue-413-detect-orphans-cannot-see-a-proposal-who
```

### Log Snippet
```
[run-shepherd] info: pr=mctlhq/mctl-agents#672 ... -> address-review
[run-shepherd] ok   mctl-agents/issue-413-detect-orphans-cannot-see-a-proposal-who -> https://github.com/mctlhq/mctl-agents/pull/672
[run-shepherd] === Shepherd summary === ... address-review
[commit-and-push] To github.com:mctlhq/mctl-gitops.git  9b65c6e..eb567a2  HEAD -> main
[commit-and-push] Pushed status updates
[post-deploy-verify] Sleeping 300s for ArgoCD to reconcile post-merge...
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-portfolio - waiting 120s to confirm (rolling-update grace)...
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-portfolio
[post-deploy-verify] Threshold (workflow.creationTimestamp): 2026-10-17T19:10:50Z
```

## Acceptance Criteria
- WHEN the shepherd workflow completes its run-shepherd and commit-and-push steps successfully THEN a Degraded ArgoCD app unrelated to the proposal's service does not by itself mark the shepherd workflow as failed with an incident attributed to mctl-agents.
