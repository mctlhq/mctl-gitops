# Tasks: issue-757-tool-availability-sli-counts-caller-erro

mctl-telegram (this repo):

- [ ] 1. Add `telegram.ErrPeerNotAccessible` and `telegram.IsCallerRefusal(err error) bool` in `internal/telegram` (session-auth codes via `sessionErrorFor` -> false; `PEER_FLOOD` -> false; `*tgerr.Error` code 400/403 -> true; `ErrPeerNotAccessible` -> true; everything else false). Refactor `borrowCallResult` to use it without changing any existing outcome. — DoD: existing `borrowCallResult` tests pass unchanged; godoc explains the shared contract.
- [ ] 2. (depends on 1) In `internal/telegram/messages.go`, replace the `%s`-formatted "could not be accessed ... not in your dialog list" error with an unexported error type whose `Error()` text is byte-identical and whose `Is` matches `ErrPeerNotAccessible` (it must not unwrap to the `*tgerr.Error`). — DoD: existing messages tests pass; new test asserts identical text and `errors.Is(err, ErrPeerNotAccessible)`.
- [ ] 3. (depends on 1) In `internal/mcp`: add `statusCallerError = "caller_error"`, `callRecord.sloStatus` and `metricStatus()`; set `sloStatus` in `Server.audit` when `telegram.IsCallerRefusal(err)`; in `flushRecordedCall` Rule 1 reconcile set it when the reason came from `explicitReason`/`hintReason` and is `ReasonInvalidArgument` or `ReasonScopeDenied`, or the message starts with `identity missing scope `. — DoD: `writeAuditRow` uses `metricStatus()` only for `ToolInvocationsTotal`; `LogToolCall`, slog `status`, span attributes unchanged; slog gains `slo_status` when set; `feedsSLO` unchanged.
- [ ] 4. Update the `mctl_tool_invocations_total` HELP in `internal/metrics/metrics.go`. — DoD: HELP names `ok`, `error`, `caller_error`.
- [ ] 5. Update `docs/slo.md` (SLI denominator `status=~"ok|error"`, `caller_error` definition, new "Error-budget alerts" subsection), `deploy/alerts/mctl-telegram.rules.yaml` + `deploy/alerts/mctl-telegram.rules_test.yaml`, and `deploy/grafana/mctl-telegram-beta.json` to the same shapes as task 7/8. — DoD: `go test ./docs/... ./deploy/...` (runbook-link tests) and promtool on the reference rules pass.
- [ ] 6. `go fmt`, `go vet`, `golangci-lint`, `go test ./...`; conventional commit `fix(metrics): classify caller errors out of the tool-availability SLI`; merge-commit PR; release via release-please. — DoD: green CI, released tag deployed to labs (`services/labs/mctl-telegram/values.yaml` image tag bumped by the release flow).

mctl-gitops (`platform-gitops/infra-components/observability/`):

- [ ] 7a. `vm-rules/mctl-telegram-slo.yaml`: denominators of `mctl_telegram:tool_errors:ratio_rate1h`, `..._rate6h`, `mctl_telegram:tool_availability:ratio_rate28d` (and their `0 *` fills) -> `status=~"ok|error"`; header provenance lists `caller_error`. Ships in the first mctl-gitops PR together with tasks 8 and 9. — DoD: vmalert-tool unittest passes.
- [ ] 7b. **Separate mctl-gitops PR, opened as a draft, merge no earlier than 2026-11-03** (see requirements.md, Decisions). Add group `mctl-telegram-slo-budget` with `MctlTelegramToolAvailabilityErrorBudgetExhausted` (< 0.995), `MctlTelegramOAuthAvailabilityErrorBudgetExhausted` (< 0.999), `MctlTelegramSessionBorrowErrorBudgetExhausted` (< 0.99), each `for: 1h`, `severity: warning`, `service: mctl-telegram`, description linking `docs/slo.md` error-budget policy. Do not add them to the telegram receiver matchers. — DoD: vmalert-tool unittest passes.
- [ ] 8. `vm-rules/mctl-telegram-alerts.yaml` `HighToolErrorRate`: denominator `status=~"ok|error"`. — DoD: alerts tests pass.
- [ ] 9. `grafana-dashboards/mctl-telegram-overview-dashboard-configmap.yaml`: availability/error-rate denominators -> `status=~"ok|error"`, add a `caller_error` series. Verify `mctl-telegram-per-user-dashboard-configmap.yaml` needs no change (reads Loki `status`, unchanged). — DoD: dashboard JSON valid; panels render on labs.

## Tests

- [ ] T1. `internal/telegram`: table test for `IsCallerRefusal`: `tgerr.New(400,"CHANNEL_INVALID")`, `PEER_ID_INVALID`, `CHAT_ID_INVALID`, 403 `CHAT_WRITE_FORBIDDEN`, wrapped `%w` variants and `ErrPeerNotAccessible` -> true; 500 `INTERNAL`, 420 `FLOOD_WAIT_5`, 400 `PEER_FLOOD`, a session-auth code from `revokedSessionCodes`/`unfinishedSessionCodes`, `context.Canceled`, `context.DeadlineExceeded`, `io.ErrUnexpectedEOF`, `ErrPoolFull`, `errors.New("x")` -> false.
- [ ] T2. `internal/mcp` (`record_test.go`): with a test metrics registry, a handler that calls `s.audit` with a 400 `CHANNEL_INVALID` / `PEER_ID_INVALID` error and one with the messages.go peer-not-accessible error increment `mctl_tool_invocations_total{status="caller_error"}` and leave `status="error"` at 0; a 5xx tgerr and a transport error increment `status="error"`; a staged error with `hintReason(ReasonInvalidArgument)` and one with `ReasonScopeDenied` become `caller_error`; a staged error whose reason comes only from the text fallback stays `error`; `audit_logs` row status is `"error"` in every failing case. Verify the test fails when task 3's classification is reverted.
- [ ] T3. `internal/telegram` `borrowCallResult` tests: all existing cases unchanged; peer-not-accessible now `call_error`.
- [ ] T4. mctl-gitops `tests/mctl-telegram-slo_test.yaml`: adding `caller_error` series leaves the three tool ratios unchanged (PR with 7a); each budget alert (PR with 7b) fires when the 28d ratio is below target for longer than 1h, does not fire above target, and does not fire for a dip shorter than `for:`.
- [ ] T5. mctl-gitops `tests/mctl-telegram-alerts_test.yaml`: `HighToolErrorRate` does not fire when only `caller_error` exceeds 10%, still fires on `error` above 10%.
- [ ] T6. Repo reference rules test (`deploy/alerts/mctl-telegram.rules_test.yaml`) updated for the new denominators.

## Rollback

- mctl-telegram: revert the PR and release (or roll labs back with `mctl_rollback_service` to `0.79.3`). Without the classifier no `caller_error` series is emitted; the `status=~"ok|error"` rules then behave exactly as before.
- mctl-gitops: revert the rules/dashboard PR; ArgoCD restores the previous VMRule. If only the budget alerts are noisy, revert just the `mctl-telegram-slo-budget` group or silence it in Alertmanager; the SLI change can stay.
- No data migration to undo; existing `caller_error` series age out of retention.
