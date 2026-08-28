# Requirements: incident-87878910

## Incident
- ID: argomctlagentsimplement5542c71a1787878910
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-28T01:01:50.959687Z

### Summary
```
implement implement mctl-portal Failed after 3357.812567s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-5542c71a
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:implement:mctl-portal:
```

### Log Snippet
```
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found
INFO:httpx:HTTP Request: GET https://api.mctl.ai/api/v1/workflows/mctl-agents-implement-ca0b6526 HTTP/1.1 200 OK
INFO:temporalio.activity:submitted mctl-agents-incidents -> mctl-agents-run-138a32ff
```

## Acceptance Criteria
- WHEN the mctl-agents pod/deployment has the agents-state directory properly mounted from mctl-gitops THEN reconciliation workflows complete successfully and implementer workflows complete without timeout failures.
