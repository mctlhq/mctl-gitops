# Design: incident-2430bb39

## Diagnosis
MctlTelegramSessionBorrowSlowBurn fires on
`mctl_telegram:session_borrow_errors:ratio_rate6h`
(`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`),
defined as `Pool.Borrow()` errors over 6h divided by `ok`+`error` borrows —
`expired_idle` and `expired_absolute` results are deliberately excluded from
both numerator and denominator, because those are expected user-side TTL
expirations, not service failures. The rule fired because that ratio exceeded
6.0% (6x the 99% session-borrow-success objective's error budget) sustained
over the full 6h window ending around 2026-09-23T12:37Z.

mctl-agent escalated this ticket with no diagnosis (`type=generic`,
`analysis` says no skill matches `MctlTelegramSessionBorrowSlowBurn`), so no
prior investigation exists to build on.

This responder cannot see `mctl_sessions_borrow_total` directly — it has no
metrics-query tool, only `mctl_get_service_logs` (Loki) — so the log evidence
in requirements.md is a proxy. That proxy is materially incomplete: the tool
call that returns the full 6h window exceeds the response size cap this
responder is bounded by (confirmed at 200, 100, and 90 lines-since-6h; only
a ~44-minute slice at the end of the window was retrievable). Within that
slice, everything is healthy: no error-status tool calls, no WARN/ERROR log
lines, and the two "idle telegram client, closing" events are routine pool
evictions (which, per the SLI definition, are not even in the `error` bucket
unless the subsequent borrow attempt itself failed — nothing in the retrieved
logs suggests that happened).

Because the burn window is 6h and the observed slice covers roughly the
final 12% of it, this responder cannot rule in or out a real, sustained
elevated borrow-error rate earlier in the window (e.g. a `TelegramClientErrors`
episode, a Telegram-side outage, or flood-wait pressure that later cleared).
Nor can it identify a root cause with the evidence available. No config
defect in `platform-gitops/services/labs/mctl-telegram/values.yaml` stands
out as an obvious cause: `resources.limits.cpu` (1000m) and the documented
history in that file's comments address MTProto-handshake CPU cost for
login/SendCode specifically, not steady-state session borrowing, and there is
no session-pool-specific tunable (idle timeout, pool size cap —
`TELEGRAM_MAX_SESSIONS` is unset/uncapped per the ops VMRule comments) in
that file to point at without stronger evidence that either is implicated.

## Proposed Fix
No alerting-rule or service-config change is proposed. Per
`mctl-telegram-slo.yaml`'s own header comment, burn-rate thresholds are
sourced from `docs/slo.md`'s objective/budget table and are not to be tuned
without observed-traffic data this responder does not have — the same
constraint the previous `mctl-telegram` SLO-burn proposal
(`incident-a2c2e080`) already documented and respected for a different alert
in the same VMRule file.

Instead, add a short runbook entry so the next occurrence of this alert —
whether investigated by a human or by this responder again — starts from a
documented triage path instead of re-discovering both the SLI definition and
this log-tooling limitation from scratch.

New file: `docs/runbooks/mctl-telegram-session-borrow-slow-burn.md`

Contents:
- Names the alert (`MctlTelegramSessionBorrowSlowBurn`) and links to
  `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
  and `mctl-telegram`'s `docs/slo.md`.
- States the SLI precisely: `mctl_sessions_borrow_total{result="error"}` vs.
  `result=~"ok|error"` over 6h, with `expired_idle`/`expired_absolute`
  explicitly excluded as expected TTL behavior, not failures.
- Documents the correct triage path: query
  `mctl_sessions_borrow_total` by `result` in VictoriaMetrics/Grafana over
  the alert window to see which result values actually moved, rather than
  reading `mctl-telegram` logs first — the base-service "mcp tool call" log
  line only reports the outer tool-call outcome, not `Pool.Borrow()`'s
  result, so a healthy-looking log slice does not confirm a healthy borrow
  ratio.
- Records the log-tooling limitation found here: `mctl_get_service_logs`
  over a 6h window exceeds this responder's/operator's output size limit
  well before 100 lines, so a full-window log pull needs a smaller `since`
  value fetched in multiple passes, or direct Loki/Grafana access, not a
  single call.
- Notes as out-of-scope follow-up: if metrics access confirms a real,
  sustained `result="error"` rate (as opposed to `expired_idle`/
  `expired_absolute` noise or a metrics-only artifact), the next step is
  correlating the error timestamps against `TelegramClientErrors`
  (`mctl_telegram_client_errors_total`) and Telegram flood-wait events
  (`mctl_telegram_flood_wait_events_total`) — both already alerted on in
  `mctl-telegram-ops.yaml` — before considering any pool-sizing or
  resource-limit change to `values.yaml`.

## Scope
Minimal. Adds one new documentation file. No alerting rule, SLO objective,
or service configuration is modified.
