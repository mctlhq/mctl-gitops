# Design: incident-87497762

## Diagnosis
The labs-mctl-telegram service has lost or failed to initialize session state in its MCP tool management layer. The service's canary probe runs repeatedly but consistently fails because all MCP tool calls return "no active session" errors. This has persisted across multiple 10-minute probe intervals (observed at 15:40, 15:50, 16:00+). When the shepherd workflow merged a PR and ran post-deploy-verify, ArgoCD correctly reported the service as Degraded, causing the shepherd to fail. The shepherd is working as designed — the real issue is the session initialization in labs-mctl-telegram.

The root cause is either:
1. Session state is not being initialized when the service starts or reconnects
2. Session state is being lost or cleared unexpectedly
3. Session authentication/validation is failing for user_id=1 (the canary probe user)

## Proposed Fix
Investigate and resolve the session management in labs-mctl-telegram's MCP tool layer. Specific areas to check:
- Session initialization on service startup
- Session persistence across pod restarts or container updates
- MCP connection state and session validation logic
- Whether the service's recent deployment (imageTag: 0.50.1) introduced a regression in session handling

The fix may require:
- Code changes to session initialization logic
- Configuration changes to session timeout or retry behavior
- Debugging why the canary probe (user_id=1) has no active session

## Scope
Minimal. This is a single service health issue affecting only labs-mctl-telegram. The fix is scoped to restoring session management in that service's MCP tool layer.

## Confidence: LOW
Without access to labs-mctl-telegram's codebase and runtime state inspection, the exact cause of the missing session is not fully determined. The implementer should verify the session initialization logic, check service logs for startup/connection errors, and possibly add debugging to understand why the session is not active.
