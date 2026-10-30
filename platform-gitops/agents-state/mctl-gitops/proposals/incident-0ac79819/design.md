# Design: incident-0ac79819

## Confidence: LOW

## Diagnosis
The tool-failure-rate alert is explained by the same logs as the canary alert: Telegram-backed MCP tools return "no active session" for user_id 245. The attached analysis from the argocd_sync_failed skill (Degraded, no signature) is a mismatched skill and carries no evidence. The pod is Ready with 0 restarts. Root cause is a missing Telegram session, not a deployment fault.

## Proposed Fix
No gitops change is evident. Treat as a duplicate of incident-41b2515a. If the implementer finds an actual misconfiguration in platform-gitops/services/labs/mctl-telegram/values.yaml, fix only that field; otherwise make no change.

## Scope
Minimal.
