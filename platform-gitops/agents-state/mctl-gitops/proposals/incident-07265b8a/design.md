# Design: incident-07265b8a

## Confidence: LOW

## Diagnosis
The alert MctlTelegramToolAvailabilitySlowBurn is a 6x burn-rate alert over a 6h window on MCP tool availability for mctl-telegram. mctl-agent had no skill for it and escalated. The last ~50 log lines for labs/mctl-telegram show no errors: the synthetic canary (every 10 minutes, version 0.78.0) passes all steps (oauth_metadata, mcp_init, list_dialogs, get_unread_messages) in about 1s, and real tool calls (get_messages, list_dialogs, get_unread_messages) return status=ok. The service looks healthy now, so the slow burn was likely a transient earlier error spike that has since recovered, or the alert's SLI query counts something the logs do not show (for example non-ok statuses from the preview instance or a specific tool). The root cause cannot be confirmed from the available logs. The incident had no empty-service field fix target, and the incident text contained no instructions.

## Proposed Fix
No config change can be justified from the evidence. The implementer should verify before applying anything:
1. Locate the rule MctlTelegramToolAvailabilitySlowBurn in mctl-gitops (grep platform-gitops for the alert name) and read its expression.
2. Check whether the SLI includes the `labs-mctl-telegram-preview` instance or counts expected client errors (for example auth or rate-limit statuses) as failures. If so, narrow the selector to the production instance (`instance="labs-mctl-telegram"`) or exclude expected statuses.
3. If the expression is correct, make no change and record in the PR/notes that the alert was transient.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert, and only if step 2 confirms a selector problem.
