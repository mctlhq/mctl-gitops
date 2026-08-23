# Design: incident-6aae5df3

## Diagnosis
The mctl-telegram canary probe in the labs tenant is failing due to persistent "no active session" errors when calling MCP tools. The canary pod successfully establishes OAuth metadata and initializes MCP connections, but cannot maintain active user sessions for subsequent MCP tool calls (list_dialogs, get_unread_messages). This pattern indicates session state corruption or loss in the labs-mctl-telegram service's base-service pods. The underlying issue is session lifecycle management, not infrastructure or connectivity. Restarting the base-service pods will clear session state and allow session re-initialization.

## Proposed Fix
Trigger a rollout restart of the labs-mctl-telegram deployment by updating a pod annotation in mctl-gitops. This causes ArgoCD to detect a change and roll out fresh pods, clearing any corrupted or stale session state.

File: `services/labs/mctl-telegram/values.yaml`
Field: `podAnnotations`
Add: `deployment.restart-timestamp: "2026-08-23T03:00:47Z"`

This forces Kubernetes to recreate all pods in the deployment without code or configuration changes.

## Scope
Minimal. Only the pod restart annotation changes. No service logic, configuration, or image tag modification. Restart clears session state and forces re-initialization of sessions on the next canary run.

## Confidence: LOW
The 'no active session' error strongly suggests session state loss, but the exact layer (cache, persistence, lifecycle hook) is not determinable from logs alone. A restart is a safe first step that clears any transient state corruption without code changes.
