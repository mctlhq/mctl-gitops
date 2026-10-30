# Requirements: incident-850ddad2

## Incident
- ID: 3f5fec5d-4a96-4acc-ba34-ae9b850ddad2
- Tenant: admins
- Service: monitoring-kube-state-metrics
- Alert: KubeJobFailed (type=generic)
- Created: 2026-10-19T04:39:45.389166Z

### Summary
```
Job failed to complete.
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
The incident carries no job name. kube-state-metrics itself logged nothing. The only failed Job
found in the admins namespace logs is the Umami retention Job (pod admins-umami-retention-29873063-g8lb4),
which is the subject of a sibling incident (bf3aa5e1-eb02-440a-889c-846542ea82c0):
```
BEGIN
DELETE 0
ERROR:  syntax error at or near "$"
LINE 1: DO $
           ^
```

## Acceptance Criteria
- WHEN the change is applied THEN the KubeJobFailed alert stops firing for this tenant/service.
