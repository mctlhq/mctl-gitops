# Design: incident-92175190

## Confidence: LOW

## Diagnosis
Tool availability burn is driven by canary calls (list_dialogs, get_unread_messages) failing for internal user 245 with "no active session". Other users' calls succeed on the same pod, so this is the canary user's lost Telegram session, the same root cause as the sibling session-borrow incident. Real-user availability appears unaffected in current logs; the burn is probably the canary's own failures counted in the SLI. This was not verified against the metric definition.

## Proposed Fix
No gitops value change is identified. Remedy is manual re-authorization of the canary user's Telegram session. Optionally the implementer may check whether the availability SLI should exclude the canary user, but only if the alert rule definition in gitops clearly counts it; do not change thresholds.

## Scope
Minimal. Touch nothing unless a concrete misconfiguration is found.
