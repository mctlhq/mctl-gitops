# Tasks: issue-459-feat-workertoken-mint-local-bridge-token

- [ ] 1. Add `allowedLocalBridgeScopes` and `workerBridgeAudience` —
      DoD: `internal/workertoken/tokenhandler.go` defines
      `allowedLocalBridgeScopes = []string{"telegram:dialogs:read",
      "telegram:messages:read", "telegram:messages:send",
      "telegram:messages:pin"}` with a doc comment cross-referencing
      `allowedReadOnlyScopes` (mirroring `scopes.go`'s existing
      cross-reference); `renewhandler.go` defines `workerBridgeAudience =
      "mcp-worker-bridge"` next to `workerAudience` with an equivalent doc
      comment; `allowedReadOnlyScopes` itself is untouched (diff shows no
      changes to its lines).

- [ ] 2. Generalize the scope-allowlist check (depends on 1) — DoD:
      `isAllowedReadOnlyScope(scope string) bool` is replaced by
      `isAllowedScope(scope string, allowlist []string) bool` (or an
      equivalent parameterized helper); both call sites in
      `tokenhandler.go` and both call sites in `renewhandler.go` are
      updated; `go build ./...` succeeds.

- [ ] 3. Add `Purpose` to the mint request and branch `NewHandler`
      (depends on 2) — DoD: `mintWorkerTokenRequest` gains `Purpose string
      \`json:"purpose,omitempty"\`` with a doc comment; `NewHandler`
      selects `(allowlist, defaultScopes, audienceMarker)` based on
      `req.Purpose` (`""` → read-only path unchanged; `"local-bridge"` →
      local-bridge allowlist/default/`workerBridgeAudience`; anything else
      → 400 `"unknown purpose: <value>"`); a request with no `purpose`
      field produces byte-identical output to today (verified by task 7's
      regression tests).

- [ ] 4. Log `expires_at` at mint (depends on 3) — DoD: the
      `slog.Info("worker token minted", ...)` call in `NewHandler` includes
      an `"expires_at"` field with the same RFC3339 value returned in the
      response body.

- [ ] 5. Extend `NewRenewHandler` to accept either audience marker
      (depends on 1, 2) — DoD: the audience check at
      `renewhandler.go:104-107` accepts `workerAudience` OR
      `workerBridgeAudience` (rejecting neither → same 403 message,
      unchanged); the defense-in-depth scope loop at
      `renewhandler.go:112-122` selects its allowlist based on which
      marker was present on the presented token; the audience rebuilt on
      re-mint (`renewhandler.go:161-169`) preserves whichever marker was
      present, plus `mcpAudience` if configured, exactly as today's
      `workerAudience`-only logic does.

- [ ] 6. Log `expires_at` at renewal (depends on 5) — DoD: the
      `slog.Info("worker token renewed", ...)` call includes an
      `"expires_at"` field, matching task 4's mint-side addition.

- [ ] 7. Update `docs/local-bridge.md` and `docs/runbook.md` (depends on
      3, 5) — DoD: `docs/local-bridge.md`'s `connect` step (or the
      paragraph above it explaining where the MCP token comes from)
      documents minting with `{"telegram_id": ..., "purpose":
      "local-bridge"}` via `POST /api/mcp/worker-token` as the supported
      path, replacing any implication that hand-signing is required;
      `docs/runbook.md`'s `MctlBridgeDaemonsFlapping` → "Bridge-token
      expiry loop" likely-cause entry gains a line pointing at the mint/
      renew log's `expires_at` field as the fast way to confirm or rule
      out this cause.

## Tests

- [ ] T1. `TestNewHandler_LocalBridgePurposeDefaultScopes` — no `scopes`
      field, `purpose: "local-bridge"` mints exactly
      `allowedLocalBridgeScopes` (all four) with `aud` containing
      `"mcp-worker-bridge"`.
- [ ] T2. `TestNewHandler_LocalBridgePurposeExplicitSubset` — `purpose:
      "local-bridge"` with `scopes: ["telegram:messages:send"]` (a subset)
      is honored, mirroring the existing
      `TestNewHandler_ExplicitSubsetScopeHonored` for the read-only path.
