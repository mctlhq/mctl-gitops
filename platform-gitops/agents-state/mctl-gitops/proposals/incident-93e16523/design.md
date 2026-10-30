# Design: incident-93e16523

## Confidence: LOW

## Diagnosis
Same root cause as incident 1694c084 (proposal incident-cef9e704). The canary completes oauth_metadata and mcp_init, but list_dialogs and get_unread_messages fail with err="no active session" for internal user_id 245 (Telegram user 924671154). Tool availability drops because the canary account has no active Telegram session; the MCP service itself is up. mctl-agent had no matching skill. No gitops config change was independently confirmed as the fix.

## Proposed Fix
Coordinate with incident-cef9e704; do not make duplicate changes.
1. Inspect platform-gitops/services/labs/mctl-telegram/values.yaml canary configuration (user id, session/credential secret references).
2. If a reference is wrong or stale, correct that single field.
3. Otherwise no gitops change: manual re-authorization of the canary Telegram account is required (human action); record this in the PR/notes.

## Scope
Minimal. Do not weaken or disable the alert rules.
