# Design: incident-a6a813e1

## Confidence: LOW

## Diagnosis
The `MctlTelegramSessionBorrowSlowBurn` alert has no matching skill because it
is a generic burn-rate alert with no dedicated diagnostic rule. Logs for
labs/mctl-telegram (base-service container) show a "bridge" component logging
`bridge: authentication failed` with `err: JWT expired` at a steady cadence of
roughly once every 60 seconds, with no successful re-authentication visible in
the sample window. A steady, unresolving failure on that cadence over several
hours is consistent with a "slow burn" (6x baseline over 6h) of failed session
borrows: something in the service periodically attempts to borrow/refresh a
Telegram session through this bridge, presents a JWT to authenticate that
call, and the JWT is already expired by the time it is used — most likely
because the token is minted once (e.g. at bridge/session creation) with a
short TTL and is never refreshed before the next borrow attempt, or the
refresh path itself is broken. This investigator has no source access to the
mctl-telegram repo (no shell, no local checkout), so the exact file/line
could not be confirmed — root cause is inferred from the log pattern alone.

## Proposed Fix
In the mctl-telegram repository, locate the "bridge" component's session
authentication/token logic (search for the log strings `"bridge: authentication failed"`
and `"JWT expired"`, and for wherever the bridge's JWT is minted or cached).
Then:
1. Confirm whether the JWT used by the bridge for session borrow has a TTL
   shorter than (or close to) the interval between borrow attempts (~60s
   observed here).
2. If so, either extend the token TTL to comfortably exceed the borrow
   interval, or add a proactive refresh (re-mint/renew the token before it
   expires) ahead of each borrow attempt instead of reusing a cached token
   past its expiry.
3. If a refresh path already exists but is not being invoked (e.g. an error
   is swallowed, or the refresh call itself needs a valid token it no longer
   has — a refresh deadlock), fix the refresh call so it does not depend on
   the already-expired token.

Because the exact code location is unconfirmed, the implementer should verify
the mechanism in source before changing values, and should prefer the
smallest fix that keeps the bridge's session token valid across a full borrow
cycle.

## Scope
Minimal. Only touch the bridge's token lifetime/refresh logic. Do not change
unrelated auth paths (e.g. the OAuth issuer, canary probe tokens, or the
preview environment's local-jwt startup auth), which are logging separately
and do not show this failure pattern.
