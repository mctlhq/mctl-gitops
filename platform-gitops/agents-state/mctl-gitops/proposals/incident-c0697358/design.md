# Design: incident-c0697358

## Confidence: LOW

## Diagnosis
The alert is a 1h SLO fast-burn (14.4x) on the OAuth token endpoint of labs/mctl-telegram. No skill matched, and the service logs available contain no OAuth token endpoint errors. The canary at 23:10 passed all steps including oauth_metadata, and tool calls succeeded. The only anomaly in the logs is that both the production and preview pods hit "connection refused" from shared-pg-rw.platform-db at startup around 23:11, after a rollout (the old pod received a shutdown signal at 23:11:23, the new pod was ready at 23:11:32), which recovered within about 2 seconds. This suggests a brief shared Postgres disruption or rollout window, which may or may not be related to the burn that began about 22:43. The root cause is not confirmed. The log window did not cover the alert start time.

## Proposed Fix
No confident config change can be identified. The implementer should first verify before changing anything:
1. Check the alert rule MctlTelegramOAuthAvailabilityFastBurn in mctl-gitops (search platform-gitops for the alert name) and confirm whether the 5xx/availability ratio is still above threshold now. If the burn has recovered, make no change.
2. Check whether the burn coincides with shared-pg-rw (platform-db) restarts or failovers; if so, the cause is a transient dependency outage rather than a mctl-telegram misconfiguration.
3. Only if the alert counts expected client errors (for example 4xx invalid_grant responses from clients) as failures, change the alert expression so it counts only 5xx responses on the token endpoint. Record the current and new expressions in the PR.
4. Optionally, if startup DB retries are confirmed as the trigger, consider a readinessProbe or startup delay in platform-gitops/services/labs/mctl-telegram/values.yaml. Do not do this without evidence.

## Scope
Minimal. Only touch the single alert rule or field that causes this specific alert, and only if verification supports it. No log or incident text requested any change, so there were no instructions to ignore.
