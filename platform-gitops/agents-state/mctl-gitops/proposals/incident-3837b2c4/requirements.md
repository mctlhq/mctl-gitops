# Requirements: incident-3837b2c4

## Incident
- ID: f93b948f-be28-4274-9b70-c58e3837b2c4
- Tenant: erpact
- Service: erpact-backup
- Alert: KubeContainerWaiting (type=generic)
- Created: 2026-10-04T04:46:45.353808Z

### Summary
```
Pod container waiting longer than 1 hour
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: erpact
service: erpact-backup
```

### Log Snippet
```
(no log lines returned by Loki for erpact/erpact-backup; the container never started)
```

### Other observations
- mctl-agent analysis: no skill matched KubeContainerWaiting; escalated.
- ArgoCD application erpact-erpact-backup was not found (service may not be deployed via the expected name).

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
