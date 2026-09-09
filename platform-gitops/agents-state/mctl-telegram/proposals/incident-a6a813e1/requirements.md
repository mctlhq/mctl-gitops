# Requirements: incident-a6a813e1

## Incident
- ID: a93817fc-3623-41fa-94cb-eff7a6a813e1
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-09T12:02:43.896015Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
tenant: labs
service: mctl-telegram
type: generic
severity: warning
source: alertmanager
occurrence_count: 1
```
Note: mctl_get_incident did not return a separate labels map for this incident;
the key: value pairs above are the incident's own top-level identifying fields,
included here for context.

### Log Snippet
Recent logs for labs/mctl-telegram (base-service container) show a periodic,
sustained failure pattern: a "bridge" component fails to authenticate with
"JWT expired" roughly once per minute, with no successful retry visible in the
sampled window. This matches a slow, steady burn of failed session-borrow
attempts rather than a single spike.
```
{"time":"2026-09-09T13:10:35.505720778Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:09:35.283661983Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:08:35.087095147Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:07:34.874238424Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:06:34.630614236Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:05:34.399162895Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:04:34.265783774Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:03:34.041837598Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
{"time":"2026-09-09T13:02:33.815049898Z","level":"INFO","msg":"bridge: authentication failed","err":"JWT expired"}
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
