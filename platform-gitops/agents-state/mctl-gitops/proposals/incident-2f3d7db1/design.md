# Design: incident-2f3d7db1

## Confidence: LOW

## Diagnosis
The alert MctlTelegramToolAvailabilitySlowBurn (6x burn, 6h window) escalated because mctl-agent has no skill for it. The service itself looks healthy: the synthetic canary (mcp_init, list_dialogs, get_unread_messages) passed at 09:00 and 09:10 and ordinary tool calls return status=ok. The only errors in the recent logs are search_messages calls failing with Telegram CHANNEL_INVALID (HTTP 400) for a single user, already tagged slo_status=caller_error by the service. These are caller errors (a stale or invalid channel id) and should not count against tool availability. The most likely cause is that the availability SLO alert expression counts such errors as failures, or that some other error class (not visible in the last 50 lines) is driving the burn. Logs only cover about 10 minutes, so the 6h burn cannot be confirmed.

## Proposed Fix
Verify first, then change only if confirmed:
1. In mctl-gitops, find the PrometheusRule defining MctlTelegramToolAvailabilitySlowBurn (search platform-gitops for the alert name).
2. Check whether the error-ratio numerator excludes calls with slo_status="caller_error" (or equivalent label). If it does not, exclude them, so the numerator counts only server-side failures.
3. If the numerator already excludes them, make no change and report that the alert reflects a real burn needing a human to investigate in Loki/Prometheus over the 6h window.

## Scope
Minimal. Only touch the single expression or rule for this alert. Do not change thresholds or silence the alert.
