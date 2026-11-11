# Design: incident-8b02f191

## Diagnosis
The slow-burn SLO alert for the mctl-telegram OAuth endpoint fired, but no skill matched it. Current logs show the service healthy: the canary passes every 10 minutes (ok=true, about 1.4s) and MCP tool calls succeed. The only OAuth WARN is `unknown_state` on `/oauth/telegram/callback`, which is emitted deliberately by the canary's `callback_unknown_state` probe (probe ok). A likely cause is that this intentional negative probe is counted as a failed request in the availability SLI, which burns budget at a steady rate. This is not confirmed: the alert rule was not available to inspect and no token-endpoint errors appear in the last hour of logs.

## Proposed Fix
Locate the PrometheusRule for MctlTelegramOAuthAvailabilitySlowBurn in mctl-gitops (search for the alert name under platform-gitops/). Check whether the SLI error ratio counts 4xx from `/oauth/telegram/callback` or from canary traffic (user_agent mctl-telegram-canary). If so, exclude those from the error numerator (for example, count only 5xx or exclude the canary route/user agent). If the rule is already correct, make no change and document that the alert was a transient burn that has recovered.

## Scope
Minimal. Only the single SLI expression for this alert, and only if the cause above is verified.

## Confidence: LOW
