# Requirements: incident-23f14d57

## Incident
- ID: f19979ae-4121-45e6-a6d2-646323f14d57
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-30T06:32:43.75389Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: labs
service: (empty in incident payload; inferred as mctl-telegram from summary text)
severity: warning
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
```
{"time":"2026-09-30T07:05:13.892566063Z","level":"WARN","msg":"db not reachable yet, retrying","err":"ping pgx: failed to connect to `user=labs-mctl-telegram database=labs-mctl-telegram`: dial tcp 10.43.131.86:5432: connect: connection refused","attempt":0,"wait":2000000000}
{"time":"2026-09-30T07:05:15.935624419Z","level":"INFO","msg":"db reachable","attempts":1}
{"time":"2026-09-30T07:05:16.222071482Z","level":"INFO","msg":"replica identity","replica_id":"labs-mctl-telegram-base-service-6fb6497f78-nbdp5"}
{"time":"2026-09-30T07:05:07.868021865Z","level":"INFO","msg":"shutdown signal received"} (pod labs-mctl-telegram-base-service-6dc4bdcbc7-wfqvl)
{"time":"2026-09-30T07:05:07.868250828Z","level":"INFO","msg":"bridge: daemon disconnected","user_id":6462,"login":"tg:8745115872"}
{"time":"2026-09-30T07:05:38.950590716Z","level":"INFO","msg":"bridge: daemon connected","user_id":6462,"login":"tg:8745115872","device_id":"dev_d506989160c0f9c5b1cce53d7f60f6d5"}
{"time":"2026-09-30T07:05:05.973352470Z","level":"WARN","msg":"db not reachable yet, retrying","err":"ping pgx: failed to connect to `user=labs-mctl-telegram-preview database=labs-mctl-telegram-preview`: dial tcp 10.43.131.86:5432: connect: connection refused","attempt":0,"wait":2000000000} (preview replica, pod c659b9b45-7g5v7)
{"time":"2026-09-30T07:04:50.167156566Z","level":"INFO","msg":"shutdown signal received"} (pod labs-mctl-telegram-preview-base-service-5dfc9b8dc6-t8rsh)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
