# Requirements: incident-db3e25e7

## Incident
- ID: 565ac919-c743-4ca7-94cc-7650db3e25e7
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-20T02:08:20.368351Z

### Summary
```
ArgoCD application admins-mctl-agents-worker OutOfSync for 1h
```

## Evidence
### Labels
```
tenant: admins
service: admins-mctl-agents-worker
type: argocd_app_degraded
severity: warning
source: alertmanager
```

### Log Snippet
```
ArgoCD status: health=Healthy syncStatus=OutOfSync revision="" project=apps destNamespace=admins imageTag=1.117.0
2026-11-20T03:08:47Z temporalio.worker._workflow._DeadlockError: [TMPRL1101] Potential deadlock detected: workflow didn't yield within 2 second(s).
2026-11-20T03:11:21Z POLICY_DECISION ... "decision": "ALLOW" ... "operation": "claim:execution-request" (repeats every 15s, normal polling)
2026-11-20T03:11:00Z INFO:httpx: GET https://api.mctl.ai/api/v1/agents/incident-responder/resolve?environment=production "HTTP/1.1 200 OK"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service (ArgoCD app admins-mctl-agents-worker reports Synced).
