# Requirements: incident-87468920

## Incident
- ID: argomctlagentsshepherd17874684001787468920
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-23T07:08:40.553284Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 512.673671s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1787468400 | post-deploy-verify flagged: unknown (verification did not complete)
```

## Evidence
### Labels
```
fingerprint: workflow_failed:shepherd::
occurrence_count: 1
severity: warning
source: argo-workflows
type: workflow_failed
```

### Log Snippet
```
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T08:00:00Z', 'workflow_run_id': '01a02da2-3511-781d-af3c-7cb30a5ec278', 'workflow_type': 'ReconcileWorkflow'})

WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T07:45:00Z', 'workflow_run_id': '01a02d94-7900-7eba-b643-13c075fd1aa5', 'workflow_type': 'ReconcileWorkflow'})

WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T07:30:00Z', 'workflow_run_id': '01a02d86-be39-73d5-9f93-aeb5fdf2f62a', 'workflow_type': 'ReconcileWorkflow'})
```

## Acceptance Criteria
- WHEN the mctl-agents pod volume mounts are configured correctly and /workdir/mctl-gitops/platform-gitops/agents-state is accessible THEN the shepherd workflow completes successfully and reconciliation workflows run without "state_dir not found" warnings.
