# Design: incident-e533b227

## Confidence: LOW

## Diagnosis
Same root cause as incident-c5455c17. The mctl-telegram pod is healthy and real-user tool calls (user_id 154537) succeed. The failing calls are the synthetic canary (tg_user_id 924671154, mctl user_id 245), where list_dialogs and get_unread_messages return "no active session": the canary's Telegram session is missing or expired. This drives the MCP tool availability SLO burn. Separate CHANNEL_INVALID errors from the real user are already classified slo_status=caller_error and are not the cause. mctl-agent had no skill for this alert. This is not a service outage.

## Proposed Fix
1. In mctl-gitops, inspect platform-gitops/services/labs/mctl-telegram/values.yaml (canary CronJob) and the alert rule MctlTelegramToolAvailabilityFastBurn.
2. The real remedy is a human re-login of the canary Telegram account (credential rotation); record that in the PR description instead of touching secrets.
3. Optionally, if the rule clearly counts canary failures against real-user availability, adjust the single alert expression to separate them. Verify against the existing rule before changing.

## Scope
Minimal. Only touch the canary configuration or the single alert rule. Resolve together with incident-c5455c17.
