# Requirements: incident-2430bb39

## Incident
- ID: 0cd105fc-13ff-4a4b-9ac1-8f5b2430bb39
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-23T12:37:43.793003Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
(none returned by mctl_get_incident for this incident — the incident record
carries no separate labels field; tenant/service/alert above were taken from
the top-level incident fields. `service` on the incident itself was empty;
"mctl-telegram" was read out of the alert name and summary text instead.)
```

### Log Snippet
Source: mctl_get_service_logs(team=labs, service=mctl-telegram, since=6h),
fetched in the largest slice the tool would return without exceeding its
output-size limit — the most recent ~44 minutes of the 6h alert window
(2026-09-23T12:31:35Z through 13:15:06Z). Requests for the full 6h (lines=200,
lines=100, lines=90) all failed with "exceeds maximum allowed tokens"; this
responder has no shell to page or filter server-side, so the older ~5h15m of
the window could not be inspected.
```
2026-09-23T12:31:35Z through 13:15:06Z (base-service + canary containers):
  - Every "mcp tool call" log entry in this slice reports status=ok (tools:
    get_messages, send_message:sent, get_unread_messages, list_dialogs).
  - Two "idle telegram client, closing" INFO entries (user_id=105074 at
    12:44:18, idle=651595337200ns; user_id=9980 at 13:11:26,
    idle=621824747581ns) — routine pool eviction of a client idle for
    roughly 10-11 minutes, not an error-level log line.
  - Two "oauth: client_registration request" entries from a Cursor client at
    12:54:34, unrelated to session borrowing.
  - Every /10-min canary probe cycle in the slice (mcp_init, oauth_metadata,
    list_dialogs, get_unread_messages) completed with probe ok / canary run
    complete ok=true.
  - No WARN/ERROR-level log line, and no line naming "borrow", "session
    borrow", or a Pool.Borrow()-style failure, appears anywhere in the
    retrieved slice.
```

## Acceptance Criteria
- WHEN the change is applied THEN the next occurrence of this alert (or the
  same alert firing on a later window) can be triaged directly against the
  mctl_sessions_borrow_total{result} series and this log-tooling limitation,
  without re-deriving either from scratch.

## Confidence: LOW
No borrow-error log line was found, but only ~44 minutes of the 6h alert
window could be retrieved (see Log Snippet). Absence of evidence in a
twelfth of the window is not evidence of absence for a 6h burn-rate alert.
See design.md for why no alerting-threshold or service-config change is
proposed here.
