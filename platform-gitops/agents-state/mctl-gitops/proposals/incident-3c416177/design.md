# Design: incident-3c416177

## Confidence: LOW

## Diagnosis
The alert is an SLO fast-burn on MCP tool availability for labs/mctl-telegram. No agent skill matched, so nothing was analysed. Current service logs show the service healthy: the canary completes ok (all probe steps ok, version 0.90.0) and tool calls return status ok. The only anomaly is a rollout at about 18:08-18:09 where both the production and preview pods logged "connection refused" from shared-pg-rw.platform-db for the first attempt, then recovered on the second attempt. This suggests the shared Postgres endpoint was briefly refusing connections during the rollout, and the alert burn window overlaps that deploy. The 17:38 alert predates these logs, so the root cause of the original burn is not directly observed. No evidence of a persistent defect in the service config was found.

## Proposed Fix
No configuration change is justified by the evidence. The implementer should first verify that the alert is no longer firing and that the ArgoCD app labs-mctl-telegram is Healthy/Synced. If it is, make no change and close this proposal as a no-op. If the alert is still firing, inspect the MctlTelegramToolAvailabilityFastBurn rule in mctl-gitops and check whether rollouts (replicas, readiness probe, maxUnavailable) in platform-gitops/services/labs/mctl-telegram/values.yaml allow a window where no ready pod serves traffic; if so, consider ensuring the readiness probe gates on DB reachability.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert, and only if verification shows it is still firing.
