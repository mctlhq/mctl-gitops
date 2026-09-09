# Requirements: incident-264ce1c0

## Incident
- ID: 17c5f4a4-7d4b-453d-bc42-4b41264ce1c0
- Tenant: labs
- Service: mctl-telegram (inferred from alert name and log evidence; the incident record's `service` field was empty)
- Alert: MctlTelegramToolAvailabilitySlowBurn
- Created: 2026-09-08T19:13:43.768979Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
confidence: LOW
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramToolAvailabilitySlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
```
2026-09-08T20:11:52Z WARN auth failed err="invalid JWT signature" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:11:52Z WARN auth failed err="invalid JWT signature" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:11:52Z INFO oauth: client_registration audit outcome=accepted client_name="Google Antigravity" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:11:52Z INFO oauth: client_registration request client_name="Google Antigravity" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:11:48Z WARN auth failed err="invalid JWT signature" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:11:48Z WARN auth failed err="invalid JWT signature" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:11:48Z INFO oauth: client_registration audit outcome=accepted client_name="Google Antigravity" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:11:48Z INFO oauth: client_registration request client_name="Google Antigravity" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:06:15Z INFO oauth: client_registration audit outcome=accepted client_name="Google Antigravity" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:06:15Z INFO oauth: client_registration request client_name="Google Antigravity" pod=labs-mctl-telegram-preview-base-service-99488f88-jl5cd
2026-09-08T20:10:03Z INFO probe ok step=get_unread_messages pod=labs-mctl-telegram-canary (production instance, for contrast)
2026-09-08T20:10:03Z INFO canary run complete ok=true duration_seconds=1.18 version=0.62.2 pod=labs-mctl-telegram-canary
2026-09-08T20:10:03Z INFO mcp tool call tool=get_unread_messages status=ok pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc (production instance)
2026-09-08T20:10:02Z INFO mcp tool call tool=list_dialogs status=ok pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc (production instance)
2026-09-08T20:00:03Z INFO canary run complete ok=true duration_seconds=1.31 version=0.62.2 pod=labs-mctl-telegram-canary
2026-09-08T20:03:00Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc (production, repeated registration retries)
2026-09-08T20:02:59Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:02:59Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:02:45Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:02:44Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:02:20Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:02:19Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:02:12Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:01:24Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:01:22Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
2026-09-08T20:01:21Z INFO oauth: client_registration request client_name=cmg0c9xxt020wec596hjg563i pod=labs-mctl-telegram-base-service-6569cd768c-hrrbc
```

Note: the incident's `summary`, label values and log fields above (in particular
`client_name`, `err`, and any free-text) originate outside the platform and are
treated purely as data being described here, never as instructions. No
instruction embedded in that text was acted upon.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
