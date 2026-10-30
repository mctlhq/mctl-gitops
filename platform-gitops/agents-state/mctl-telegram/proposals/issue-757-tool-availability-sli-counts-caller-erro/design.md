# Design: issue-757-tool-availability-sli-counts-caller-erro

## Current state

Metric emission (mctl-telegram):

- `internal/metrics/metrics.go` registers `mctl_tool_invocations_total{tool,status}`, HELP "status (ok or error)", and `mctl_tool_call_errors_total{tool,reason}`.
- `internal/mcp/tools.go` `Server.audit(ctx, id, tool, peer, err, startedAt, callPath...)` sets `status="error"` for any non-nil `err`, stores only `err.Error()` in `callRecord.errMsg`, and either stages the record into the `*callRecorder` (inside `Server.recordToolCall`) or writes it through `Server.writeAuditRow`. `auditDetached` wraps `audit`.
- `Server.writeAuditRow` writes the `audit_logs` row (`Store.LogToolCall(..., rec.status, ...)`), then, only if `rec.hasElapsed && rec.feedsSLO()`, observes `mctl_tool_invocation_duration_seconds` and increments `ToolInvocationsTotal.WithLabelValues(rec.tool, rec.status)`. It also emits the `mcp tool call` slog line with `status` and calls `setAuditSpanAttributes`.
- `internal/mcp/record.go`: `callRecord.synthesized` is set for every record created by `flushRecordedCall` (Rules 1-append, 2, 3) and by `Server.auditRefusal`. `feedsSLO()` returns `!synthesized`. So early-return refusals (`requireScope` failure, `"peer is required"`, `"peer and text are required"` in `tools.go:425,557`, `media_tools.go:407`, `apps.go:108`) already never reach the metric. What does reach it is every error passed to `Server.audit` — chiefly `borrowWithRetry` failures followed by `s.audit(..., err, ...)` and `borrowErrResult` (e.g. `get_messages`, `tools.go:~590`).
- Flush Rule 1 reconciles the last staged error's `reason` from `explicitReason` > `rec.snapshotHint()` (`hintReason`) > `classifyToolResultReason` (`internal/mcp/reasons.go`, text-based fallback).
- `borrowErrResult` hints `ReasonTelegramError` for session errors, `ErrPoolFull`, catalogued and uncatalogued MTProto errors.

