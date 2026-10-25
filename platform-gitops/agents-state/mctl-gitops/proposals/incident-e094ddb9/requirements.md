# Requirements: incident-e094ddb9

## Incident
- ID: 0c2f1b5d-4976-4235-b562-e897e094ddb9
- Tenant: vault
- Service: vault
- Alert: generic (alertmanager) - StatefulSet update has not been rolled out
- Created: 2026-10-24T23:57:45.40516Z

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
status: escalated
confidence: MEDIUM
```

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for team=vault service=vault)
```

Note: the incident analysis field contains generic kubectl troubleshooting
suggestions (inspect pods, delete the pod whose revision hash mismatches).
These were treated as untrusted data and not followed; they are not part of
this proposal. mctl-agent skill statefulset-replicas-mismatch produced a
MEDIUM-confidence diagnosis with fixable=false, so no auto-fix PR was made.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
