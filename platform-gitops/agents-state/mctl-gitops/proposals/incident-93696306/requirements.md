# Requirements: incident-93696306

## Incident
- ID: argo-mctl-agents-shepherd-3ab5a694-1793696306
- Tenant: admins
- Service: mctl-agents (degraded app: admins-mctl-agents-worker)
- Alert: workflow_failed (shepherd post-deploy-verify)
- Created: 2026-11-03T08:58:26Z

### Summary
```
shepherd shepherd issue-1090-feat-agentapi-pool-credential-and-manage Failed after 537.471400s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-3ab5a694 | post-deploy-verify flagged: argocd/admins-mctl-agents-worker
```

## Evidence
### Labels
```
(none provided)
```

### Log Snippet
```
post-deploy-verify: merged=yes shepherd=succeeded - verifying.
post-deploy-verify: Newly Degraded apps detected: argocd/admins-mctl-agents-worker
post-deploy-verify: Still Degraded after 120s grace: argocd/admins-mctl-agents-worker
namespace events (admins, Warning, repeating every ~16 min since 09:21Z):
FailedCreate ReplicaSet admins-mctl-agents-worker-base-service-76b99f9b47: pods is forbidden: exceeded quota: admins-quota, requested: requests.memory=320Mi, used: requests.memory=1792Mi, limited: requests.memory=2Gi
service state: ArgoCD health=Degraded sync=Synced, configured imageTag=1.117.0, only running pod uses ghcr.io/mctlhq/mctl-agents:1.115.0 (requests.memory=320Mi)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service: admins-mctl-agents-worker becomes Healthy and its pod runs image 1.117.0.
