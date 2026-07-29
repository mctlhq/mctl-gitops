# Requirements: incident-c33cf596

## Incident
- ID: 8ff99e00-e49c-43f4-a2e1-3f396344595e
- Tenant: nfc
- Service: quirestack-web
- Alert: argocd_app_degraded
- Created: 2026-07-27T14:31:20Z
- Summary: ArgoCD app nfc-quirestack-web health: Degraded

## Evidence
### Labels
- type: argocd_app_degraded
- source: polling
- service: quirestack-web
- tenant: nfc
- severity: warning
- confidence: LOW (as noted in incident analysis)

### Log Snippet
Recent logs show repeated runtime errors from the Next.js application:
- Multiple "Error: The Server Reference ID did not match the expected format. Received '0000000000000000000000000000000000000000'" errors occurring every few seconds
- Earlier error: "[Error [BetterAuthError]: You are using the default secret. Please set `BETTER_AUTH_SECRET` in your environment variables"
- Successful deployment log line: "$ next start -p 3000" and "Ready in 2.8s"
- The application started successfully but then encountered server action errors (all zero server reference IDs)

The pod is running and responding but experiencing repeated failures when handling Next.js server actions.

## Acceptance Criteria
- WHEN the application environment is properly configured with required secrets (BETTER_AUTH_SECRET) AND server action serialization is fixed OR a build cache is invalidated THEN the ArgoCD health check passes and the service becomes Healthy.
