# Design: incident-41b2515a

## Confidence: LOW

## Diagnosis
The canary reaches the service, passes oauth_metadata and mcp_init, then fails list_dialogs and get_unread_messages. The server logs show the real error: "no active session" (reason telegram_error) for user_id 245, canary Telegram id 924671154. flood_wait is false, so this is not Telegram rate limiting. The canary account has no usable Telegram session in mctl-telegram: it was never established, was revoked, or was lost. The auto-fix skills had no rule for this. The alert originates from pushgateway metrics, so the tenant/service fields on the incident (monitoring/prometheus-pushgateway) are not the faulty component.

## Proposed Fix
This is operational, not a gitops value: the canary account must re-authorize its Telegram session. The implementer cannot do this. Check whether the canary config in platform-gitops/services/labs/mctl-telegram/values.yaml refers to the correct user and that session storage (database/secret reference) is intact. If config is correct, make no change and open no PR; flag for a human to re-login the canary account. A code-level follow-up (mctl-telegram: surface session-expired distinctly, or restore sessions after pod restart; pod started 21:10:28) may be worth an issue.

## Scope
Minimal. Do not modify secrets or alert rules to silence the alert.
