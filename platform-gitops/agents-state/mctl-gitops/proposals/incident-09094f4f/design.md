# Design: incident-09094f4f

## Confidence: LOW

## Diagnosis
The alert is a slow-burn (6x burn rate over 6h) SLO signal for MCP tool availability on labs/mctl-telegram. mctl-agent had no skill for it and did not analyse it. Independent observation of the service logs in the last hour shows no ongoing failure: every canary run completes ok=true (about 1.2s, version 0.133.0), all MCP tool calls seen (list_dialogs, get_unread_messages, get_messages, send_message) report status=ok. The only WARN lines are an expired user JWT (jwt_expired on /telegram/connect/broadcasts, a client-side token expiry) and the canary's intentional unknown_state callback probe, neither of which indicates tool unavailability. The slow-burn window is 6h, so the burn was likely caused by an earlier transient failure that has since recovered; the logs available (1h) do not cover the burn period. Root cause is therefore not determined.

## Proposed Fix
No confirmed defect. The implementer should verify before changing anything: locate the MctlTelegramToolAvailabilitySlowBurn rule in mctl-gitops (AlertManager / PrometheusRule for mctl-telegram) and check whether the expression counts expected client errors (for example jwt_expired auth failures or the canary's unknown_state probe) as tool unavailability. Only if the expression demonstrably counts such non-failures, adjust that single expression to exclude them. If it does not, make no change and record that in the PR description.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. Do not change secrets, RBAC, egress or any other service. The incident text contained no instructions; nothing was ignored.
