# Classify caller errors out of the tool-availability SLI and alert on an exhausted error budget

## Context

The MCP tool-availability SLI (`mctl_telegram:tool_errors:ratio_rate{1h,6h}` and
`mctl_telegram:tool_availability:ratio_rate28d` in mctl-gitops
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`)
counts every `mctl_tool_invocations_total{status="error"}` sample as
unavailability. `Server.audit` (`internal/mcp/tools.go`) sets `status="error"`
for any non-nil error, so a Telegram reply that refuses the caller's request
(`CHANNEL_INVALID`, `PEER_ID_INVALID`, `CHAT_ID_INVALID`, any other 400/403)
burns the 99.5% budget even though it proves the service works. On labs the
SLI read 99.02% over 4 days while every failure was a caller error and the
canary never failed. The same diagnosis was already accepted on 2026-09-07
(`incident-9dafe20c`) and #746 already applied it to the session-borrow SLI
(`borrowCallResult`, `internal/telegram/clientpool.go`).

Second, only 1h/6h burn-rate alerts exist. Nothing fires when a 28-day SLI is
below its objective, so the error-budget policy in `docs/slo.md` ("freeze
rollouts once the budget is spent") has no trigger. The session-borrow 28d
ratio sits at 92.83% against 99% and no alert surfaced it.

The classifier lands in this repo; recording rules, alerts, rule tests and
dashboards land in mctl-gitops.

## User stories

- AS an on-call engineer I WANT the tool-availability SLI to count only failures the service caused SO THAT a burn-rate alert means the service is degraded, not that a client passed a bad peer id.
- AS a service owner I WANT an alert when a 28-day SLI is below its objective SO THAT the error-budget policy in `docs/slo.md` is actually triggered.
- AS an operator reading dashboards I WANT caller errors to remain visible as their own series SO THAT a misbehaving client is still observable even though it no longer burns the budget.

## Acceptance criteria (EARS)

Classifier (mctl-telegram):

- WHEN a tool call staged through `Server.audit` fails with an MTProto error whose code is 400 or 403 (e.g. `CHANNEL_INVALID`, `PEER_ID_INVALID`, `CHAT_ID_INVALID`, `CHAT_ADMIN_REQUIRED`) THE SYSTEM SHALL increment `mctl_tool_invocations_total{status="caller_error"}` and not `status="error"`.
- WHEN a tool call fails with the "could not be accessed ... it is not in your dialog list" error built in `telegram.GetMessages`/`GetMessagesRaw` (`internal/telegram/messages.go`) THE SYSTEM SHALL classify it as `caller_error`, while keeping the error text returned to the client byte-identical to today.
- WHEN a staged error record is reconciled at flush with reason `invalid_argument` or `scope_denied` named by `hintReason` (or the deterministic `identity missing scope ` prefix) THE SYSTEM SHALL record `status="caller_error"` on `mctl_tool_invocations_total`.
- IF the error is a session-auth rejection (anything `sessionErrorFor` maps, or `db.ErrSessionUnauthorized/Revoked/Expired/ErrNoActiveSession`), a Telegram 5xx, a 420/FLOOD_WAIT after retries are exhausted, a transport failure, a context cancellation or deadline, `ErrPoolFull`, or any error that is not an MTProto reply and carries no caller-error hint THEN THE SYSTEM SHALL keep `status="error"`.
- WHILE a call succeeds THE SYSTEM SHALL keep recording `status="ok"` exactly as today.
- WHILE classifying THE SYSTEM SHALL use one shared predicate in `internal/telegram` for both `borrowCallResult` (session-borrow SLI) and the tool SLI, so the two SLIs cannot disagree on what a caller error is.
- THE SYSTEM SHALL leave the `audit_logs.status` column, the `mcp tool call` slog line's `status` attribute and the audit span attribute unchanged (`ok`/`error`); the slog line SHALL gain an `slo_status=caller_error` attribute only when the metric label is `caller_error`.
- WHILE a record is `synthesized` THE SYSTEM SHALL continue not to sample `mctl_tool_invocations_total` (existing `callRecord.feedsSLO` behaviour unchanged).
- THE SYSTEM SHALL update the `mctl_tool_invocations_total` HELP text to name the three values `ok`, `error`, `caller_error`.

Rules and alerts (mctl-gitops):

- WHEN computing `mctl_telegram:tool_errors:ratio_rate1h`, `..._rate6h` and `mctl_telegram:tool_availability:ratio_rate28d` THE SYSTEM SHALL use `status=~"ok|error"` as the denominator, so `caller_error` is excluded from both sides.
- WHEN computing `HighToolErrorRate` in `mctl-telegram-alerts.yaml` THE SYSTEM SHALL use the same `status=~"ok|error"` denominator.
- IF `mctl_telegram:tool_availability:ratio_rate28d < 0.995` for 1h THEN THE SYSTEM SHALL fire `MctlTelegramToolAvailabilityErrorBudgetExhausted` (severity `warning`).
- IF `mctl_telegram:oauth_availability:ratio_rate28d < 0.999` for 1h THEN THE SYSTEM SHALL fire `MctlTelegramOAuthAvailabilityErrorBudgetExhausted` (severity `warning`).
- IF `mctl_telegram:session_borrow_success:ratio_rate28d < 0.99` for 1h THEN THE SYSTEM SHALL fire `MctlTelegramSessionBorrowErrorBudgetExhausted` (severity `warning`).
- THE SYSTEM SHALL route the three budget alerts the same way as the SlowBurn alerts (fall through to the default `mctl-agent` receiver; no Alertmanager matcher change).
- THE SYSTEM SHALL carry vmalert-tool unit tests for each budget alert covering one firing and one non-firing case, and tests showing `caller_error` samples do not move the tool SLI ratios.

## Out of scope

- The shared-pg roll DB-connection failures in background jobs (no SLI covers them) — separate issue.
- Changing SLO objectives, burn multipliers or windows.
- Re-classifying the `audit_logs` table or `get_my_audit_log` / admin audit output.
- Classifying FLOOD_WAIT (420) at tool level as anything but `error` (see Open questions).
- Back-filling or rewriting historical `status="error"` samples; the 28d ratio converges on its own within 28 days.
- Deploying `deploy/alerts/mctl-telegram.rules.yaml` (it stays a non-deployed reference, updated only for consistency).

## Open questions

- 420 / FLOOD_WAIT that survives `borrowWithRetry`: the issue does not list it. This proposal keeps it `error` (conservative; the session-borrow SLI also excludes it only per attempt). Reviewer may prefer `caller_error`.
- Argument-validation and scope refusals in the labs log lines are mostly early returns that never reach `Server.audit`; they are already `synthesized` and already excluded from the metric. Only the audit-staged subset changes. So the measured improvement on labs will come mainly from the Telegram 400 replies; the reviewer should not expect all 31 errors to disappear.
- `for:` on the budget alerts: 1h is proposed (the 28d ratio moves slowly, so 1h is enough to suppress evaluation-boundary flapping without delaying the signal meaningfully). The issue only says "long enough".
- On rollout the session-borrow budget alert will fire immediately (92.83% < 99%) and likely stay firing until about 2026-11-03, and the tool-availability one may fire until old `error` samples age out. This is the intended signal, but the reviewer should decide whether to accept that or temporarily silence it in Alertmanager.
- The Telegram 403 class includes `CHAT_WRITE_FORBIDDEN`-style refusals and also any 403 Telegram might emit for a server-side reason; this proposal follows #746 and treats all 403 as caller error.
