# Requirements: incident-68c12fc2

## Incident
- ID: c027f822-1496-4e3a-986c-99be68c12fc2
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramOAuthAvailabilityFastBurn
- Created: 2026-11-11T17:21:43.844338Z

### Summary
```
mctl-telegram: OAuth token endpoint fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: critical
analysis: no skill matched this ticket
```

### Log Snippet
```
2026-11-11T18:10:04Z WARN oauth: callback request rejected route=/oauth/telegram/callback reason=unknown_state prefetch=false
2026-11-11T18:10:04Z INFO probe ok step=callback_unknown_state
2026-11-11T18:10:03Z INFO canary run complete ok=true duration_seconds=1.44 version=0.137.1
2026-11-11T18:00:04Z WARN oauth: callback request rejected route=/oauth/telegram/callback reason=unknown_state prefetch=false
2026-11-11T18:00:04Z INFO canary run complete ok=true duration_seconds=1.32 version=0.137.1
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
