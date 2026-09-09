# Design: incident-776dd0cd

## Confidence: LOW

## Diagnosis
`MctlTelegramSessionBorrowSlowBurn` fires when
`mctl_telegram:session_borrow_errors:ratio_rate6h` (the share of
`mctl_sessions_borrow_total` results that are `result="error"`, excluding the
expected `expired_idle`/`expired_absolute` TTL outcomes) exceeds 6% over a
trailing 6h window — see
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`.
This is a metrics-only SLO burn-rate alert with no corresponding skill in
mctl-agent, which is why it escalated: "no skill matched ... the agent has no
diagnostic rule for this signal, so nothing was analysed."

Two root causes are plausible from the evidence available to this responder,
and it cannot distinguish between them:

1. A real, sustained elevation in `Pool.Borrow()` failures (e.g. expired or
   revoked MTProto sessions being hit before their TTL-exempt/expected paths
   apply, DB unavailability during borrow, or an MTProto-side issue such as
   `AUTH_KEY_DUPLICATED` for a shared identity — the values.yaml history for
   this service shows this has happened before, e.g. the canary/operator
   identity sharing note in `services/labs/mctl-telegram/values.yaml`).
2. The alert's own documented low-traffic caveat: the same VMRule file notes
   "on a low-traffic service a 1h window holds few invocations, so a couple of
   errors can cross a burn threshold" — a handful of ordinary borrow errors on
   a low-volume tenant could cross the 6% ratio without any systemic problem.

This responder has no PromQL/metrics query tool and could not pull the raw
`mctl_sessions_borrow_total{result="error"}` sample count or the identities
involved to tell these apart. The logs available via `mctl_get_service_logs`
for the full 6h alert window (768 lines, tenant=labs, service=mctl-telegram)
contain zero lines matching "session", "borrow", or "error"
(case-insensitive) and zero lines at level WARN/ERROR — every sampled line is
level=INFO. In other words: whatever is incrementing
`mctl_sessions_borrow_total{result="error"}`, it does so silently. That gap is
itself the actionable, low-risk finding: this class of incident cannot be
diagnosed — by mctl-agent, by a future skill, or by a human — without a log
line to correlate to the metric.

## Proposed Fix
Add a structured log line at the point(s) in mctl-telegram where
`mctl_sessions_borrow_total{result="error"}` is incremented (registered in
`internal/metrics/metrics.go` per the VMRule's provenance comment; the
increment call site itself is expected to live in the session pool package,
e.g. `internal/session/pool.go` or equivalent `Pool.Borrow()`
implementation — this responder does not have the mctl-telegram source tree
checked out to confirm the exact path, so the implementer should locate it by
searching for the `mctl_sessions_borrow_total` metric name or a `Borrow(`
method).

At the `result="error"` branch, log at WARN (or ERROR) level with at least:
- the underlying error / failure reason,
- the identity or session key involved (e.g. `tg_user_id`, matching the field
  name already used elsewhere in this service's logs),
- enough context to distinguish causes (auth-key error vs. DB error vs.
  timeout, etc.), without logging session secrets/tokens.

This is additive observability only — no change to `Pool.Borrow()` control
flow, retry behavior, or the SLO thresholds/rules themselves.

## Scope
Minimal. Only the error-logging call at the existing `result="error"` branch
of the session-borrow path. No behavior change, no alert-threshold change, no
other files touched.
