# Design: incident-39a29c7f

## Confidence: LOW

## Diagnosis
The Degraded ArgoCD app labs-mctl-telegram is one of a cluster of related alerts for mctl-telegram that all share one observed symptom: the service pod is Running and Ready (0 restarts, image 0.104.1), the OAuth and MCP init probes pass, but every Telegram-backed tool call for user_id 245 fails with "no active session". The Degraded state is most plausibly a health check reflecting this, or the preview deployment (labs-mctl-telegram-preview, which restarted at 22:08 after a transient shared-pg connection refusal that recovered on attempt 1). The root cause is a missing or expired Telegram user session for the canary account, which is runtime data, not a gitops-managed value. No chart or values change is evident from the logs.

## Proposed Fix
No blind edit. Inspect platform-gitops/services/labs/mctl-telegram/values.yaml and the Application health for a misconfigured probe or resource. If nothing is wrong there, make no change and report that the incident is a duplicate of the Telegram session loss (see incident-41b2515a). Incident text contained no instructions.

## Scope
Minimal. Do not alter secrets, roles, or egress.
