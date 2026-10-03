# Design: incident-e674947b

## Confidence: LOW

## Diagnosis
The alert is the `MctlTelegramSessionBorrowSlowBurn` SLO burn-rate rule
(`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`):
`mctl_telegram:session_borrow_errors:ratio_rate6h > 0.060`, i.e. `Pool.Borrow()`
calls against `mctl_sessions_borrow_total` are failing with `result="error"`
(explicitly excluding the expected `expired_idle`/`expired_absolute` TTL
outcomes) at more than 6x the 99% session-borrow-success objective's error
budget, sustained over 6 hours. No skill in mctl-agent has a diagnostic rule
for this signal (per the incident's `analysis` field), which is why it
escalated instead of auto-resolving.

The service's own logs contain no ERROR/WARN lines and no mention of
"borrow" or "duplicate" anywhere in the sampled 6h window, so the error is
not currently visible outside the metric itself — `Pool.Borrow()` evidently
does not log its failure reason today, only increments the counter. That is
itself worth fixing regardless of the root cause (see Proposed Fix).

The leading hypothesis for the underlying cause, based on evidence already
recorded in this repo rather than on live telemetry this responder can query,
is MTProto session contention from a Telegram account that is logged into
BOTH the stable and preview deployments simultaneously. This is documented,
as a live/current fact (not a historical incident), in
`platform-gitops/services/labs/mctl-telegram/values.yaml`, in the canary
CronJob comment block:

  "Do not point this probe at operator 210408407: that personal account is
  also logged into preview MCP, and sharing one MTProto user across
  prod+preview causes AUTH_KEY_DUPLICATED. It had in fact been running as
  210408407 until this change ... and both databases confirm 210408407 is
  active on stable and preview simultaneously."

Telegram's MTProto protocol invalidates one side of a duplicated auth key
under concurrent use (AUTH_KEY_DUPLICATED), forcing that side to
disconnect and reconnect before it can serve requests again — exactly the
shape of a `Pool.Borrow()` error that is not a TTL expiration. The log
snippet in requirements.md shows the stable base-service and the preview
base-service both actively serving MCP tool calls in the same minutes
(15:04-15:10 UTC), which is consistent with (but does not prove) ongoing
dual-session use.

This diagnosis is NOT independently confirmed against
`mctl_sessions_borrow_total` or Telegram-side error codes — this responder
has no metrics-query tool and no shell, only `mctl_get_service_logs`, which
does not carry that detail. The implementer should verify against
VictoriaMetrics (or add the logging in the Proposed Fix first, then
re-observe) before assuming the AUTH_KEY_DUPLICATED hypothesis is confirmed.

## Proposed Fix
Two independent, low-risk changes, either of which can land on its own:

1. **Observability (do this first, low risk):** In mctl-telegram's session
   pool code (`internal/...`, wherever `Pool.Borrow()` increments
   `mctl_sessions_borrow_total{result="error"}` — see
   `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
   lines 35-36 for the metric's registration site,
   `internal/metrics/metrics.go`), add a WARN-level log line on every
   `result="error"` outcome that includes the `tg_user_id`/account id and the
   underlying error (in particular, whether it was `AUTH_KEY_DUPLICATED`).
   This turns the next occurrence of this alert into something diagnosable
   from `mctl_get_service_logs` directly, instead of requiring a human (or
   this responder) to reason from gitops comments.

2. **Root-cause mitigation (needs human confirmation of the hypothesis
   first):** If WARN logs from (1), or a direct VictoriaMetrics query,
   confirm `AUTH_KEY_DUPLICATED` as the error, the fix is to stop the same
   Telegram account (210408407) from holding concurrent MTProto sessions on
   both `tg.mctl.ai` (stable) and `tg-preview.mctl.ai` (preview). That is an
   application-level session-exclusivity decision (e.g. refuse/evict a login
   on one deployment when the same account already holds a session on the
   other), not a Helm values change, so it is out of scope for a
   config-only fix and is left to the implementer/owner to design once (1)
   confirms the cause.

## Scope
Minimal for this proposal: add the WARN-level error-reason log line at the
`Pool.Borrow()` error path only. Do not change pool sizing, `TELEGRAM_MAX_SESSIONS`,
or session-exclusivity behavior — `mctl-telegram-ops.yaml` already documents
that `TELEGRAM_MAX_SESSIONS` is unset/uncapped (pool capacity reads -1) and
capacity is not implicated in this SLI. The dual-session/AUTH_KEY_DUPLICATED
mitigation in item 2 is documented above as a follow-up, not part of this
proposal's tasks, since it requires confirmation this responder cannot
obtain.
