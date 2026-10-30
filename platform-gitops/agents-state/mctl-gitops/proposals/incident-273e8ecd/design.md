# Design: incident-273e8ecd

## Confidence: LOW

## Diagnosis
The session-borrow SLO burn matches the observed failures: borrowing a Telegram client session for user_id 245 fails with "no active session". The pod is healthy, so this is a missing or expired session for that account rather than a capacity or config issue. The alert rule had no matching skill.

## Proposed Fix
No gitops value change is evident. Treat as a duplicate of incident-41b2515a. Optionally check the MctlTelegramSessionBorrow alert rule only for obviously wrong thresholds; do not loosen thresholds to silence the alert.

## Scope
Minimal.
