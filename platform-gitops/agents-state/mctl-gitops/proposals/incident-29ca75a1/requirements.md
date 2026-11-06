# Requirements: incident-29ca75a1

## Incident
- ID: fb5f08ad-3fe4-4cd7-8df6-e19129ca75a1
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationDegraded (argocd_app_degraded)
- Created: 2026-11-03T21:25:20.542956Z

### Summary
```
ArgoCD application admins-mctl-agents-worker has been Degraded for 30m
```

## Evidence
### Labels
```
(none present on the incident record)
```

### Log Snippet
Service logs are healthy (the running 1.115.0 pod keeps polling). The evidence is in namespace events and pod/status state:
```
Warning FailedCreate ReplicaSet admins-mctl-agents-worker-base-service-76b99f9b47: Error creating: pods "admins-mctl-agents-worker-base-service-76b99f9b47-8nwzl" is forbidden: exceeded quota: admins-quota, requested: requests.memory=320Mi, used: requests.memory=1792Mi, limited: requests.memory=2Gi
(same event repeated at 21:18:34, 21:35:14, 21:51:54, 22:08:34)
Running pod: admins-mctl-agents-worker-base-service-75869bd9cc-wfzwk, image ghcr.io/mctlhq/mctl-agents:1.115.0, requests.memory 320Mi
Desired image tag in gitops / ArgoCD status: 1.117.0 (Synced, Health Degraded)
```

## Acceptance Criteria
- WHEN the change is applied THEN the admins-mctl-agents-worker rollout to 1.117.0 completes without exceeding admins-quota and the ArgoCD app returns to Healthy.
- WHEN the change is applied THEN the ArgoCDApplicationDegraded alert stops firing for admins/admins-mctl-agents-worker.
