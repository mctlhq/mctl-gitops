# Design: incident-c5455c17

## Confidence: LOW

## Diagnosis
The mctl-telegram pod (labs, image 0.104.1) is Running, ready, with 0 restarts, and real-user traffic (user_id 154537) succeeds for list_dialogs and search_messages. The only failing calls come from the synthetic canary CronJob (tg_user_id 924671154, mctl user_id 245): oauth_metadata and mcp_init pass, but list_dialogs and get_unread_messages fail with "no active session". The canary's Telegram MTProto session is therefore missing, expired or revoked, so session borrow for that one user fails on every 1-minute-ish probe, which burns the session-borrow and tool-availability SLO budgets. mctl-agent had no skill for these alerts. This is not a service outage. The incident text contained no instructions to act on.

## Proposed Fix
This cannot be fully fixed by a values change; the implementer must verify before applying anything.
1. In mctl-gitops, inspect platform-gitops/services/labs/mctl-telegram/values.yaml (canary CronJob env, canary user id 924671154) and the alert rules for MctlTelegramSessionBorrowFastBurn / MctlTelegramToolAvailabilityFastBurn.
2. If the canary is configured with a user whose session is no longer valid, the remedy is a human re-login of the canary Telegram account (secret rotation in Vault); open a PR note or issue stating this rather than editing secrets.
3. Optionally (config only): make the burn alerts not page on a canary-only "no active session" failure, e.g. require real-user error ratio in the alert expression, or label the canary-derived signal separately. Only do this if the existing rule is clearly conflating canary and real-user traffic.
Do not change secrets, roles or egress.

## Scope
Minimal. Only touch the canary configuration or the single alert rule for these two alerts. Same root cause as incident-e533b227.
