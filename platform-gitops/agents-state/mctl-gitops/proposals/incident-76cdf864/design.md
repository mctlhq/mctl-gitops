# Design: incident-76cdf864

## Diagnosis
The labs-mctl-telegram service's base-service pods are losing MCP tool call sessions. The canary probe initializes OAuth metadata successfully and establishes an MCP connection, but user-scoped MCP operations fail with "no active session". This indicates session state was not properly persisted or was cleared between initialization and use. The sustained canary failures caused ArgoCD to detect the service as unhealthy and mark the application degraded. A pod restart will clear any corrupted session state and reset the service to a known good state.

## Proposed Fix
Force a rollout restart of the labs-mctl-telegram deployment to clear session state and reinitialize all pods. In mctl-gitops values.yaml for the labs tenant:

File: `services/labs/mctl-telegram/values.yaml`
Field: `podAnnotations` (add or update)
Current value: (may not exist)
New value: Add `deployment.restart-timestamp: "2026-08-23T03:00:47Z"` to force pod recreation

Alternatively, update the deployment spec's pod template annotation to trigger a rollout restart.

## Scope
Minimal. Only restart the labs-mctl-telegram pods by updating the deployment's podAnnotations to force ArgoCD to detect a change and roll out new pods. This clears session state without code changes or configuration alterations.

## Confidence: LOW
Session state loss is inferred from log patterns. Actual root cause (session cache expiry, persistence layer failure, or improper session lifecycle) requires deeper investigation of the service's session management code.
