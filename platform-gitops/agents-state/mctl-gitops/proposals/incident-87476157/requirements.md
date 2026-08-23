# Requirements: incident-87476157

## Incident
- ID: argo-mctl-agents-shepherd-1787475600-1787476157
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-23T09:09:17.547175Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 541.657524s - post-deploy-verify flagged: unknown (verification did not complete)
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
status: analyzing
```

### Log Snippet
```
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T10:00:00Z', 'workflow_run_id': '01a02dd9-23a8-75fd-8f24-a84b78cb17b4', 'workflow_type': 'ReconcileWorkflow'})
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T09:45:00Z', 'workflow_run_id': '01a02de6-dec2-7636-b6fe-f1a8ce0bf60e', 'workflow_type': 'ReconcileWorkflow'})
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T09:30:00Z', 'workflow_run_id': '01a02df4-9a3e-7ca3-a62e-446197611cf1', 'workflow_type': 'ReconcileWorkflow'})
```

## Acceptance Criteria
- WHEN the Helm values for mctl-agents are corrected to properly mount the agents-state volume THEN the warning disappears from logs and shepherd workflows complete successfully.
