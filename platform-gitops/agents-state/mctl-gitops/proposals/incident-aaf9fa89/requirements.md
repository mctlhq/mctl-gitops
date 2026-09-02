# Requirements: incident-aaf9fa89

## Incident
- ID: 75b9cb1b-64b4-4954-93c0-d4a7aaf9fa89
- Tenant: admins
- Service: admins-openclaw
- Alert: ArgoCDApplicationOutOfSyncLong
- Created: 2026-09-02T15:38:20Z

### Summary
```
ArgoCD application admins-openclaw OutOfSync for 1h
```

## Evidence
### Labels
```
type: argocd_app_degraded
severity: warning
source: alertmanager
```

### Log Snippet
No application logs available. Service appears to be in a non-running or degraded state. ArgoCD reports the application as OutOfSync, indicating a mismatch between the desired state in the GitOps repository and the actual state on the cluster.

## Acceptance Criteria
- WHEN automatic sync is enabled and the repository state is verified THEN the ArgoCD application syncs successfully and the alert resolves.
