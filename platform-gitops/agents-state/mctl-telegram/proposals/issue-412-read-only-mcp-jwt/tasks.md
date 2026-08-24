# Tasks: issue-412-read-only-mcp-jwt

- [ ] 1. Create `internal/workertoken` package with `allowedReadOnlyScopes`,
      `defaultWorkerTokenTTL` (30 days), `maxWorkerTokenTTL` (90 days), the
      `mintWorkerTokenRequest`/`workerTokenResponse` types, and
      `NewHandler(secret []byte, issuer string) http.HandlerFunc` — DoD: package
      compiles, handler mints a `localjwt` token with `Audience: []string{"mcp-worker-ro"}`
      when called with a valid admin identity and a `telegram_id`, following the
      structure of `internal/agentapi/tokenhandler.go`.
- [ ] 2. Implement scope validation in the handler: default to
      `allowedReadOnlyScopes` when `Scopes` is omitted; reject the request with
      HTTP 400 and mint nothing if any requested scope is not a member of
      `allowedReadOnlyScopes` (depends on 1) — DoD: a request with
      `scopes: ["telegram:messages:send"]` returns 400 and no token is
      generated (verify via a code path test, not just log inspection).
- [ ] 3. Implement `admin:users` scope gate and `telegram_id > 0` validation,
      matching `NewAgentTokenHandler`'s existing checks exactly (403 for missing
      admin scope, 400 for missing/invalid `telegram_id`) (depends on 1) —
      DoD: unauthenticated and non-admin identities get 401/403 respectively;
      `telegram_id: 0` or negative gets 400.
- [ ] 4. Implement `ttl_hours` handling: default `defaultWorkerTokenTTL` when
      absent, clamp to `maxWorkerTokenTTL` when the requested value exceeds it,
      matching `NewAgentTokenHandler`'s clamp behavior exactly (depends on 1) —
      DoD: `ttl_hours: 100000` mints a token expiring at `now + 90d`, not
      `now + 100000h`.
- [ ] 5. Add the `slog.Info("worker token minted", ...)` log line with
      `admin_user_id`, `target_tg_id`, `scopes`, `ttl` fields on success, and
      `slog.Error` on signer/mint failure, matching the existing
      `agent token minted` / `bridge token minted` log shapes (depends on 1) —
      DoD: log line present and field names match the pattern grep'd from
      `internal/agentapi/tokenhandler.go` and `internal/bridge/tokenhandler.go`.
- [ ] 6. Mount `POST /api/mcp/worker-token` in `cmd/server/main.go` next to the
      existing `/api/agent/token` / `/api/bridge/token` registrations, gated on
      `cfg.OAUTHJWTSecret != ""`, using `auth.Middleware(provider, true, m,
      resourceMeta)` (the same plain MCP provider `/mcp` uses — not
      `selectAgentProvider`/`selectBridgeProvider`) and `selectAgentIssuer(cfg)`
      for the issuer string (depends on 1-5) — DoD: route registered only when
      the secret is configured; a token minted through it authenticates
      successfully at `/mcp` in local-jwt mode.
- [ ] 7. Add a doc comment on the new handler documenting the `aud:
      "mcp-worker-ro"` choice and the "must stay in lockstep" note about
      `OAUTH_JWT_AUDIENCE`, following the style of the existing comments on
      `selectBridgeIssuer`/`selectAgentIssuer` (depends on 6) — DoD: comment
      present and cross-references `cmd/server/main.go`'s audience-config
      variables by name.
- [ ] 8. Update `docs/runbooks/canary.md`'s "Mitigation > Token expired"
      section to reference `POST /api/mcp/worker-token` instead of the
      unqualified "rotate the canary bearer in the Secret" instruction —
      DoD: runbook names the endpoint and states the new token still goes into
      the `mctl-telegram-canary` Secret's `bearer_token` key, no CronJob change
      needed.
- [ ] 9. Add a code comment on `allowedReadOnlyScopes` in `internal/workertoken`
      cross-referencing `internal/oauth/scopes.go`'s `DCRNegotiableScopes` so a
      future scope addition prompts a reviewer to check both lists (depends on
      1) — DoD: comment present in both files pointing at each other.

## Tests

- [ ] T1. Unit test: admin identity + default request (no `scopes`, no
      `ttl_hours`) mints a token with exactly `allowedReadOnlyScopes` and TTL
      `defaultWorkerTokenTTL`.
- [ ] T2. Unit test: request with a write scope (`telegram:messages:send`) or
      `admin:users` in `scopes` is rejected with 400 and produces no token.
- [ ] T3. Unit test: non-admin authenticated identity gets 403; unauthenticated
      request gets 401.
- [ ] T4. Unit test: `ttl_hours` above the ceiling is clamped to
      `maxWorkerTokenTTL`; `ttl_hours` within range is honored exactly, mirroring
      the existing `TestNewAgentTokenHandler`-style TTL clamp test if one exists
      in `internal/agentapi/tokenhandler_test.go` (reuse its structure).
- [ ] T5. Integration-shaped test (can live alongside `internal/mcp/tools_test.go`
      patterns): a token minted with only `allowedReadOnlyScopes` passes
      `requireScope("telegram:dialogs:read")` / `requireScope("telegram:messages:read")`
      but fails `requireScope("telegram:messages:send")`, confirming the
      existing per-tool gate (`internal/mcp/tools.go:1196`) already enforces the
      boundary this proposal relies on — this test should already pass without
      any change to `internal/mcp`; it documents the invariant this design
      depends on rather than introducing new behavior.
- [ ] T6. `go vet` / `golangci-lint` clean on the new package and the
      `cmd/server/main.go` diff, per repository convention.

## Rollback

The new endpoint is additive and gated behind `cfg.OAUTHJWTSecret != ""`,
exactly like the two existing mint endpoints it is modeled on. To roll back:

1. Remove the `POST /api/mcp/worker-token` route registration in
   `cmd/server/main.go` (or simply do not deploy the new binary — the change
   has no accompanying schema migration to reverse).
2. Any tokens already minted through the endpoint continue to work until
   their `exp` (there is no revocation, same as every other `localjwt` token
   today — consistent with the existing system, not a regression introduced
   by this change). If immediate invalidation is required, rotate
   `OAUTH_JWT_SIGNING_KEY` — this invalidates every outstanding local-jwt
   token platform-wide (interactive sessions, agent tokens, bridge tokens,
   and worker tokens alike), which is the same blunt instrument available
   today for the manually-signed canary token.
3. No data migration or backfill is needed in either direction since no new
   tables or columns are introduced.
