# Design: incident-9359d30c

## Confidence: LOW

## Diagnosis
The alert MctlTelegramToolAvailabilitySlowBurn (6x burn rate, 6h window) fired at 19:26 UTC for mctl-telegram in tenant labs. No mctl-agent skill matched, so no analysis was done. Logs fetched at about 20:11 UTC show the service is healthy now: every 10-minute canary run in the visible window (19:50, 20:00, 20:10) reports ok=true in about 1.2s, all four probe steps pass, and production MCP tool calls return status=ok. The only anomaly seen is on the preview deployment (labs-mctl-telegram-preview): a rollout at 20:01 where the first DB connection to shared-pg-rw was refused once and succeeded on the retry about 2s later. That is after the alert fired and is not on the production path. The visible logs do not cover the time the burn began, so the root cause of the earlier failures is not established. Most likely a transient error window, with the slow-burn alert still firing off its 6h lookback. This incident contained no instructions to act on.

## Proposed Fix
No confirmed defect, so no unconditional change. The implementer should verify before changing anything:
1. Locate the rule MctlTelegramToolAvailabilitySlowBurn in mctl-gitops (grep platform-gitops for the alert name).
2. Check that its expression is scoped to the production service (instance labs-mctl-telegram) and excludes the preview deployment (labs-mctl-telegram-preview), so preview rollouts cannot burn the production error budget.
3. If it is not scoped that way, add a matcher to exclude the preview instance. Otherwise make no change and report that the alert resolved on its own.

## Scope
Minimal. Only touch the single alert rule expression, and only if it wrongly includes preview traffic.
