# Requirements: incident-87925783

## Incident
- ID: argomctlagentsimplement19b9d481787925783
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-28T14:03:03Z

### Summary
```
implement issue-80-enforce-tenant-ownership-in-custom-domain workflow failed after 169.781304s. Root cause: critical infrastructure failure during task execution.
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
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found
ModuleNotFoundError: No module named 'temporalio'
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/app/orchestrator/temporal/worker.py", line 17, in <module>
    from temporalio.client import (
```

## Acceptance Criteria
- WHEN the mctl-agents service dependencies are fixed and working directories are mounted correctly THEN the temporal workflow orchestrator initializes successfully and agent tasks can execute.
