# Design: incident-cef9e704

## Confidence: LOW

## Diagnosis
The synthetic canary (Telegram user 924671154, mapped to internal user_id 245) completes oauth_metadata and mcp_init successfully, but every session-dependent tool call (list_dialogs, get_unread_messages) fails with err="no active session" and reason=telegram_error. The MCP surface and OAuth are healthy; the canary account has no usable Telegram user session (never logged in, revoked, or expired/invalidated session in the service database). This is the signal behind the session-borrow burn alert. It is most likely a data/credential state problem, not a Helm value problem, and mctl-agent had no skill for it. Related incident 96e29c7a (tool availability) shows the identical failure and has the same root cause. No gitops config change was independently confirmed as the fix.

## Proposed Fix
Do not change resource limits or alert thresholds to silence this. The implementer should verify, in this order:
1. Inspect platform-gitops/services/labs/mctl-telegram/values.yaml for the canary configuration (CronJob, tg user id, session/credential secret references) and confirm the canary points at a user that has a stored active session.
2. If the canary references a wrong or stale user/secret key, correct that single reference.
3. If the configuration is correct, the fix is an operational re-authorization of the canary Telegram account (human action); in that case make no gitops change and record in the PR/notes that manual re-login is needed.

## Scope
Minimal. Only touch the single canary reference that causes this alert. Do not weaken or disable the alert rules.
