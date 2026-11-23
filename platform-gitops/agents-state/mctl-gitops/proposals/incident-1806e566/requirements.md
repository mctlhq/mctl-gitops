# Requirements: incident-1806e566

## Incident
- ID: 0c422484-51ce-444d-8c6f-82661806e566
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-19T11:08:20.442099Z

### Summary
```
ArgoCD application admins-mctl-agents-worker OutOfSync for 1h
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: admins
service: admins-mctl-agents-worker
analysis: Escalated, no skill matched (type=argocd_app_degraded, alert=ArgoCDApplicationOutOfSyncLong)
```

### Log Snippet
```
Service status (observed independently): ArgoCD health=Healthy, syncStatus=OutOfSync, revision="" (empty), imageTag=1.117.0
Pod admins-mctl-agents-worker-base-service-6c59864d64-w8zxb is running; logs show normal operation only:
POLICY_DECISION ... "decision": "ALLOW" ... "operation": "claim:execution-request" (repeating every ~15s)
INFO:httpx:HTTP Request: GET https://api.mctl.ai/api/v1/agents/incident-responder/resolve?environment=production "HTTP/1.1 200 OK"
INFO:httpx:HTTP Request: POST https://api.mctl.ai/api/v1/agents/executions "HTTP/1.1 201 Created"
gh api --paginate ... repos/mctlhq/<repo>/issues/comments (routine polling)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the change is applied THEN ArgoCD application admins-mctl-agents-worker reports syncStatus Synced.
