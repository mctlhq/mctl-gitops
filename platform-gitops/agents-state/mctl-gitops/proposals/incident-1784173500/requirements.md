# Requirements: incident-1784173500

## Incident
- ID: argo-mctl-agents-incidents-1784173500-1784173629
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows) — mctl-agents-run incident-responder
- Created: 2026-07-16T03:47:09.47015Z
- Summary: mctl-agents-run incident-responder Failed after 116.991753s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784173500

This proposal also covers two sibling incidents with the identical failure
signature (same workflow, same ~11-14s crash window on both primary and
fallback OAuth tokens):
- argo-mctl-agents-incidents-1784171700-1784171832 (created 2026-07-16T03:17:12Z)
- argo-mctl-agents-incidents-1784169900-1784170035 (created 2026-07-16T02:47:16Z)

At least 13 more incidents of the same `workflow_failed` / incident-responder
signature exist in the queue going back to 2026-07-15T13:18Z, including four
prior proposals for this same recurring failure (incident-17840745 [merged,
raised SERVICE_AGENT_BUDGET_USD 2.0->5.0], and incident-17840763/781/799/817
[all four rejected — PRs closed without merging]). The budget increase did
not stop the recurrence, and the four rejected proposals only offered an
undifferentiated "budget vs MCP vs exception vs OOM" decision tree with no
confirmed root cause. This proposal narrows that down with new, directly
reproduced evidence (see design.md).

## Evidence

### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- status: analyzing
- tenant: admins
- service: mctl-agents

### Log Snippet
```
Loki: 0 log lines returned for admins/mctl-agents (6h window) — app emits
no structured logs to Loki for this workflow.

mctl_get_workflow_status("mctl-agents-incidents-1784173500"): "workflow
record not found in audit log" (cron-triggered workflows are not tracked
in mctl's own operation audit log, this is expected and unrelated).

Direct query against the in-cluster Argo Workflows Server API (this agent's
own pod has an argo-workflow-sa token, used read-only):

  GET http://<argo-workflows-server>:2746/api/v1/workflows/argo-workflows?listOptions.limit=3
  -> HTTP 500
  -> {"code":13,"message":"ERROR: relation \"argo_workflows\" does not exist (SQLSTATE 42P01)"}

  GET .../api/v1/workflows/argo-workflows/mctl-agents-incidents-1784173500
  -> HTTP 200 (single-object GET by name works — it does not hit the
     broken code path)
  -> status.nodes show:
       run           (oauth-key=claude-code-oauth-token,   is-fallback=false) Failed, exit code 1, ran 03:45:43-03:45:57 (14s)
       run-fallback  (oauth-key=claude-code-oauth-token-2,  is-fallback=true)  Failed, exit code 1, ran 03:46:07-03:46:18 (11s)
       assert-produced                                                        Failed, exit code 1 (expected: both primary+fallback inputs were "Failed")

Pod stdout/stderr for the "run"/"run-fallback" containers could not be
retrieved: kubelet logs are already garbage-collected (pod TTL passed),
the Argo Server artifact-download route returned {"code":12,"message":
"Not Implemented"}, and no S3/R2 artifact-repository credentials are
mounted in this agent's pod to fetch the archived main.log directly from
the argo-workflows-logs bucket.
```

## Acceptance Criteria
- WHEN the change is applied THEN `mctl-agents-run incident-responder` (and
  its sibling crons: shepherd, issue-poll, implement, reconcile) no longer
  fail due to the Argo Workflows Server returning HTTP 500 on live workflow
  list queries.
- WHEN the fix is applied THEN a manual `GET /api/v1/workflows/argo-workflows`
  against the Argo Workflows Server returns HTTP 200 instead of the
  `relation "argo_workflows" does not exist` error.
- WHEN the next scheduled incident-responder run (15,45 * * * * UTC) fires
  THEN it completes with either Succeeded or a Failed status that carries a
  *different*, non-generic error (proving the crash is no longer the same
  startup-time failure).
