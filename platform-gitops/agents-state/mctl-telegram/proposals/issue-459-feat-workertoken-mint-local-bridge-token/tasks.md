# Tasks: issue-459-feat-workertoken-mint-local-bridge-token

- [ ] 1. Add `allowedBridgeScopes` and `isAllowedBridgeScope` to
      `internal/workertoken/tokenhandler.go`, listing
      `telegram:dialogs:read`, `telegram:messages:read`,
      `telegram:messages:send`, `telegram:messages:pin` as literal values
      (not imported from `internal/oauth`), with a doc comment mirroring
      the existing `allowedReadOnlyScopes` comment's drift-safety
      reasoning — DoD: new var + helper compile, no existing symbol
      renamed, `allowedReadOnlyScopes` untouched.
- [ ] 2. Add `workerBridgeAudience = "mcp-worker-bridge"` constant next to
      `workerAudience` in `internal/workertoken/renewhandler.go` (or
      tokenhandler.go, whichever already owns `workerAudience` — check
      before adding) — DoD: constant defined, referenced from both
      handler files without an import cycle.
- [ ] 3. Add `Purpose string` (`json:"purpose,omitempty"`) to
      `mintWorkerTokenRequest` in `tokenhandler.go`, and branch
      `NewHandler`'s scope-default/scope-validation/audience logic on
      `Purpose` (depends on 1, 2) — DoD: `Purpose == ""` reproduces
      today's behavior exactly (existing tests pass unmodified);
      `Purpose == "local-bridge"` defaults to `allowedBridgeScopes`,
      validates explicit scopes against `isAllowedBridgeScope`, and mints
      with `Audience: []string{workerBridgeAudience, <mcpAudience if
      set>}`; any other `Purpose` value returns 400.
- [ ] 4. Add `expires_at` (RFC3339, from the already-computed response
      value) to the `slog.Info("worker token minted", ...)` log line in
      `tokenhandler.go`, alongside the existing `ttl` field (depends on 3)
      — DoD: log line carries both `ttl` and `expires_at` for every mint,
      regardless of purpose.
- [ ] 5. Update `internal/workertoken/renewhandler.go`'s audience check
      (currently `hasAudience(claims.Audience, workerAudience)`) to accept
      either `workerAudience` or `workerBridgeAudience`, and record which
      one matched (depends on 2) — DoD: a token with neither audience is
      still refused 403 "token is not a worker token", unchanged.
- [ ] 6. Replace the renew handler's flat
      `isAllowedReadOnlyScope`-only defense-in-depth loop with a
      purpose-aware check: read-only-audience tokens validate against
      `allowedReadOnlyScopes`, bridge-audience tokens validate against
      `allowedBridgeScopes` (depends on 1, 5) — DoD: a bridge-audience
      token carrying only scopes from `allowedBridgeScopes` renews
      successfully; a token (of either audience) carrying any scope
      outside its matching allowlist is refused 403, matching the
      existing `TestRenew_RejectsScopeOutsideAllowlist` semantics extended
      to the new allowlist.
- [ ] 7. Update the renew handler's audience-rebuild
      (`audience := []string{workerAudience}` before minting the renewed
      token) to reuse whichever of the two worker audiences the presented
      token carried, not always `workerAudience` (depends on 5) — DoD: a
      renewed bridge-purpose token keeps carrying `mcp-worker-bridge` (plus
      `mcpAudience` if set) and stays renewable on its next cycle.
- [ ] 8. Add `expires_at` to the renew handler's
      `slog.Info("worker token renewed", ...)` log line, alongside the
      existing `ttl`, `original_issued_at`, and `chain_deadline` fields
      (depends on 3, 4) — DoD: log line for every renewal (either purpose)
      carries the new token's absolute expiry.
- [ ] 9. Update `docs/runbook.md`'s `MctlBridgeDaemonsFlapping` section:
      replace the "there is no supported way to issue a long-lived MCP
      token today" likely-cause bullet with a pointer to
      `purpose: "local-bridge"` minting, and add a one-line diagnostic step
      to check the mint/renew log's `expires_at` before assuming a
      different root cause (depends on 3, 4, 8) — DoD: the section no
      longer describes the gap this proposal closes as unresolved.

## Tests

