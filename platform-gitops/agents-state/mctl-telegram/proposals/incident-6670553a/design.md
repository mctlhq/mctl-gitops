# Design: incident-6670553a

## Diagnosis
MctlTelegramSessionBorrowFastBurn fires when
`mctl_telegram:session_borrow_errors:ratio_rate1h` — the share of
`Pool.Borrow()` calls with `result="error"` over the trailing 1h, excluding
`expired_idle`/`expired_absolute` TTL expirations — exceeds 14.4%, the
fast-burn threshold for the 99% session-borrow-success SLO objective
(source of truth: docs/slo.md in mctlhq/mctl-telegram, deployed as
platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml).
mctl-agent has no skill wired to this alert name, so it escalated with "no
diagnostic rule for this signal" and no proposed fix.

Loki logs available for team=labs/mctl-telegram cover roughly
2026-09-22T07:30:00Z through 08:11:32Z (about 40 minutes after the alert
fired) and show only successful canary probes and `status="ok"` MCP tool
calls — no ERROR-level line, and no line mentioning "borrow" at all. The log
tool has no offset/pagination and this service's line volume is high enough
that the earlier part of the alert's 1h burn window (~06:20-07:30) could not
be retrieved without exceeding the response size limit, so this is a partial
window, not full coverage of the burn period.

Two explanations are consistent with what was observed, and the available
evidence cannot distinguish between them:
(a) The burn was a statistical artifact of low traffic. The rule file's own
    authors document this explicitly: "on a low-traffic service a 1h window
    holds few invocations, so a couple of errors can cross a burn threshold
    ... Known property, not a bug." docs/slo.md deliberately has no
    minimum-volume guard, so a handful of borrows (e.g. 2 of 13) can already
    exceed 14.4%.
(b) `Pool.Borrow()` failures are not logged at a level/content that would
    show up in a tail sample. This would also explain why mctl-agent had "no
    diagnostic rule": there is nothing in the logs for a skill to pattern-match
    against, only the metric.

No direct query access to the raw `mctl_sessions_borrow_total` counter values
(e.g. via VictoriaMetrics) was available to this responder, so the actual
error count/denominator for the burn window is unknown.

## Proposed Fix
In mctl-telegram (Go), at the point(s) in the session pool where
`mctl_sessions_borrow_total{result="error"}` is incremented (see the metric
provenance note in mctl-telegram-slo.yaml: registered in
`internal/metrics/metrics.go`, incremented from the `Pool.Borrow()` error
path), add a structured log line at WARN or ERROR level carrying the
underlying error, the tenant/user identifier, and the session identifier if
available.

This does not assume (a) or (b) above is the true cause — it closes the gap
that caused this specific incident to be undiagnosable either way: the SLO
alert fired but left no log trail for a human or an automated skill to read.
It is a logging-only change: no change to pool sizing, timeouts, retry
behavior, or the alert/rule definitions themselves.

## Scope
Minimal. Touch only the `Pool.Borrow()` error-return path(s) in mctl-telegram
to add the log call. Do not change pool capacity, TTLs, retry logic, or
anything in platform-gitops/infra-components/observability/vm-rules/.

## Confidence: LOW
This responder could not confirm an actual defect, and could not rule out
that this was the "known property, not a bug" low-traffic false-positive the
SLO rule file itself documents. The proposed change is a safe, generically
useful diagnostic improvement rather than a fix for a confirmed root cause.
Before applying, the implementer should check whether `Pool.Borrow()` errors
are already logged elsewhere with adequate detail, and should feel free to
close this proposal without a code change if so.
