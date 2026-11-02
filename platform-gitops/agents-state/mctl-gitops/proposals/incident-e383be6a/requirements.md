# Requirements: incident-e383be6a

## Incident
- ID: 5393760d-8226-4a8d-b279-eddfe383be6a
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-02T21:59:20.36154Z

### Summary
```
ArgoCD application admins-mctl-agents-worker has been Degraded for 30m
```

## Evidence
### Labels
```
(none supplied on the incident record)
```

### Log Snippet
Service logs show the running worker pod (image 1.115.0) is healthy. The failure evidence is in namespace events:
```
Warning FailedCreate ReplicaSet admins-mctl-agents-worker-base-service-5ddd76fc84:
Error creating: pods "admins-mctl-agents-worker-base-service-5ddd76fc84-wm92t" is forbidden:
exceeded quota: admins-quota, requested: requests.memory=320Mi, used: requests.memory=1792Mi, limited: requests.memory=2Gi
(repeats at 22:12, 22:17, 22:29, 22:46, 23:02 UTC)
```
Service status: ArgoCD Synced, Degraded; configured imageTag 1.116.0 while the only running pod uses ghcr.io/mctlhq/mctl-agents:1.115.0.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the change is applied THEN a pod running image 1.116.0 is created and the old 1.115.0 pod is replaced.
