# Requirements: incident-87483374

## Incident
- ID: argo-mctl-agents-shepherd-1787482800-1787483374
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-08-23T11:09:34.610988Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 543.062724s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1787482800 | post-deploy-verify flagged: unknown (verification did not complete)
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
status: analyzing
occurrence_count: 1
```

### Log Snippet
```
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found
WARNING:temporalio.activity:state_dir /workdir/mctl-gitops/platform-gitops/agents-state not found
INFO:temporalio.activity:submitted mctl-agents-incidents -> mctl-agents-run-805b625d
INFO:httpx:HTTP Request: GET https://api.mctl.ai/api/v1/workflows/mctl-agents-run-805b625d "HTTP/1.1 200 OK"
```

## Acceptance Criteria
- WHEN the change is applied THEN mctl-agents shepherd workflow completes successfully without "state_dir not found" warnings.
