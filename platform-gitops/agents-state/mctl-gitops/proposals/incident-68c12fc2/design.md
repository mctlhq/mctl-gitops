# Design: incident-68c12fc2

## Diagnosis
The fast-burn SLO alert for the mctl-telegram OAuth endpoint fired, but no skill matched it. Current logs show the service healthy: the canary passes every 10 minutes (ok=true, about 1.4s) and MCP tool calls succeed. The only OAuth WARN is `unknown_state` on `/oauth/telegram/callback`, which is emitted deliberately by the canary's `callback_unknown_state` probe (probe ok). A likely cause is that this intentional negative probe is counted as a failed request in the availability SLI. This is not confirmed: the alert rule was not available to inspect and no token-endpoint errors appear in the last hour of logs. This is the sibling of incident-8b02f191 (slow burn); one fix should cover both.

## Proposed Fix
Locate the PrometheusRule for MctlTelegramOAuthAvailabilityFastBurn in mctl-gitops (search for the alert name under platform-gitops/). Check whether the SLI error ratio counts 4xx from `/oauth/telegram/callback` or canary traffic. If so, exclude those from the error numerator (count only 5xx or exclude the canary route/user agent). If the rule is already correct, make no change and document that the burn was transient and has recovered.

## Scope
Minimal. Only the single SLI expression for this alert, and only if the cause above is verified.

## Confidence: LOW
