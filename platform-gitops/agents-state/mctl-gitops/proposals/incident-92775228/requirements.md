# Requirements: incident-92775228

## Incident
- ID: argo-mctl-agents-shepherd-05d7208e-1792775228
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, issue-707-spike-devloop-evaluate-pyrefly-as-a-fast)
- Created: 2026-10-23T17:07:08.891778Z

### Summary
```
shepherd shepherd issue-707-spike-devloop-evaluate-pyrefly-as-a-fast Failed after 507.431085s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-05d7208e | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
workflow_name: mctl-agents-shepherd-05d7208e
fingerprint: workflow_failed:shepherd:mctl-agents:issue-707-spike-devloop-evaluate-pyrefly-as-a-fast
```

### Log Snippet
```
Workflow logs were not fetched for this proposal; the following is from labs/mctl-telegram service logs.
18:09:06 WARN db not reachable yet, retrying: connection refused (shared-pg-rw.platform-db.svc.cluster.local:5432)
18:09:08 INFO db reachable (attempts=1)
18:10:03 INFO canary run complete ok=true version=0.90.0
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
