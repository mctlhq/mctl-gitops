# Tasks: issue-464-feat-mcp-mint-worker-token-tool-so-issui

- [ ] 1. Add `internal/workertoken/mint.go` exporting `Purpose`,
      `MintParams`, `MintResult`, sentinel errors
      (`ErrUnknownPurpose`, `ErrInvalidTelegramID`, `ErrScopeNotAllowed`),
      and `Mint(signer *localjwt.Issuer, mcpAudience string, p MintParams) (*MintResult, error)`
      containing the purpose dispatch, scope-allowlist validation, TTL
      clamp, audience assembly, and `orig_iat` anchoring currently inlined
      in `tokenhandler.go:153-220`. — DoD: `Mint` compiles standalone, has
      no HTTP-specific imports (`net/http`, JSON), and existing constants
      (`allowedReadOnlyScopes`, `allowedLocalBridgeScopes`,
      `defaultWorkerTokenTTL`, `maxWorkerTokenTTL`, `workerAudience`,
      `workerBridgeAudience`) are referenced, not duplicated.
- [ ] 2. Rewrite `internal/workertoken/tokenhandler.go`'s `NewHandler` to
      decode the request, translate to `MintParams`, call `Mint`, map its
      sentinel errors to the same HTTP status codes it returns today (400
      for `ErrUnknownPurpose`/`ErrInvalidTelegramID`/`ErrScopeNotAllowed`,
      500 for signer failure), and log/respond using `Mint`'s result.
      (depends on 1) — DoD: `go test ./internal/workertoken/...` passes
      unchanged (existing `tokenhandler_test.go` assertions on status
      codes, response body, and log fields still hold with zero test
      edits, proving the refactor is behavior-preserving).
- [ ] 3. Add `WorkerTokenSigner *localjwt.Issuer` and
      `WorkerTokenAudience string` fields plus
      `WithWorkerTokenSigner(signer *localjwt.Issuer, mcpAudience string) *Server`
      to `internal/mcp/server.go`, matching the existing `With*` builder
      pattern (`WithHub`, `WithMetrics`, etc.). (depends on 1) — DoD:
      `mcp.Server{}` zero value has `WorkerTokenSigner == nil` (safe
      default, tool refuses cleanly).
- [ ] 4. Add `stringSliceArg(args map[string]any, key string) []string`
      helper in `internal/mcp/tools.go` next to `intArg`/`stringArg`/
      `boolArg`, returning nil when the key is absent or not a
      `[]any`/`[]string`-shaped value. — DoD: unit-tested for absent key,
      empty array, and populated array.
