# Design: incident-6b0018ea

## Confidence: LOW

## Diagnosis
The alert MctlTelegramOAuthAvailabilitySlowBurn (6x burn rate over 6h, warning) fired for the OAuth token endpoint of mctl-telegram. No skill matched, so no analysis existed. Current logs do not show an active OAuth failure: the synthetic canary at 03:10:03Z passed every step (oauth_metadata, mcp_init, list_dialogs, get_unread_messages) in about 1s with a token valid until 2026-11-22, and the production pod serves MCP tool calls with status ok. This suggests the burn was transient (it may already have recovered) or is concentrated in a window not covered by the last 50 log lines. The only anomaly in the logs is the preview deployment (labs-mctl-telegram-preview) logging AUTH_KEY_UNREGISTERED every 5 seconds: its stored Telegram session for user_id 1 was revoked. That is a separate defect and is not shown to affect the token endpoint, but if the preview shares the alert's metrics selector it could be inflating the error ratio. This is unverified.

## Proposed Fix
Verify first, then apply only what is confirmed:
1. In mctl-gitops, find the rule MctlTelegramOAuthAvailabilitySlowBurn (grep platform-gitops for the alert name). Check that its expr selects only the production instance (for example instance="labs-mctl-telegram") and excludes the preview instance (instance="labs-mctl-telegram-preview"). If the selector is unscoped and includes preview or non-token-endpoint failures, add the missing matcher. Do not change the burn-rate threshold or the 6x/6h window.
2. If the selector is already scoped correctly, make no change and record in the PR/notes that the alert was transient and no fix is needed.
3. Separately note (do not fix here): the preview deployment's Telegram session needs re-authentication, or the preview agent poll should be disabled. That requires a human to re-login and a secret change, which is out of scope for this proposal.

## Scope
Minimal. Only touch the single alert rule expression if a selector problem is confirmed. No secret, session, or threshold changes.
