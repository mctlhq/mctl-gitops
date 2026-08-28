# Requirements: incident-d51a3c44

## Incident
- ID: argo-mctl-agents-shepherd-1787907600-1787908081
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-28T09:08:01.731677Z
- Summary: shepherd shepherd (all open PRs) Failed after 460.870579s - post-deploy-verify flagged: unknown (verification did not complete)

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- occurrence_count: 3

### Log Snippet
```
ModuleNotFoundError: No module named 'temporalio'
  File "/app/orchestrator/temporal/worker.py", line 17, in <module>
    from temporalio.client import (
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/app/orchestrator/temporal/worker.py", line 17, in <module>
```

## Acceptance Criteria
- WHEN the temporalio Python package is added to mctl-agents Dockerfile THEN the shepherd workflow completes without ModuleNotFoundError.
- WHEN the mctl-agents pod restarts with the updated image THEN the Temporal worker process starts successfully.