- [ ] T1. `TestNewHandler_BridgePurposeDefaultsToFullScopeSet` — POST with
      `purpose: "local-bridge"` and no `scopes` mints a token whose
      `Scopes` equal `allowedBridgeScopes` (send + pin + both read scopes).
- [ ] T2. `TestNewHandler_BridgePurposeAllowsSendScope` — POST with
      `purpose: "local-bridge"`, `scopes: ["telegram:messages:send"]`
      succeeds (200), where today's default-purpose request with the same
      scope is rejected (covered by existing
      `TestNewHandler_RejectsWriteScope`).
- [ ] T3. `TestNewHandler_DefaultPurposeStillRejectsSendScope` — regression
      pin: omitting `purpose` (or passing `""`) and requesting
      `telegram:messages:send` still returns 400, unchanged from today.
- [ ] T4. `TestNewHandler_RejectsUnknownPurpose` — POST with
      `purpose: "something-else"` returns 400.
- [ ] T5. `TestNewHandler_BridgePurposeMintsBridgeAudience` — a
      `purpose: "local-bridge"` mint carries `mcp-worker-bridge` (and the
      configured `mcpAudience`, mirroring
      `TestNewHandler_IncludesConfiguredMCPAudience`) in its audience, not
      `mcp-worker-ro`.
- [ ] T6. `TestNewHandler_BridgePurposeSetsOriginalIssuedAt` — a
      `purpose: "local-bridge"` mint sets `orig_iat` the same way the
      read-only path does.
- [ ] T7. `TestRenew_BridgeAudienceRenewsSendScopes` — a token minted with
      `workerBridgeAudience` and `telegram:messages:send` renews
      successfully, preserving the scope.
- [ ] T8. `TestRenew_BridgeAudienceRejectsScopeOutsideBridgeAllowlist` — a
      bridge-audience token carrying a scope outside `allowedBridgeScopes`
      is refused renewal (403), mirroring
      `TestRenew_RejectsScopeOutsideAllowlist` for the new allowlist.
- [ ] T9. `TestRenew_ReadOnlyAudienceStillRejectsSendScope` — regression
      pin: a `workerAudience` (`mcp-worker-ro`) token that somehow carries
      `telegram:messages:send` (e.g. a manually forged or legacy-bug token)
      is still refused renewal, exactly as today's
      `TestRenew_RejectsScopeOutsideAllowlist`.
- [ ] T10. `TestRenew_BridgeAudiencePreservesAudienceAcrossRenewal` — a
      renewed bridge-purpose token still carries `mcp-worker-bridge`
      (mirroring `TestRenew_CarriesConfiguredMCPAudience` and
      `TestRenew_PreservesOriginAnchorAcrossRenewals`), so it remains
      renewable on a subsequent cycle.
- [ ] T11. `TestRenew_BridgeAudienceRespectsRenewalChainCeiling` — a
      bridge-purpose token past its 365-day `maxRenewalChain` deadline is
      refused renewal, exactly like
      `TestRenew_RefusesOnceChainExhausted` for the read-only path.
- [ ] T12. Full existing suite (`go test ./internal/workertoken/...`)
      passes unmodified for every pre-existing test — confirms the
      default (`purpose == ""`) path is byte-for-byte unchanged.
- [ ] T13. `go vet ./... && golangci-lint run ./internal/workertoken/...`
      clean, per repo convention (`.claude/CLAUDE.md`).

## Rollback

The change is additive and gated entirely behind a new, optional `purpose`
request field with existing default behavior on absence — there is no
schema migration and no changed wire format for existing callers. Rollback
is a plain revert of the commit(s) touching
`internal/workertoken/tokenhandler.go`,
`internal/workertoken/renewhandler.go`, and `docs/runbook.md`, followed by a
redeploy. Any Local Bridge token already minted under
`purpose: "local-bridge"` keeps working as a bearer JWT after rollback
(minting is stateless — nothing to undo server-side), but it stops being
renewable once the renew handler no longer recognizes
`mcp-worker-bridge`/`allowedBridgeScopes` audience — the daemon holding it
falls back to its normal expiry-driven reconnect-and-fail behavior, the
same as any other MCP-token-expired case the runbook already covers, and an
admin re-mints once the fix is rolled forward again.
