# Requirements: incident-339188ad

## Incident
- ID: 31a1ba5b-d152-49cb-a808-18ff339188ad
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-28T21:32:43.748063Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
alert: MctlTelegramSessionBorrowSlowBurn
tenant: labs
severity: warning
confidence: LOW
occurrence_count: 1
```

### Log Snippet
```
{"time":"2026-09-28T22:10:03.560049805Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.195712636,"tg_user_id":"924671154","version":"0.69.0"}
{"time":"2026-09-28T22:10:03.352145164Z","level":"INFO","msg":"probe start","step":"get_unread_messages","tg_user_id":"924671154"}
{"time":"2026-09-28T22:10:02.364956658Z","level":"INFO","msg":"probe start","step":"oauth_metadata","tg_user_id":"924671154"}
{"time":"2026-09-28T22:00:04.083677298Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.545338386,"tg_user_id":"924671154","version":"0.69.0"}
{"time":"2026-09-28T22:00:03.324835931Z","level":"INFO","msg":"idle telegram client, closing","user_id":245,"idle":600045245290}
{"time":"2026-09-28T22:00:02.538605376Z","level":"INFO","msg":"token lifetime","expires_at":"2026-10-13T20:30:02Z"}
{"time":"2026-09-28T21:59:14.291929511Z","level":"INFO","msg":"listening","addr":":8080"}
{"time":"2026-09-28T21:59:11.789010389Z","level":"WARN","msg":"db not reachable yet, retrying","err":"ping pgx: failed to connect to `user=labs-mctl-telegram-preview database=labs-mctl-telegram-preview`: 10.43.131.86:5432 (shared-pg-rw.platform-db.svc.cluster.local): dial error: dial tcp 10.43.131.86:5432: connect: connection refused","attempt":0,"wait":2000000000}
{"time":"2026-09-28T21:58:55.810538265Z","level":"INFO","msg":"shutdown signal received"}
{"time":"2026-09-28T21:50:03.426716303Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.274301822,"tg_user_id":"924671154","version":"0.69.0"}
{"time":"2026-09-28T21:50:03.250527424Z","level":"INFO","msg":"probe start","step":"get_unread_messages","tg_user_id":"924671154"}
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
