# Design: incident-c39c5ca7

## Confidence: LOW

## Diagnosis
The SessionBorrow SLO is burning because the canary user (internal user_id 245, tg_user_id 924671154) gets "no active session" on every tool call (list_dialogs, get_unread_messages), while the oauth_metadata and mcp_init steps pass. So the service is up but has no usable Telegram session for that user: the stored session may be expired or revoked, or the session borrow path fails to find it. Separately, the bridge for user_id 6462 connects and disconnects two different devices alternately every 1-3 seconds, which suggests two daemons fighting for one session slot. This may or may not be related. The ArgoCD app labs-mctl-telegram is also Degraded (Synced, image 0.89.0), which is probably the same root cause. mctl-agent had no skill for this alert. The root cause is not confirmed from logs alone.

## Proposed Fix
1. In the mctl-telegram repo, inspect the session borrow path. Find where "no active session" is returned and why it fires for a user with a valid token.
2. Check the bridge daemon registration logic. Two device IDs for one user should not evict each other in a loop. Add single-owner or backoff handling.
3. If the canary session is simply revoked, re-authenticating the canary Telegram account is an operational step outside this repo. Note it in the PR description and do not change secrets.
4. Check why the ArgoCD health is Degraded (probe or pod state) and fix only what is evidently wrong.

## Scope
Minimal. Only touch the session borrow and daemon registration code paths. No secret or access-policy changes.
