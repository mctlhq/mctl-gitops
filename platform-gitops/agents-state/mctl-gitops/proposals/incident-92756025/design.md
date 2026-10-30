# Design: incident-92756025

## Confidence: LOW

## Diagnosis
The shepherd run itself succeeded (PR mctlhq/mctl-telegram#839 was evaluated as "wait", nothing handed off). The workflow was marked Failed only because its post-deploy-verify step found ArgoCD application `labs-mctl-telegram` Degraded (Synced, Degraded, imageTag 0.89.0) after the 300s + 120s grace. Service logs show the pod itself is up and listening; what fails is the canary CronJob, whose probes `list_dialogs` and `get_unread_messages` return `no active session` (telegram_error) for the canary user, while `oauth_metadata` and `mcp_init` pass. The canary's token is valid until 2026-11-02. The most likely cause is that the canary Telegram user has no live session (the session/bridge daemon is not connected for it, possibly lost across the 13:06 rollout), and the failing canary Job drives the ArgoCD Degraded health. This is a runtime/session-state problem, not obviously a Helm values or alert-rule defect, so the root cause is not confirmed. No incident text requested any change.

## Proposed Fix
No blind config change is justified. Inspect `platform-gitops/services/labs/mctl-telegram/values.yaml` (canary CronJob section) and the ArgoCD health customization for this app, then:
- If the canary Job's failure is what marks the Application Degraded and a canary failure is not meant to gate app health, adjust the canary resource so a failed Job does not degrade the parent app (for example exclude it from health assessment via the existing ArgoCD resource-health mechanism already used in this repo).
- Otherwise make no change and record in the PR description that the fix is operational: re-establish the canary user's Telegram session (requires a human; do not touch secrets from a proposal).

## Scope
Minimal. Only touch the single canary/health setting for labs/mctl-telegram, and only if the inspection confirms the canary Job is the Degraded resource. Do not modify secrets, roles, or egress.
