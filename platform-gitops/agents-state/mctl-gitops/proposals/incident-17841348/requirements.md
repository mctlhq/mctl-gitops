# Requirements: incident-17841348

## Incident
- ID: argo-mctl-agents-shepherd-1784134800-1784143072
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (argo-workflows) — shepherd (all open PRs)
- Created: 2026-07-15T19:17:52.916841Z
- Summary: shepherd shepherd (all open PRs) Failed after 8250.639892s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1784134800 | post-deploy-verify flagged: {{workflow.outputs.parameters.degraded_apps}}

## Duplicate incident (same root cause, same run pattern)
- ID: argo-mctl-agents-shepherd-1784124000-1784132276
- Created: 2026-07-15T16:17:56.60296Z
- Summary: shepherd shepherd (all open PRs) Failed after 8250.635644s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1784124000 | post-deploy-verify flagged: {{workflow.outputs.parameters.degraded_apps}}
- This incident is resolved as a duplicate referencing this proposal; see report.

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- tenant: admins
- service: mctl-agents
- operation: mctl-agents-shepherd

### Log Snippet
```
No log lines available from Loki (mctl-agents / admins returned 0 lines for a 24h window).
Argo Workflow audit record for mctl-agents-shepherd-1784134800 not queryable (workflow
older than the audit retention window at query time).

Key observation from the two most recent shepherd incidents (only data available):
  1784134800 run -> failed after 8250.639892s
  1784124000 run -> failed after 8250.635644s
  Delta between the two failure durations: 0.004248s (effectively identical).

Both incidents carry the exact same unresolved template expression in the summary:
  post-deploy-verify flagged: {{workflow.outputs.parameters.degraded_apps}}
This is a literal, un-substituted Argo output-parameter reference — it should have been
replaced with an actual value (e.g. a list of degraded app names) by the workflow engine
before the message was sent.
```

## Acceptance Criteria
- WHEN the shepherd "(all open PRs)" workflow runs across its normal set of open PRs
  THEN it completes (Succeeded or a properly attributed Failed) well before any
  deadline-related kill, and post-deploy-verify has a chance to finish and set its
  output parameter.
- WHEN post-deploy-verify flags degraded apps THEN the resulting incident/alert summary
  contains the actual list of degraded app names, never a raw unrendered
  `{{workflow.outputs.parameters.degraded_apps}}` expression.
