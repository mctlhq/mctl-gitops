# Design: incident-db31e9d4

## Confidence: LOW

## Diagnosis
The failing tool calls in the logs are the canary's (user 245): "no active session" on list_dialogs and get_unread_messages, roughly twice per 10-minute canary run. Real-user calls succeed. Because canary traffic is a large share of low overall call volume, it can push the error ratio above 10%. Root cause is the canary user's missing Telegram session, shared with the sibling mctl-telegram incidents. Not verified against the alert expression.

## Proposed Fix
No gitops value change is identified. Remedy is manual re-authorization of the canary session. The implementer may check the HighToolErrorRate expression for mctl-telegram and report whether canary calls are included, without changing thresholds.

## Scope
Minimal. Touch nothing unless a concrete misconfiguration is found.
