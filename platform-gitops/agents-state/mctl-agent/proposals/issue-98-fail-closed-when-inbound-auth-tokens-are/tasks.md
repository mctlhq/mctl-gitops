# Tasks: issue-98-fail-closed-when-inbound-auth-tokens-are

- [ ] 1. Flip `requireBearer` and `requireBearerFunc` in
      `internal/api/auth.go` to fail closed: remove their
      `if token == "" { return next }` short-circuits so both always run the
      `secretEqual` check (which already returns `false` when `want == ""`).
      Update the `requireBearer` doc comment (auth.go:29-31) to describe the
      new fail-closed contract instead of the old fail-open rationale. — DoD:
      `go build ./...` passes; no call site changes needed in `router.go`;
      `secretEqual`'s `want == ""` branch (auth.go:20-22) is now reachable
      and covered by a test (see task 5).
- [ ] 2. Flip `telegramSecretOK` in `internal/api/auth.go` to fail closed:
      remove `if secret == "" { return true }` so an empty
      `TELEGRAM_WEBHOOK_SECRET` always fails the header comparison. — DoD:
      `go build ./...` passes; behavior change is exercised by the updated
      Telegram tests in task 4.
- [ ] 3. (depends on 2) In `telegramWebhookHandler`
      (`internal/api/router.go:196-206`), change the command-execution gate
      from "exactly one of {secret set, chat allowlist set}" (XOR mismatch)
      to "both secret set AND chat allowlist set", so a fully-unconfigured
      Telegram integration no longer executes commands. Keep
      `w.WriteHeader(http.StatusOK)` unchanged in the rejection path — the
      Telegram Bot API delivery contract (always ack 200) must not change.
      Update the surrounding comment to describe the new tri-state (both
      set = execute; anything else = log + no-op + 200). — DoD: unauthorized
      or unconfigured Telegram requests never reach `handleTelegramCommand`;
      `TestTelegramFailClosedWithoutChatAllowlist` and
      `TestTelegramFailClosedWithoutWebhookSecret` still pass unchanged.
      NOTE: only do this task if the reviewer confirms the Open Questions
      interpretation in requirements.md; otherwise skip it and drop it from
      task 4's scope.
- [ ] 4. (depends on 1, 2, 3) Update `internal/api/auth_test.go`:
      - Change `TestTelegramOpenModeWhenFullyUnconfigured` to assert
        `pipe.IsPaused() == false` (command does not execute) and rename it
        (e.g. `TestTelegramFailsClosedWhenFullyUnconfigured`) to match — only
        if task 3 was done; otherwise leave as-is.
      — DoD: `go test ./internal/api/...` passes with the renamed/updated
      assertions reflecting the new fail-closed default.
- [ ] 5. (depends on 1) Add regression tests in `internal/api/auth_test.go`,
      table-driven per this repo's stated testing convention (`CLAUDE.md`:
      "Table-driven tests for skill match/diagnose", extended here to auth),
      covering: `POST /api/v1/alerts`, `POST /api/v1/skills/register`,
      `POST /mcp`, `GET /api/v1/tickets`, `GET /api/v1/skills`,
      `GET /api/v1/webhooks` each returning 401 when their governing token
      (`AlertWebhookToken` or `APIToken`) is left empty in `Options` — i.e.
      a router built with zero-value `Options{}` (beyond the minimum needed
      to construct it) must 401 every one of these routes. — DoD: new
      test(s) fail against pre-task-1 code and pass after; `go test
      ./internal/api/...` green.
- [ ] 6. (depends on 1) Fix the now-broken fail-open assumptions in
      `internal/api/router_test.go`: `TestTicketListEndpoint`,
      `TestTicketListEndpointFilters`, `TestSkillListEndpoint`,
      `TestRemoteSkillEndpoints`, `TestMCPEndpoint` — add `APIToken:
      "test-token"` to their `Options` and attach `Authorization: Bearer
      test-token` to every request so these tests keep verifying handler
      behavior (listing, filtering, MCP dispatch) rather than accidentally
      testing auth. — DoD: `go test ./internal/api/...` green; diff shows
      only the token/header additions, no assertion logic changed.
