# Requirements: incident-a436160e

## Incident
- ID: c9138cfb-c1bf-4ab7-a5d6-5fe5a436160e
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-10T19:02:43.822449Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: labs
service: (empty on the incident record; the summary and logs identify it as mctl-telegram)
severity: warning
alert: MctlTelegramSessionBorrowSlowBurn
mctl-agent analysis: "Escalated: no skill matched this ticket (type=generic,
alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the
agent has no diagnostic rule for this signal, so nothing was analysed. Needs
a human, or a new skill."
```

### Log Snippet
Fetched from `labs/mctl-telegram` (base-service container), last 6h window.
Recurring roughly once per minute across the full window, i.e. continuously
during the alert's 6x/6h burn window:
```
2026-09-10T20:11:11.483281236Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:10:11.237554451Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:08:10.787273775Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:07:10.521541761Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:06:10.279202962Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:05:10.051796924Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:04:09.825589555Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:03:09.592694837Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:02:09.372580258Z level=INFO msg="bridge: authentication failed" err="JWT expired"
2026-09-10T20:01:09.155542358Z level=INFO msg="bridge: authentication failed" err="JWT expired"
```
No other error pattern repeats at comparable frequency in the fetched window.
A second, unrelated auth-failure pattern ("invalid JWT signature" on the
`labs-mctl-telegram-preview` pod, tied to OAuth dynamic client registration
from a "Google Antigravity" client) also appears in the same window but is a
different pod, a different failure mode, and not the subject of this
proposal.

## Acceptance Criteria
- WHEN the change is applied THEN the `bridge: authentication failed`
  ("JWT expired") log line stops recurring on the `labs-mctl-telegram`
  base-service pod, and the `MctlTelegramSessionBorrowSlowBurn` alert stops
  firing for tenant labs / service mctl-telegram.
