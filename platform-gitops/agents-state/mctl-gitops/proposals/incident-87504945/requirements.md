# Requirements: incident-87504945

## Incident
- ID: argomctlagentsshepherd17875044001787504945
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-23T17:09:05Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 539.790261s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1787504400 | post-deploy-verify flagged: unknown (verification did not complete)
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd::
```

### Log Snippet
```
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T18:00:00Z', 'workflow_run_id': '01a02fc7-8646-7716-b44b-6cd036cec486', 'workflow_type': 'ReconcileWorkflow'})
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T17:45:00Z', 'workflow_run_id': '01a02fb9-c9ef-7a3f-89c3-85c0ca627535', 'workflow_type': 'ReconcileWorkflow'})
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found ({'activity_id': '1', 'activity_type': 'discover_and_project', 'attempt': 1, 'namespace': 'mctl-agents', 'task_queue': 'mctl-dev-loop', 'workflow_id': 'reconcile-mctl-agents-2026-08-23T17:30:00Z', 'workflow_run_id': '01a02fac-0e3e-7995-97ef-797e9e9a5b76', 'workflow_type': 'ReconcileWorkflow'})
```

## Acceptance Criteria
- WHEN the state directory structure is created THEN mctl-agents reconciliation workflows no longer fail with state_dir not found errors.
