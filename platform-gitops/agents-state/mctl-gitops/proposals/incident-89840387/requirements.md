# Requirements: incident-89840387

## Incident
- ID: argo-mctl-agents-shepherd-1ea2ae72-1789840387
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-19T17:53:07.584912Z

### Summary
```
shepherd shepherd issue-305-add-repository-scoped-declarative-servic Failed after 502.390437s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1ea2ae72 | post-deploy-verify flagged: argocd/labs-agent-worker-preview
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd:mctl-agents:issue-305-add-repository-scoped-declarative-servic
occurrence_count: 1
analysis: (empty — no skill matched)
```

### Log Snippet
Workflow step `post-deploy-verify` (mctl-agents-shepherd-1ea2ae72):
```
Sleeping 300s for ArgoCD to reconcile post-merge…
Listing applications that became Degraded after 2026-09-19T17:44:39Z…
Newly Degraded apps detected: argocd/labs-agent-worker-preview — waiting 120s to confirm (rolling-update grace)…
Still Degraded after 120s grace: argocd/labs-agent-worker-preview
Threshold (workflow.creationTimestamp): 2026-09-19T17:44:39Z
```

Workflow step `run-shepherd` (mctl-agents-shepherd-1ea2ae72), for context — the shepherd's own work that
tick completed normally and had nothing to do with the flagged app:
```
python -m orchestrator.run_shepherd --service mctl-agents --slug issue-305-add-repository-scoped-declarative-servic
shepherd: skipping mctl-academy (SHEPHERD_SKIP_SERVICES; owned by another PR lifecycle)
info: no implemented/review-fixing proposals with a PR found.
nothing to hand off
```

Service status for the flagged app (queried independently at diagnosis time, 2026-09-19T19:1x):
```
argocd health: Degraded, syncStatus: Synced, updatedAt: 2026-09-19T19:10:06Z
```
`labs/agent-worker-preview`'s own container logs from the same window show it completing
`agent-worker` job invocations normally (`outcome":"completed"`), which is inconsistent with the
app being genuinely broken and consistent with a flaky/unscoped health signal.

## Acceptance Criteria
- WHEN an unrelated ArgoCD preview Application flaps to Degraded THEN a shepherd tick for a
  different service is no longer failed by that flap, and this alert stops recurring for
  mctl-agents shepherd runs.
