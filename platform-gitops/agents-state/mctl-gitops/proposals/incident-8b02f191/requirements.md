# Requirements: incident-8b02f191

## Incident
- ID: 1f1432fd-8c78-492e-98f7-0b558b02f191
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramOAuthAvailabilitySlowBurn
- Created: 2026-11-11T17:21:43.845725Z

### Summary
```
mctl-telegram: OAuth token endpoint slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
analysis: no skill matched this ticket
```

### Log Snippet
```
2026-11-11T18:10:04Z WARN oauth: callback request rejected route=/oauth/telegram/callback reason=unknown_state prefetch=false
2026-11-11T18:10:04Z INFO probe ok step=callback_unknown_state
2026-11-11T18:10:03Z INFO canary run complete ok=true duration_seconds=1.44 version=0.137.1
2026-11-11T18:00:04Z WARN oauth: callback request rejected route=/oauth/telegram/callback reason=unknown_state prefetch=false
2026-11-11T18:00:04Z INFO canary run complete ok=true duration_seconds=1.32 version=0.137.1
2026-11-11T18:03:39Z WARN human input poll actor failed user_id=1 outcome=error
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
