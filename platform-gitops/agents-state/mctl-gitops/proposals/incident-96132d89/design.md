# Design: incident-96132d89

## Confidence: LOW

## Diagnosis
mctl-agent had no skill for alert MctlTelegramSessionBorrowSlowBurn, so the incident was escalated without analysis. The last ~50 log lines for labs/mctl-telegram (07:10Z) show no errors: the canary passes every step (oauth_metadata, mcp_init, list_dialogs, get_unread_messages) every 10 minutes in about 1.2s, and all MCP tool calls return status=ok. The only session-related line is a normal "idle telegram client, closing" at 06:47Z. The alert is a slow-burn (6x over 6h) warning, so it may have been a transient error-budget burn that has since recovered, or the alert expression may be too sensitive. The logs do not show the cause of the original burn, so the root cause cannot be determined from them.

## Proposed Fix
1. Locate the alert rule MctlTelegramSessionBorrowSlowBurn in mctl-gitops (search for the alert name under platform-gitops/ and the mctl-telegram service chart values / PrometheusRule).
2. Inspect the expression, the metric it uses for session borrow failures, and the burn-rate/threshold. Verify it is not firing on healthy traffic (for example, counting idle-client closes as borrow failures, or having a threshold too low for low traffic volume).
3. Only if the expression is demonstrably wrong, adjust the specific threshold or selector. Otherwise make no change, and add a `runbook`/`description` annotation to the rule explaining what the alert means so future incidents are diagnosable.

Do not make any change that disables the alert.

## Scope
Minimal. Only touch the single rule that causes this alert. Verify before applying, because the evidence does not confirm a defect.
