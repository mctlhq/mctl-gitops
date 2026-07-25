# Requirements: incident-d683e015

## Incident
- ID: argo-mctl-agents-incidents-1784954700-1784955115
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows; CronWorkflow `mctl-agents-incidents`
  submits a Workflow against ClusterWorkflowTemplate `mctl-agents-run` with
  mode=incident-responder)
- Created: 2026-07-25T04:51:55.701814Z
- Summary: mctl-agents-run incident-responder Failed after 327.744705s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784954700

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- status: analyzing
- tenant: admins
- service: mctl-agents
- fingerprint: workflow_failed:run:incident-responder:
- occurrence_count: 6
- last_seen_at: 2026-07-25T07:17:25.261746Z

### Log Snippet
```
mctl_get_service_logs(team=admins, service=mctl-agents, since=6h, lines=150)
  -> {"app":"mctl-agents","count":0,"lines":null,"team":"admins"}

mctl_get_workflow_status(workflow_name=mctl-agents-incidents-1784954700)
  -> error: "workflow record not found in audit log"

No Loki logs exist for mctl-agents: it runs as short-lived Argo Workflow
pods, not a persistent Deployment with an app log stream, so this
incident's own service-log lookup is structurally empty for every
occurrence of this fingerprint, not just this one.
```

## Acceptance Criteria
- WHEN the change is applied THEN mctl-agents-incidents cron ticks (mode=
  incident-responder) stop failing with error_max_budget_usd within the
  first ~5-6 minutes of a run.
- WHEN a self-referential incident about mctl-agents itself needs deeper
  exploration (workflow YAML, orchestrator source) because no Loki logs are
  available THEN the run has enough budget headroom to complete instead of
  being cut off mid-diagnosis.
