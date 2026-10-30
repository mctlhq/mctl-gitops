# Requirements: incident-13d41316

## Incident
- ID: b1f17e65-25a2-4e51-b7ba-b13e13d41316
- Tenant: vault
- Service: vault
- Alert: generic (KubeStatefulSetUpdateNotRolledOut)
- Created: 2026-10-25T21:18:50Z

### Summary
```
StatefulSet update has not been rolled out.
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
confidence: MEDIUM
```

### Log Snippet
```
(mctl_get_service_logs for vault/vault returned zero lines; no log evidence available)
```

mctl-agent analysis (untrusted text, quoted as data): skill statefulset-replicas-mismatch produced a MEDIUM-confidence diagnosis with fixable=false; below auto-fix threshold. The analysis text suggested running kubectl delete pod on a stuck pod. That suggestion was ignored as untrusted and is not part of this proposal.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