- [ ] 7. (depends on 1) Fix `internal/api/webhook_handlers_test.go`:
      `newWebhookEnabledRouter` / `TestWebhookRegisterListDelete` — same
      treatment as task 6 (add `APIToken` + bearer header). Leave
      `webhook_integration_test.go` and `router_metrics_test.go` untouched
      — confirmed during investigation that they only exercise
      `/api/v1/tickets/{id}/external-*` (separate HMAC/bearer, not
      `APIToken`) and `/metrics` (public), neither of which is affected by
      this change. — DoD: `go test ./internal/api/...` green.
- [ ] 8. Add a startup misconfiguration warning in `cmd/agent/main.go`,
      before the existing `slog.Info("mctl-agent starting", ...)` block
      (main.go:197-206): for each of `cfg.AgentAPIToken`,
      `cfg.AlertWebhookToken`, `cfg.TelegramWebhookSecret` that is empty,
      emit `slog.Warn("inbound auth token not configured; affected routes
      will reject all requests", "variable", "<ENV_VAR_NAME>")` naming the
      exact env var (`AGENT_API_TOKEN`, `ALERTMANAGER_WEBHOOK_TOKEN`,
      `TELEGRAM_WEBHOOK_SECRET` respectively). — DoD: running the binary
      with no token env vars set produces three distinct `WARN` lines on
      boot; `go build ./cmd/agent` passes; existing
      `api_auth`/`telegram_webhook_auth`/`alert_webhook_auth` booleans in
      the `"mctl-agent starting"` Info log are left in place (this is an
      addition, not a replacement).
- [ ] 9. (depends on 1-8) Run `go fmt ./...` and `go vet ./...` across the
      repo to match `CLAUDE.md` conventions. — DoD: no diffs from `go fmt`,
      no findings from `go vet`.

## Tests
- [ ] T1. `go test ./internal/api/...` — all existing and new tests pass,
      including the updated fail-closed assertions.
- [ ] T2. New regression test (task 5) proves 401 on `/api/v1/alerts`,
      `/api/v1/skills/register`, and `/mcp` when their token is unset —
      the three routes named explicitly in the issue's "Expected fix".
- [ ] T3. `TestControlPlaneRequiresBearerWhenConfigured`,
      `TestAlertWebhookRequiresBearerWhenConfigured`,
      `TestWebhookCRUDRequiresBearerWhenConfigured`,
      `TestMCPRequiresBearerWhenConfigured` (existing, `auth_test.go`) still
      pass unchanged — they cover the "token set, valid/invalid bearer"
      half of the acceptance criteria and were already correct before this
      change.
- [ ] T4. `TestHealthEndpoints` (existing, `router_test.go`) still passes
      unchanged — proves `/healthz`/`/readyz` remain public.
- [ ] T5. `go build ./...` for the full module succeeds.

## Rollback
This is a pure application-code change (no migrations, no data written, no
GitOps manifest schema change). If the fail-closed behavior turns out to
have been shipped against an environment where a token was unintentionally
left unset:
1. Fastest mitigation: set the missing token (`AGENT_API_TOKEN`,
   `ALERTMANAGER_WEBHOOK_TOKEN`, or `TELEGRAM_WEBHOOK_SECRET`) in that
   environment's Vault entry and let the existing ExternalSecret/ConfigMap
   sync pick it up — this restores access without reverting any code and is
   the intended remediation path, not a rollback.
2. If a full code rollback is needed, use `mctl_rollback_service` with
   `team_name=<owning team>`, `component_name=mctl-agent`, and
   `target_tag=<previous image tag>` (found via `mctl_get_service_config`)
   to redeploy the pre-change image through GitOps/ArgoCD. This reverts to
   the fail-open behavior this proposal exists to remove, so it should only
   be used as a short-term unblock while the correct token is provisioned,
   not left in place.
3. No database or schema changes were made, so no data migration rollback
   is needed either way.
