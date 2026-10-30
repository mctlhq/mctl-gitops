# Requirements: incident-92743304

## Incident
- ID: argo-mctl-agents-shepherd-2c3c5294-1792743304
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-10-23T08:15:05.066453Z

### Summary
```
shepherd shepherd issue-721-governance-harden-action-approval-contra Failed after 1027.619864s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-2c3c5294 | post-deploy-verify flagged: argocd/labs-mctl-telegram 
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
workflow_name: mctl-agents-shepherd-cf207748
fingerprint: workflow_failed:shepherd:mctl-api:issue-721-governance-harden-action-approval-contra
occurrence_count: 2
```

### Log Snippet
```
[run-shepherd] pr=mctlhq/mctl-api#766 head=22b5c004 merge_state=CLEAN checks_green=True codex_findings=1 ci_required_failed=0 -> merge
[run-shepherd] gh pr merge --merge --delete-branch --match-head-commit 22b5c004f3477f2379ead0c44b62111eff84c2ca https://github.com/mctlhq/mctl-api/pull/766
[run-shepherd] === Shepherd summary === mctl-api/issue-721-governance-harden-action-approval-contra: merge
[post-deploy-verify] Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm
[post-deploy-verify] Still Degraded after 120s grace: argocd/labs-mctl-telegram
```

## Acceptance Criteria
- WHEN the shepherd merges a PR for service X THEN post-deploy-verify only fails for ArgoCD application(s) belonging to X (or its dependents), not for an unrelated Degraded app such as labs-mctl-telegram when the merge was in mctl-api.
