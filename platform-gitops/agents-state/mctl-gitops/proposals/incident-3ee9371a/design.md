# Design: incident-3ee9371a

## Confidence: LOW

## Diagnosis
The alert MctlTelegramSessionBorrowFastBurn (14.4x burn over 1h) fired at 17:44 UTC, and no mctl-agent skill covers it. Available logs only cover from about 18:08 UTC, so the burn window itself is not visible. What is visible: a rollout at 18:08-18:09 UTC, where both the prod and preview pods hit "connection refused" from shared-pg-rw.platform-db (database briefly unavailable) and recovered within about 2 seconds on the first retry. After that the canary reports ok=true and tool calls succeed. The service looks healthy now, so this is likely a transient burn from earlier or a DB blip, not a persistent fault. The root cause of the 17:44 burn cannot be established from these logs. Note the logs also show DEMO_REVIEWER_ENABLED on in the labs prod pod; that is unrelated to this alert and is only noted as an observation.

## Proposed Fix
1. Verify first: query the alert expression for MctlTelegramSessionBorrowFastBurn in mctl-gitops (grep the name under platform-gitops/) and check whether the burn metric is currently below threshold. If it has recovered, no config change is needed; close the proposal as no-op.
2. If the rule counts failures during DB-unavailable windows at rollout, consider adding a `for:` duration or tuning the burn window on that rule. Do not change thresholds without confirming the current value and the SLO it implements.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. If the alert has already cleared, make no change.