- [ ] T3. `TestNewHandler_LocalBridgePurposeRejectsUnknownScope` —
      `purpose: "local-bridge"` with a scope outside
      `allowedLocalBridgeScopes` (e.g. `"admin:users"`) is rejected with
      400, mirroring `TestNewHandler_RejectsWriteScope`'s shape for the
      read-only path.
- [ ] T4. `TestNewHandler_RejectsUnknownPurpose` — `purpose: "bogus"` is
      rejected with 400.
- [ ] T5. `TestNewHandler_NoPurposeUnchanged` — a request identical to
      today's (`{"telegram_id": N}`, no `purpose` field) still yields
      `allowedReadOnlyScopes` and `aud` containing `"mcp-worker-ro"` —
      regression guard for backward compatibility.
- [ ] T6. `TestNewHandler_LocalBridgePurposeRespectsTTLBounds` — TTL
      clamping (`maxWorkerTokenTTL`) and default TTL
      (`defaultWorkerTokenTTL`) behave identically for `purpose:
      "local-bridge"` as for the read-only path, mirroring
      `TestNewHandler_TTLClamp`.
- [ ] T7. `TestRenew_LocalBridgeTokenRenewsWithSendScope` — a token minted
      with `aud=["mcp-worker-bridge"]` and
      `scopes=["telegram:messages:send","telegram:messages:pin"]` renews
      successfully and the renewed token preserves those scopes — this is
      the test that would fail against today's code (the existing
      defense-in-depth check would reject it), proving the fix.
- [ ] T8. `TestRenew_LocalBridgeTokenRejectsScopeOutsideBridgeAllowlist` —
      a token carrying `aud=["mcp-worker-bridge"]` plus a scope outside
      `allowedLocalBridgeScopes` (e.g. `"admin:users"`) is refused
      renewal, mirroring `TestRenew_RejectsScopeOutsideAllowlist` for the
      new allowlist.
- [ ] T9. `TestRenew_ReadOnlyTokenStillRejectsSendScope` — regression:
      a token with `aud=["mcp-worker-ro"]` carrying
      `"telegram:messages:send"` is still refused renewal (proves the
      audience-to-allowlist mapping did not accidentally cross-wire).
- [ ] T10. `TestRenew_RejectsNonWorkerAudience` (existing test) — extend
      the table with `{"local-bridge-shaped but wrong string",
      []string{"mcp-worker-bridge-typo"}}` to confirm only the exact
      marker values are accepted.
- [ ] T11. `TestNewHandler_LogsExpiresAt` /
      `TestRenew_LogsExpiresAt` — capture `slog` output (or refactor the
      logger to be injectable if the existing tests do not already support
      this) and assert `expires_at` is present and matches the response
      body's `ExpiresAt`. If the existing test harness has no precedent
      for asserting on log output, fall back to asserting only the
      response-body/behavioral contract in T1-T10 and note the log
      assertion as manual verification in the PR description.
- [ ] T12. `go vet ./...` and `golangci-lint run` pass (repo convention,
      per `CLAUDE.md`).

## Rollback

This is a pure additive change to an existing package with no schema
migration and no config/env var changes — rollback is a plain revert of the
commit(s)/PR.

- If a bad mint has already produced a live send-capable token before
  rollback: the token remains valid until its own expiry regardless of code
  rollback (it is a self-contained signed JWT, per `SECURITY.md`'s existing
  "access tokens are not individually revocable within their TTL" trade-off
  applied to this token family too). An admin can force early invalidation
  the same way any locally-issued JWT is force-invalidated today: rotating
  `OAUTH_JWT_SECRET`/`OAUTH_JWT_SIGNING_KEY` — the blunt, whole-deployment
  instrument this proposal exists to avoid reaching for routinely, but still
  the correct tool for an actual incident.
- Reverting the code change does not touch previously-minted tokens' claims
  (nothing rewrites already-issued JWTs); it only stops new `purpose:
  "local-bridge"` mints from succeeding (they revert to 400, since the
  `Purpose` field and branch no longer exist) and stops
  `aud=["mcp-worker-bridge"]` tokens from renewing (the renew handler
  reverts to accepting `workerAudience` only) — an already-issued
  local-bridge token would then fail to renew and expire on schedule at its
  next TTL boundary, which is a safe failure mode (daemon reconnect loop,
  same as today's "MCP token expired" case), not a security regression.
- No data backfill or cleanup needed on rollback.