- [ ] 5. Add `mintWorkerTokenResult` struct (`TelegramID`, `Purpose`,
      `Scopes`, `ExpiresAt`, `Token`, `OK`) next to `setAccountModeResult`
      in `internal/mcp/tools.go`, and implement `toolMintWorkerToken()`
      following `toolSetAccountMode`'s shape: `requireScope(id,
      "admin:users")` first, a `refuse` closure auditing every exit past
      the gate (including the `WorkerTokenSigner == nil` case), a call to
      `workertoken.Mint`, a `slog.Info("worker token minted", ...)` line on
      success carrying `purpose`, `scopes`, `expires_at`,
      `audience_marker` (never the raw token), and a final
      `s.audit(ctx, id, "mint_worker_token", "", nil, startedAt)` before
      `jsonResult(...)`. (depends on 1, 3, 4) — DoD: every early return
      after the scope gate — invalid `telegram_id`, unknown `purpose`,
      scope outside allowlist, signer not configured — is proven audited
      by test 5 below.
- [ ] 6. Register the tool in `internal/mcp/server.go`'s `HTTPHandler`:
      `{t, h := s.toolMintWorkerToken(); s.addTool(srv, t, h)}`, placed
      next to `toolSetAccountMode`/`toolProvisionLocalAccount`.
      (depends on 5) — DoD: tool appears in the MCP tool list when
      `WorkerTokenSigner` is set; `s.ToolFilter == "read-only"` excludes it
      (its `ReadOnlyHint` is `false`, matching `toolSetAccountMode`).
- [ ] 7. Wire `cmd/server/main.go`: inside the existing
      `if secret := cfg.OAUTHJWTSecret; secret != "" { ... }` block that
      mounts `POST /api/mcp/worker-token` (around line 470), construct a
      `*localjwt.Issuer` via `localjwt.NewIssuer([]byte(secret),
      selectAgentIssuer(cfg))` and chain
      `mcpSrv = mcpSrv.WithWorkerTokenSigner(signer, cfg.OAUTHJWTAudience)`
      onto the existing `mcpSrv` assignment chain, logging and continuing
      (tool stays unconfigured, not a startup failure) if signer
      construction errors. (depends on 3) — DoD: with
      `OAUTH_JWT_SIGNING_KEY` unset, server starts and `mint_worker_token`
      calls return the "not configured" refusal instead of panicking or
      being silently absent from documentation.
- [ ] 8. Update `docs/runbook.md` (or wherever the existing worker-token
      curl instructions live, per the issue's reference to "docs/runbook.md
      points an operator at this line") to document `mint_worker_token` as
      the preferred path and the HTTP endpoint as the fallback for
      non-MCP callers (e.g. CI). (depends on 6) — DoD: doc mentions both
      surfaces call the same policy and that `purpose: "local-bridge"`
      must be requested explicitly for a send/pin-capable token.

## Tests

- [ ] T1. `internal/workertoken/mint_test.go`: table test over
      `purpose=""` and `purpose="local-bridge"` asserting `Mint` selects
      the correct allowlist, applies the correct default scopes when
      `Scopes` is empty, clamps `TTLHours` to `maxWorkerTokenTTL`, and sets
      the correct `AudienceMarker`. Covers task 1.
- [ ] T2. `internal/workertoken/tokenhandler_test.go` (existing file):
      confirm all current tests pass unmodified after task 2's refactor —
      this is the regression guard that the HTTP behavior did not change.
      Covers task 2.
- [ ] T3. Parity test (new, in `internal/workertoken/` or
      `internal/mcp/`) — the test the issue explicitly asks for: drive
      `NewHandler` over HTTP and `workertoken.Mint` directly with
      equivalent inputs (`telegram_id`, `purpose`, `scopes`, `ttl_hours`)
      for both purposes, and assert identical `Scopes`, clamped TTL
      (`ExpiresAt` within a small tolerance of each other), and audience
      marker. Written so that reintroducing separate allowlist/TTL/
      audience logic in either caller — e.g. hardcoding scopes in
      `toolMintWorkerToken` instead of calling `Mint` — makes this test
      fail. Covers design.md's "Proposed solution" step 4.
- [ ] T4. `internal/mcp/tools_test.go`: `toolMintWorkerToken` returns a
      refusal, and audits it, for: no `admin:users` scope, `telegram_id
      <= 0`, unknown `purpose`, a `scopes` entry outside the selected
      allowlist, and `WorkerTokenSigner == nil`. Mirrors the existing
      `toolSetAccountMode` refusal tests. Covers task 5.
- [ ] T5. `internal/mcp/tools_test.go`: successful mint with
      `purpose=""` yields `Scopes == allowedReadOnlyScopes` and no
      send/pin scope present; successful mint with
      `purpose="local-bridge"` yields send+pin scopes present only when
      explicitly requested via `purpose`. Asserts the result includes a
      parseable `ExpiresAt` and that the success path is audited with
      `err == nil`. Covers task 5 and the issue's "send/pin still requires
      naming the purpose explicitly" acceptance criterion.
- [ ] T6. `internal/mcp/tools_test.go`: with `WorkerTokenSigner == nil`
      (server built without task 3's wiring), the tool returns the
      "not configured" refusal rather than a nil-pointer panic. Covers
      task 7's fallback path.

## Rollback

The tool is additive and does not change the shape, route, or gating of
`POST /api/mcp/worker-token` / `/renew` (task 2 is a behavior-preserving
internal refactor, guarded by T2 running the pre-existing test suite
unmodified). If `mint_worker_token` needs to be pulled:

1. Revert task 6's registration line in `internal/mcp/server.go` (or set
   `cfg.OAUTHJWTSecret` unset in the affected deployment, which leaves the
   tool present but permanently refusing via the `WorkerTokenSigner == nil`
   path added in task 5/7) — either is a single-commit revert with no data
   migration, since no schema changed.
2. `internal/workertoken/mint.go`'s `Mint` can stay even if the tool is
   pulled — `NewHandler` depends on it after task 2, so removing it would
   require reverting task 2 as well. If a full rollback to pre-proposal
   state is needed, revert tasks 1-7 as one PR revert (they land as a
   single logical change per the repo's squash-merge convention).
3. No audit-log or gitops-config cleanup is needed: `mint_worker_token`
   audit rows are ordinary `audit_logs` entries, harmless to retain, and
   `SESSION_TTL_EXEMPT_TG_IDS` is untouched by this proposal.
