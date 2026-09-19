# Requirements: incident-89840364

## Incident
- ID: argo-mctl-agents-shepherd-85d1c938-1789840364
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-19T17:52:44.330897Z

### Summary
```
shepherd shepherd issue-364-run-implementer-records-a-quota-exhauste Failed after 494.140079s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-85d1c938 | post-deploy-verify flagged: argocd/labs-agent-worker-preview
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd:mctl-agents:issue-364-run-implementer-records-a-quota-exhauste
occurrence_count: 1
analysis: (empty — no skill matched)
```

### Log Snippet
Workflow step `post-deploy-verify` (mctl-agents-shepherd-85d1c938):
```
Sleeping 300s for ArgoCD to reconcile post-merge…
Listing applications that became Degraded after 2026-09-19T17:44:25Z…
Newly Degraded apps detected: argocd/labs-agent-worker-preview — waiting 120s to confirm (rolling-update grace)…
Still Degraded after 120s grace: argocd/labs-agent-worker-preview
Threshold (workflow.creationTimestamp): 2026-09-19T17:44:25Z
```

Workflow step `run-shepherd` (mctl-agents-shepherd-85d1c938), for context — the shepherd's own work
that tick was evaluating an unrelated proposal's PR merge state and had nothing to do with the
flagged app:
```
python -m orchestrator.run_shepherd --service mctl-agents --slug issue-364-run-implementer-records-a-quota-exhauste
Found 1 proposal(s) to evaluate (budget cap $5.00):
  - mctl-agents/issue-364-run-implementer-records-a-quota-exhauste [implemented] attempts=5
info: pr=mctlhq/mctl-agents#409 head=143312e4 merge_state=BLOCKED checks_green=False codex_responded=True codex_findings=11 connector_findings=0 copilot_responded=False copilot_findings=0 -> wait
=== Shepherd summary ===
mctl-agents/issue-364-run-implementer-records-a-quota-exhauste: wait
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
