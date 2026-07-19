# Requirements: incident-argo-id-slug-collision

## Incident
- ID: argo-mctl-agents-incidents-1784483100-1784483248
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows) — mctl-agents-run incident-responder
- Created: 2026-07-19T17:47:28.597718Z
- Summary: mctl-agents-run incident-responder Failed after 143.215045s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784483100

### Duplicate incidents (same root cause, resolved together in this run)
- argo-mctl-agents-incidents-1784481300-1784481445 (created 2026-07-19T17:17:25.642517Z)
- argo-mctl-agents-incidents-1784479500-1784479654 (created 2026-07-19T16:47:34.366848Z)
- argo-mctl-agents-incidents-1784477700-1784477882 (created 2026-07-19T16:18:02.292349Z)
- argo-mctl-agents-incidents-1784475900-1784476054 (created 2026-07-19T15:47:34.200528Z)

Note: additional analyzing incidents of the same shape exist beyond this
run's 5-incident cap (e.g. argo-mctl-agents-incidents-1784474100-1784474233,
argo-mctl-agents-incidents-1784472300-1784472499,
argo-mctl-agents-run-f868212c-1784381073). Recommend a follow-up
incident-responder run once the fix below lands, to clear the remainder.

## Evidence

### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- status: analyzing (prior to this run)
- tenant: admins
- service: mctl-agents

### Log Snippet
```
mctl_get_service_logs(team=admins, service=mctl-agents, since=6h) -> 0 lines
  (Loki has no application logs here; the incident-responder runs as a
  short-lived Argo Workflow pod, not a scraped long-running service.)
mctl_get_workflow_status(workflow_name=mctl-agents-incidents-1784483100) ->
  "workflow record not found in audit log" (cron-submitted CronWorkflow runs
  are not tracked in the operator audit log used by that tool).
```

### Repository evidence (root cause, found directly in mctl-gitops)
```
$ find agents-state -iname "*incident-argo*"
platform-gitops/agents-state/mctl-gitops/proposals/incident-argo-mct/

$ cat platform-gitops/agents-state/mctl-gitops/proposals/incident-argo-mct/requirements.md
# Requirements: incident-argo-mct
## Incident
- ID: argo-mctl-agents-implement-1784072700-1784073633
...

$ cat platform-gitops/agents-state/mctl-gitops/proposals/incident-argo-mct/.status.yaml
status: in-progress
updated_at: '2026-07-17T07:15:12Z'
updated_by: mctl-agents[bot]
```
This directory was created on 2026-07-17 for an UNRELATED incident (an
`mctl-agents-implement` pipeline failure, not incident-responder), and is
still sitting at `status: in-progress`.

### mctl_list_recent_agent_runs evidence
```
{"operation":"mctl-agents-incidents","status":"failed","timestamp":"2026-07-19T18:15:01Z",
 "message":"child 'mctl-agents-incidents-1784484900-2612175429' failed",
 "workflowName":"mctl-agents-incidents-1784484900"}
```
In the same window (18:15-18:45 UTC), five consecutive `mctl-agents-implement`
cron ticks succeeded. Both pipelines share the same `mctl-gitops-main-writes`
mutex and the same primary/fallback OAuth token mechanism, so shared-
infrastructure contention (lock wait, token quota) cannot be the sole cause —
it would have to affect both pipelines, not just incident-responder.

## Acceptance Criteria
- WHEN the incident-responder's proposal-slug generation is fixed to be
  collision-resistant for argo-workflows-sourced incident IDs THEN the
  `mctl-agents-run incident-responder` CronWorkflow (schedule `15,45 * * * *`)
  completes with status Succeeded on its next scheduled tick.
- WHEN two different argo-workflows-sourced incidents are processed in
  separate runs THEN they write to two different proposal directories (no
  slug collision).
