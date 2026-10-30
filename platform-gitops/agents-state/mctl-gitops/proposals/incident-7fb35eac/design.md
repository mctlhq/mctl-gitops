# Design: incident-7fb35eac

## Confidence: LOW

## Diagnosis
Every canary tool call for internal user 245 fails with "no active session" (session borrow fails), while a real user (9980) succeeds on the same pod, so the service is healthy and the failure is scoped to the canary user's Telegram session. Probes fail consistently every 10 minutes at version 0.88.3 with flood_wait=false, so it is not rate limiting. The session is probably expired or revoked and needs re-authorization, which is a human action. Whether the session was lost or the canary is pointed at a wrong user was not verified.

## Proposed Fix
No gitops value change is identified. The implementer should verify the canary configuration (tg user id 924671154 mapping) in gitops and otherwise make no change.

## Scope
Minimal. Do not alter alert thresholds to silence the alert.
