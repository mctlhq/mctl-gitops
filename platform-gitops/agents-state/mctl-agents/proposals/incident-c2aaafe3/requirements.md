# Requirements: incident-c2aaafe3

## Incident
- ID: argo-mctl-agents-incidents-1787904900-1787905066
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-28T08:17:46.532199Z
- Summary: mctl-agents-run incident-responder Failed after 162.395498s - orchestrator failed to initialize

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- occurrence_count: 6

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
- WHEN the temporalio Python package is added to mctl-agents Dockerfile THEN the incident-responder workflow completes without ModuleNotFoundError.
- WHEN the mctl-agents pod restarts with the updated image THEN the incident responder orchestrator starts successfully and processes incidents.
