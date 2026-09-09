# Design: incident-2e838012

## Diagnosis
The alert name and its "14.4x, 1h" burn value match the standard multi-window,
multi-burn-rate SLO pattern (a 1h-window fast-burn check at ~14.4x normal rate
is the classic "page immediately" threshold for a 2%-of-30-day error budget),
so `MctlTelegramSessionBorrowFastBurn` is very likely burning down a budget on
how often the service has to acquire ("borrow") a Telegram MTProto client
session, rather than reporting a literal outage. No skill matched because the
platform has no diagnostic rule for this specific signal (per the incident's
own `analysis` field), not because the signal is spurious. Recent logs for
labs/mctl-telegram show a plausible mechanism: base-service closes idle
Telegram clients after ~651278792772ns (~10.85 minutes) of inactivity
("idle telegram client, closing", user_id=9980), and several `get_messages`
calls in the same window fail with `PEER_ID_INVALID` / `CHANNEL_INVALID`
because the peer isn't in the current dialog list — consistent with a session
having been evicted and recreated with a stale/incomplete dialog cache.
Bursty, multi-user traffic (user_ids 1, 245, 9980 all active within the log
window) against a short idle timeout would force frequent session borrows as
each user's client is torn down and rebuilt, which lines up with a "fast
burn" of a session-borrow budget. The 50 most recent log lines pulled do not
contain a literal "session borrow" error or expose the pool's configured
size/timeout, so the mechanism above is inferred, not confirmed from logs
alone.

## Confidence: LOW

## Proposed Fix
Increase the Telegram client session idle-timeout (and/or session pool size)
for the mctl-telegram service in its GitOps Helm values, so idle clients are
not torn down and re-borrowed as aggressively under normal bursty traffic:
- File: `services/labs/mctl-telegram/values.yaml` (path may differ slightly —
  implementer should locate the actual values file for the labs mctl-telegram
  service and confirm the field name for the session idle timeout / pool size
  before editing; field may be under a `sessionPool`, `telegram`, or `env`
  block).
- Current value: idle timeout observed in logs at ~10.85 minutes
  (651278792772ns).
- New value: increase to a longer idle timeout (e.g. 30 minutes) and/or raise
  the session pool's max size, whichever field the chart actually exposes.
- Fallback if no such tunable exists: widen the `MctlTelegramSessionBorrowFastBurn`
  AlertManager rule's burn-rate threshold or window for the labs tenant only,
  but only after a maintainer confirms pool sizing is not the true root cause
  — do not silently mute the alert.

## Scope
Minimal. Only touch the session idle-timeout/pool-size setting (or, as
fallback, the one AlertManager rule threshold) for the labs mctl-telegram
service. Do not change other tenants' configuration or unrelated values.