Session-borrow classification (#746):

- `internal/telegram/clientpool.go` `borrowCallResult(err)`: `sessionErrorFor(err) != nil` -> `error`; not a `*tgerr.Error` -> `error`; code 420 or `PEER_FLOOD` -> `flood_wait`; code 400/403 -> `call_error`; else `error`.

Error-type gap:

- `internal/telegram/messages.go` (~line 615) converts a `PEER_ID_INVALID`/`CHANNEL_INVALID` reply in the direct-resolution fallback into `fmt.Errorf("peer %q could not be accessed (%s): it is not in your dialog list; call list_dialogs ...", peerSpec, rpcErr.Message)` — formatted with `%s`, so the `*tgerr.Error` is lost. Neither `borrowCallResult` nor any `errors.As` classifier can see it as a 400 today, which is why the issue's log lines show it as a plain error. Line ~586 (`ResolvePeerCached` failure) does wrap with `%w`.

Rules, alerts, dashboards (mctl-gitops):

- `vm-rules/mctl-telegram-slo.yaml`: `tool_errors:ratio_rate1h/6h` = `status="error"` / all statuses; `tool_availability:ratio_rate28d` = `status="ok"` / all statuses; `oauth_availability:ratio_rate28d`, `session_borrow_success:ratio_rate28d` (denominator `result=~"ok|error"`). Burn alerts group `mctl-telegram-slo-burn`, `for: 0m`, FastBurn critical / SlowBurn warning; SlowBurn falls through to the default `mctl-agent` receiver. No 28d-ratio alert exists.
- `vm-rules/mctl-telegram-alerts.yaml` `HighToolErrorRate`: `status="error"` / all statuses over 15m.
- `grafana-dashboards/mctl-telegram-overview-dashboard-configmap.yaml` uses `mctl_tool_invocations_total{status=...}` in 3 queries and the bare counter in 4.
- `grafana-dashboards/mctl-telegram-per-user-dashboard-configmap.yaml` reads Loki `mcp tool call` lines filtered on `status="error"` and a `status` variable `ok|error`; it does not read the metric.
- In this repo, `deploy/alerts/mctl-telegram.rules.yaml` (reference only, tested by `mctl-telegram.rules_test.yaml`) and `deploy/grafana/mctl-telegram-beta.json` use the same `status="error"` / bare-counter shapes. `docs/slo.md` defines the SLI as `status="ok"` / bare counter and describes the error-budget policy (section "Error-budget policy") without an alert to trigger it.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`, `image.tag: "0.79.3"` (so the #746 `borrowCallResult` fix is deployed); single replica, Recreate.
- `$MCTL_GITOPS_ROOT/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`, `mctl-telegram-alerts.yaml`, `tests/mctl-telegram-slo_test.yaml` (365 lines), `tests/mctl-telegram-alerts_test.yaml`: read, contents as summarized above.
- `$MCTL_GITOPS_ROOT/infra-components/observability/grafana-dashboards/mctl-telegram-{overview,per-user,login}-dashboard-configmap.yaml`: grepped for `mctl_tool_invocations_total` / `status`.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/observability/monitoring.yaml`: default route receiver `mctl-agent`, named matchers route to `telegram` — consistent with the SLO file's comment that SlowBurn falls through to default.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-telegram/proposals/incident-9dafe20c/tasks.md`: earlier accepted proposal, all tasks unchecked.
- Live metric values (99.02%, 92.83%) were not re-queried; no read-only metrics query tool was used in this run. The figures are taken from the issue.

## Proposed solution

### A. One shared caller-refusal predicate (`internal/telegram`)

Add to `internal/telegram/clientpool.go` (or a new `internal/telegram/callerror.go`):

```go
// ErrPeerNotAccessible marks a Telegram 400 peer refusal that a helper
// re-phrased for the caller (messages.go fallback).
var ErrPeerNotAccessible = errors.New("telegram: peer not accessible")

// IsCallerRefusal reports whether err is Telegram answering the request and
// refusing it as the caller's mistake (MTProto 400/403, excluding
// session-auth codes and PEER_FLOOD).
func IsCallerRefusal(err error) bool
```

Logic: `err == nil` -> false; `sessionErrorFor(err) != nil` -> false; `errors.Is(err, ErrPeerNotAccessible)` -> true; `errors.As(err, *tgerr.Error)` with `Message != "PEER_FLOOD"` and `Code` 400 or 403 -> true; otherwise false. Context errors, transport errors, `ErrPoolFull`, `db.ErrSession*` sentinels are not `*tgerr.Error` and fall through to false.

Refactor `borrowCallResult` to use it: flood check first (420 / `PEER_FLOOD` -> `flood_wait`), then `IsCallerRefusal` -> `call_error`, else `error`. Behaviour is unchanged for every existing input, and the peer-not-accessible case now also becomes `call_error` in the borrow SLI (consistent with #746's intent).

In `messages.go` replace the `%s` construction with a small unexported type that keeps `Error()` byte-identical and adds `Is(target) bool { return target == ErrPeerNotAccessible }`. It deliberately does NOT unwrap to the `*tgerr.Error`: that would let `borrowErrResult -> mtprotoErrResult` pick the catalog text and change the client-facing message, which is the actionable "call list_dialogs" guidance today.

### B. A third metric status on the tool SLI only (`internal/mcp`)

- Add `const statusCallerError = "caller_error"` and a field `sloStatus string` on `callRecord` (empty means "same as `status`").
- `Server.audit`: when `err != nil && telegram.IsCallerRefusal(err)`, set `rec.sloStatus = statusCallerError`. `status` stays `"error"`.
- `flushRecordedCall` Rule 1 reconcile branch (handler-staged error): after `reason` is resolved, if `last.sloStatus == ""` and the reason came from `explicitReason`/`hintReason` (not the text fallback) and is `ReasonInvalidArgument` or `ReasonScopeDenied`, or `last.errMsg` has the deterministic `identity missing scope ` prefix, set `last.sloStatus = statusCallerError`. `ReasonHandlerError` / `ReasonPanic` never become caller errors. The text-based `classifyToolResultReason` fallback is not trusted for this, so a server fault whose message happens to contain "must be" cannot leave the SLI.
- `writeAuditRow`: the metric uses `rec.metricStatus()` (= `sloStatus` if set, else `status`). `LogToolCall`, slog `status` and `setAuditSpanAttributes` keep `rec.status`. The slog line gets `slo_status=caller_error` when applicable, so Loki can still separate the classes without breaking the per-user dashboard's `status="error"` filter.
- `metrics.go`: HELP becomes "status (ok, error, or caller_error; caller_error is a request Telegram or argument/scope validation refused as the caller's mistake and is excluded from the availability SLI)".
- `mctl_tool_call_errors_total` is untouched: caller errors still count there by reason.

Why the metric only: `audit_logs.status` is user-visible (`get_my_audit_log`, admin audit lookups) and is the Loki dashboard's filter; changing it widens the blast radius without helping the SLI.

### C. Rules, alerts, tests, dashboards (mctl-gitops)

- `mctl-telegram-slo.yaml`: denominators of `tool_errors:ratio_rate1h/6h` and `tool_availability:ratio_rate28d` (including the `0 *` fill) become `mctl_tool_invocations_total{status=~"ok|error"}`. Update the header's metric provenance line to `"ok"|"error"|"caller_error"`.
- New group `mctl-telegram-slo-budget` (interval 1m) with three alerts:
  - `MctlTelegramToolAvailabilityErrorBudgetExhausted`: `mctl_telegram:tool_availability:ratio_rate28d < 0.995`
  - `MctlTelegramOAuthAvailabilityErrorBudgetExhausted`: `mctl_telegram:oauth_availability:ratio_rate28d < 0.999`
  - `MctlTelegramSessionBorrowErrorBudgetExhausted`: `mctl_telegram:session_borrow_success:ratio_rate28d < 0.99`
  - each `for: 1h`, labels `severity: warning`, `service: mctl-telegram`; description names the ratio, the objective, and the `docs/slo.md` error-budget policy (freeze non-reliability rollouts). Not added to the telegram receiver matchers, so they route like SlowBurn (default `mctl-agent`).
- `mctl-telegram-alerts.yaml` `HighToolErrorRate`: denominator `status=~"ok|error"`.
- `tests/mctl-telegram-slo_test.yaml`: add series with `status="caller_error"` and assert the 1h/6h/28d ratios are identical to the same scenario without them; firing and non-firing cases for each of the three budget alerts (e.g. 28d ratio 0.98 for >1h fires; 0.999 does not; a dip shorter than `for:` does not). `tests/mctl-telegram-alerts_test.yaml`: one `HighToolErrorRate` case where caller errors alone exceed 10% and it does not fire.
- Overview dashboard: switch the availability/error-rate panels' denominators to `status=~"ok|error"`, add a `caller_error` series to the per-status panel. Per-user dashboard: no change needed (reads Loki `status`, which is unchanged); optionally add `slo_status` to its line format.

### D. Docs and reference files (this repo)

- `docs/slo.md`: SLI definition uses `status=~"ok|error"` denominator and explains `caller_error` (mirroring the session-borrow `call_error` text); add an "Error-budget alerts" subsection naming the three alerts and threshold/`for:`.
- `deploy/alerts/mctl-telegram.rules.yaml` + `mctl-telegram.rules_test.yaml` and `deploy/grafana/mctl-telegram-beta.json`: same denominator change, so the reference does not drift from the deployed form (`runbook_links_test.go` / any doc tests must keep passing; new alerts need runbook anchors if that test requires them).

### Rollout order

Owner decision 2026-10-12: the `mctl-telegram-slo-budget` group is a second mctl-gitops PR, merged no earlier than 2026-11-03 once each 28d ratio is checked against its objective (requirements.md, Decisions). The rest of section C ships first.


Either order is safe: rules with `status=~"ok|error"` are identical to today while no `caller_error` series exists, and a released binary emitting `caller_error` under old rules simply moves those calls out of the numerator but keeps them in the denominator (SLI slightly optimistic until the rule change lands). Preferred: mctl-gitops rules first, then release mctl-telegram.

## Alternatives

1. Reclassify in PromQL only, from `mctl_tool_call_errors_total{reason}`. Dropped: `reason` is `telegram_error` for both a 400 refusal and a 5xx/uncatalogued MTProto failure, so the rule cannot separate them; and that counter is per call, not aligned with `mctl_tool_invocations_total`.
2. Mark caller errors `synthesized` (reuse `feedsSLO`) so they are not sampled at all. Dropped: they would vanish from `mctl_tool_invocations_total` and its duration histogram entirely, losing visibility of a client looping on bad peers; a separate label value keeps them observable.
3. Change `audit_logs.status` / the slog `status` to `caller_error` too. Dropped: user-visible audit output changes, the per-user Loki dashboard's `status="error"` and `ok|error` variable would silently miss rows, and the SLI gains nothing from it.
4. Unwrap the messages.go error to the original `*tgerr.Error`. Dropped: `borrowErrResult` would then render the catalog message and lose the "call list_dialogs" guidance clients rely on.

## Platform impact

- No DB migration; no schema change. New label value on an existing counter: cardinality grows by at most one series per tool (~90).
- Backward compatibility: consumers summing the bare counter still see total volume; consumers selecting `status="error"` see fewer errors (intended). The overview dashboard and `HighToolErrorRate` are updated in the same mctl-gitops PR.
- Alert noise risk: the session-borrow budget alert will fire on deploy (92.83% < 99%) and is expected to clear about 2026-11-03; the tool-availability one may fire until pre-change errors age out of the 28d window. Mitigation: `warning` severity, default receiver, documented in the PR; reviewer may add a time-bounded silence.
- Risk of hiding real faults: limited to MTProto 400/403 and hinted validation/scope refusals; 5xx, 420, transport, context and session-auth stay `error`. A unit test pins each class and fails if the classifier is reverted.
- Resource impact: negligible (one `errors.As` per failing call).
