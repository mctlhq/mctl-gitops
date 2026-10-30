# Design: incident-0c5e067d

## Confidence: LOW

## Diagnosis
The alert MctlTelegramToolAvailabilitySlowBurn is a 6x burn-rate alert over 6h on MCP tool availability for mctl-telegram. mctl-agent had no skill for it, so no analysis was done. In the most recent logs the production instance (labs-mctl-telegram) serves tool calls with status ok, and the synthetic canary (version 0.88.3) passes all steps (oauth_metadata, mcp_init, list_dialogs, get_unread_messages) every 10 minutes. The only recurring error is in the PREVIEW instance (labs-mctl-telegram-preview): "human input poll actor failed ... outcome=api_503" every 30-60 seconds, so that preview polls an upstream API that keeps returning 503. The most plausible cause is that the availability SLI is counting failures from the preview instance (or from a historical failure window earlier than the logs fetched), rather than a current production outage. This could not be confirmed from logs alone; the alert expression and the SLI recording rule were not visible to the responder.

## Proposed Fix
1. In mctl-gitops, locate the alert rule MctlTelegramToolAvailabilitySlowBurn and its SLI recording rule (search platform-gitops for the alert name).
2. Check whether the SLI selector includes the preview instance (instance="labs-mctl-telegram-preview"). If it does, restrict the selector to the production instance (instance="labs-mctl-telegram") so preview 503s cannot burn the production budget.
3. If the selector is already production-only, make no change to the rule and instead record in the PR description that production logs show no tool failures in the last hour and the canary is green, so the alert is likely a historical burn that will clear on its own.
4. Separately, the preview instance's 503 from the human-input poll should be investigated by the owners of mctl-telegram (upstream API returning 503 for user_id=1); no change is proposed for it here.

## Scope
Minimal. Only touch the selector of the single SLI/alert rule for this alert. Do not change thresholds, silence the alert, or modify any other rule.
