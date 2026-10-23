# Design: incident-19770fcd

## Diagnosis
The synthetic canary (CronJob labs-mctl-telegram-canary, tg_user_id 924671154, service user_id 245) passes OAuth metadata and MCP init, but every tool call fails with "no active session" (telegram_error). A real user (user_id 9980) succeeds in the same pod at the same time, so the service itself is healthy. The most likely cause is that the canary account's stored Telegram session is missing, revoked or expired, so each canary probe counts as a failed session borrow and burns the SLO budget. mctl-agent had no skill for this alert. Logs alone do not show why the session was lost, and re-authenticating a Telegram account is an interactive operator action that cannot be done through a gitops change.

## Proposed Fix
No config value was identified from the evidence as the cause. The implementer should inspect the canary CronJob values in platform-gitops/services/labs/mctl-telegram/values.yaml (canary user id / token / schedule) and confirm they reference the intended canary account. Do not change secrets or credentials. If the values are correct, open a note in the PR description that the canary Telegram session must be re-established by an operator, and do not alter alert thresholds to silence the burn alert.

## Confidence: LOW

## Scope
Minimal. Verification only unless a clearly wrong canary reference is found.
