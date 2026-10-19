# Requirements: incident-42ea82c0

## Incident
- ID: bf3aa5e1-eb02-440a-889c-846542ea82c0
- Tenant: admins
- Service: monitoring-kube-state-metrics
- Alert: UmamiRetentionJobFailed (type=generic)
- Created: 2026-10-19T04:29:38.14326Z

### Summary
```
Umami retention Job admins/admins-umami-retention-29873063 failed — check its logs for the "past retention" check or a database error
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: admins
service: monitoring-kube-state-metrics
```

### Log Snippet
Logs from service admins/umami, container retention, pod admins-umami-retention-29873063-g8lb4:
```
BEGIN
DELETE 0
DELETE 0
DELETE 0
DELETE 0
DELETE 0
DELETE 0
DELETE 0
DELETE 0
ERROR:  syntax error at or near "$"
LINE 1: DO $
           ^
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the next admins-umami-retention Job runs THEN it completes without a SQL syntax error.
