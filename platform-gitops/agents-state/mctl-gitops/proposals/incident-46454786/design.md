# Design: incident-46454786

## Confidence: LOW

## Diagnosis
mctl-agent had no skill for MctlTelegramConnectorNoFirstCall, so nothing was analysed. Independent observation of labs/mctl-telegram shows the service healthy: one pod Running and ready with 0 restarts on image 0.119.0, the canary passing every probe (OAuth metadata, MCP init, list_dialogs, get_unread_messages) with a 1.1s run, and real users (user ids 267999, 96357, 6462) making successful MCP tool calls through the edge. The pod was created at 12:51:09Z, about 12 minutes after the alert fired at 12:39:39Z, which points to a rollout from 0.118.0 to 0.119.0 (both images were still listed in the service at last check). The most likely cause is a transient: tokens were issued around the rollout and the first-call counter did not move until the new pod served traffic. This is an inference from timing, not confirmed, and no incident text asked for any change. The alert rule itself was not available to this responder.

## Proposed Fix
No service, resource or secret change is justified by the evidence. The implementer should:
1. Locate the AlertManager/PrometheusRule definition for MctlTelegramConnectorNoFirstCall in mctl-gitops.
2. Check whether the expression compares token issuance against first-call counters over a window short enough to fire during a rolling deploy or pod restart (counters reset on a new pod).
3. If so, add a `for:` duration or widen the window so a single rollout does not trigger it. Change only that field, and state the current and new values in the PR.
4. If the rule already tolerates rollouts, make no change and report that the alert self-cleared.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. Do not modify the mctl-telegram deployment, secrets or egress.
