# Requirements: incident-90639911

## Incident
- ID: argo-mctl-agents-shepherd-92f3bc8a-1790639911
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-09-28T23:58:31.944232Z

### Summary
```
shepherd shepherd issue-705-media-responses-amplify-memory-10x-fetch Failed after 1597.182852s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-92f3bc8a | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
tenant: admins
service: mctl-agents
severity: warning
fingerprint: workflow_failed:shepherd:mctl-telegram:issue-705-media-responses-amplify-memory-10x-fetch
status (at pickup): analyzing (no skill match — analysis field was empty)
```

### Log Snippet
`post-deploy-verify` step log for this run (`mctl_get_workflow_logs`,
workflow `mctl-agents-shepherd-92f3bc8a`, step `post-deploy-verify`):
```
Sleeping 300s for ArgoCD to reconcile post-merge...
Listing applications that became Degraded after 2026-09-28T23:31:49Z...
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-mctl-telegram
Threshold (workflow.creationTimestamp): 2026-09-28T23:31:49Z
```
The `commit-and-push` step for this same run completed successfully (its own
`.status.yaml` transition merged); only `post-deploy-verify` failed.

Unlike incident `argo-mctl-agents-shepherd-744786f6-1790640590` (a different,
unrelated shepherd run also flagged by the same Degraded app), THIS run's own
fingerprint (`...:mctl-telegram:issue-705-media-responses-amplify-memory-10x-fetch`)
names `mctl-telegram` as its target — i.e. this proposal's own merge is a
plausible trigger for `labs-mctl-telegram` going Degraded shortly afterward,
not just an unlucky bystander.

## Acceptance Criteria
- WHEN `labs-mctl-telegram` returns to Healthy (tracked in sibling incident
  `18bc5134-18f5-4959-b594-6f2f2932eaa0`, proposal
  `mctl-gitops/proposals/incident-2932eaa0`) THEN a re-run of
  `post-deploy-verify` for this proposal's change would pass.
