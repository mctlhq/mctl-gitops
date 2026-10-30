# Tasks: issue-860-fix-logs-a-failed-loki-query-is-returned

- [ ] 1. Add `minLogWindow` (1m), `maxLogWindow` (720h), `defaultLogLines` (100), `maxLogLines` (1000) and `defaultLogWindow` (1h) constants and strict parsing for `lines`/`since` in `GetServiceLogs` (`internal/api/handlers_read.go`) — DoD: a malformed or out-of-range value answers 400 with a message naming the range; an empty value uses the default; `QueryRange` is not called on 400.
- [ ] 2. Add `dnsLabelPattern` validation and the `requireRegisteredTenant` + `resolveWorkloadService` gates (from `internal/api/handlers_workload.go`) to `GetServiceLogs`, in the order auth → DNS → access → params → tenant → service → querier (depends on 1) — DoD: an unknown tenant or service answers 404; a failed lookup answers 503; nothing reaches Loki in either case.
- [ ] 3. Replace the nil-querier `200 []` with `writeError(w, 503, "log querying not configured")` (depends on 2) — DoD: no 200 is returned when `h.opts.LogQuerier == nil`.
- [ ] 4. Add `classifyLogQueryError` (timeout/deadline → 504 `timeout`; canceled → 503 `canceled`; other → 503 `unavailable`), and on `QueryRange` error call `slog.Warn("log query failed", team, app, error_class, error)` and then `writeError` with a fixed message (depends on 3) — DoD: the failure body has no `lines`/`count` and contains no Loki URL, LogQL or upstream body; one WARN line per failure.
- [ ] 5. Make the success body `{team, app, lines, count, limit, since}` with `lines` never `null`; drop `note` (depends on 4) — DoD: an empty Loki result serializes as `"lines": []`, `"count": 0`.
- [ ] 6. Update the `mctl_get_service_logs` description in `internal/mcp/server.go` and `/api/v1/logs/{team}/{app}` in `internal/openapi/openapi.yaml` (400/404/503/504, the `limit`/`since` fields, the meaning of `count: 0`); check `README.md:468` wording — DoD: the docs state that a failed read is an error and that `count: 0` means only that Loki answered empty. The MCP tool count is unchanged (no `server_test.go` change).
- [ ] 7. Update `e2e/e2e_test.go` logs test to accept 200 (asserting `count == len(lines)`) or skip on 503 `log querying not configured`, and fail on anything else (depends on 5) — DoD: the e2e test compiles and no longer treats `note` as success.
- [ ] 8. `go fmt`, `go vet`, `golangci-lint`, `go test ./...` — DoD: all clean.

## Tests

New `internal/api/handlers_logs_test.go`, reusing `workloadTenants`, `workloadArgo` and `serveUser` from `handlers_workload_test.go`, with a `stubLogQuerier{lines, err, calls}`:

- [ ] T1. Loki error (generic `errors.New("loki: HTTP 500: secret-body http://loki.internal")`) → 503, the body has an `error` key and no `lines`/`count`, and the body does not contain `loki.internal` or `secret-body`.
- [ ] T2. Loki timeout (`fmt.Errorf("loki: request failed: %w", context.DeadlineExceeded)`, and a `*url.Error` wrapping a timeout `net.Error`) → 504, no `lines`.
- [ ] T3. Nil `LogQuerier` → 503 `log querying not configured`.
- [ ] T4. Loki returns nil/empty → 200, `"lines": []` (not `null`), `count: 0`, `limit: 100`, `since: "1h0m0s"`.
- [ ] T5. Loki returns 2 lines with `lines=10&since=15m` → 200, `count: 2`, `limit: 10`, `since: "15m0s"`, and the stub received `lines=10, since=15m`.
- [ ] T6. Invalid params, table-driven: `lines=0`, `lines=1001`, `lines=abc`, `since=7d`, `since=-1h`, `since=30s`, `since=721h` → 400, stub calls == 0.
- [ ] T7. Unknown service → 404; gitops error → 503; unregistered tenant → 404; non-DNS team/app → 400; stub calls == 0 in each.
- [ ] T8. Through the support audit gate (`serveAudited`): a Loki error records audit status `failed` with `http_status` 503.
- [ ] T9. Revert check: with the handler change reverted (stash it), T1-T4 and T6 fail; record this in the PR description.

## Rollback

Revert the PR and redeploy the previous mctl-api image (the image tag in the gitops `mctl-api.yaml` bootstrap, or an ArgoCD rollback). There are no data, schema or config changes, so a revert fully restores the old `200` + `note` behavior.
