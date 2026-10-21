# Requirements: incident-b7550bef

## Incident
- ID: b2d3bef0-64d9-4066-9bdb-0fd1b7550bef
- Tenant: platform-db
- Service: shared-pg
- Alert: SharedPgBackupFailed (type=generic)
- Created: 2026-10-21T11:18:13.358389Z

### Summary
```
shared-pg last backup failed
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: platform-db
```

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for platform-db/shared-pg in the last hour)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the next scheduled backup runs THEN it completes successfully and the last-backup-failed metric clears.
