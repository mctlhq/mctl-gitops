# Requirements: incident-87512208

## Incident
- ID: argomctlagentsshepherd17875116001787512208
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-23T19:10:09.101138Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 579.605619s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1787511600 | post-deploy-verify flagged: unknown (verification did not complete)
```

## Evidence

### Labels
```
type: workflow_failed
severity: warning
source: argo-workflows
```

### Log Snippet
```
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T20:00:00Z', ...})

WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T19:45:00Z', ...})

WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T19:30:00Z', ...})

INFO:temporalio.activity:submitted mctl-agents-incidents -> mctl-agents-run-98bd7cbc
INFO:httpx:HTTP Request: POST https://api.mctl.ai/api/v1/operations/mctl-agents-incidents/execute "HTTP/1.1 202 Accepted"
```

## Acceptance Criteria
- WHEN the state directory is created and mounted correctly in the mctl-agents service THEN the shepherd workflow completes without errors and the post-deploy-verify check passes.
