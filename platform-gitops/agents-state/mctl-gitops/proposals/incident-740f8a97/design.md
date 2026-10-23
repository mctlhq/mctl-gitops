# Design: incident-740f8a97

## Confidence: LOW

## Diagnosis
The slow-burn alert measures failed session borrows over a 6h window at a 6x burn rate. The logs show one clear contributor: the canary identity (user_id 245) fails every probe with "no active session", every few minutes, so each canary run counts as a failed borrow. CHANNEL_INVALID errors for user_id 183623 are tagged slo_status=caller_error and should not count against the SLO, though I could not confirm from logs alone whether the borrow metric excludes them. The alert is most likely driven by the canary session loss (same root cause as incidents eb51f2c9 and 826783a6) and will clear once the canary Telegram session is restored.

## Proposed Fix
No gitops change is confirmed to be needed. Verify in the mctl-telegram alert rules whether the SessionBorrowSlowBurn expression excludes the canary user and caller_error outcomes. If it does not exclude the canary, consider excluding the canary identity from the borrow SLO expression; otherwise make no change and document that recovery depends on re-login of the canary account.

## Scope
Minimal. Only the single MctlTelegramSessionBorrowSlowBurn expression, and only if the canary is demonstrably counted in it.
