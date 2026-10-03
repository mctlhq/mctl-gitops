# Tasks: issue-701-connect-oauth-follow-ups-from-698-review

Nine independent items. Tasks 1-9 map one-to-one onto the issue's items; each
can land and be reverted alone. Suggested order is the order below (item 1 is
the only user-visible one).

- [ ] 1. Add `framedLoginErr(prefix string, err error, suffix string) string` to
  `internal/oauth/enable_access.go` next to `friendlyErr`, returning bare
  `friendlyErr(err)` when `shortReason(err) == "auth_restart"` and
  `prefix + friendlyErr(err) + suffix` otherwise. Rewrite all three call sites
  to use it: `handleEnableStart` (replacing the inline guard at lines 833-839),
  `handleEnableCode` (line 948-951, `"The code was not accepted: "` /
  `" Start again to get a fresh code."`), `handleEnablePassword`'s generic
  fallback (line 1056-1059, `"The password was not accepted: "` /
  `" Start again."`). Leave the `db.ErrAccountModeConflict` and
  `reason == "bad_password"` arms untouched. — DoD: `go test ./internal/oauth/...`
  passes with the existing phone-step test at
  `enable_access_classification_test.go:167-203` unmodified; T1 and T2 pass.

- [ ] 2. In `internal/web/connect.go`, add
  `reasonRecoveredRedirect = "recovered_redirect"` to the const block (lines
  51-59) and restructure `HandleConnectDone`'s reused/expired arm (lines 281-293)
  so `s.alreadyConnected(r)` is evaluated first: on true, emit one `slog.Info`
  ("connect: request recovered", `route`, `reason=recovered_redirect`,
  `prefetch`) and redirect 303 to `/telegram/connect/manage`; on false, compute
  `unknown_state`/`expired_state` as today and call `logConnectReject`. — DoD:
  no request emits both a reject and a recovery line; T3 passes.

- [ ] 3. In `internal/oauth/server_test.go`, extend
  `TestHandleTelegramCallback_PrefetchDoesNotConsumeState` (line 1038) with two
  additional prefetch requests sent via `callbackWithStateHeaders(t, mux,
  act.oidcState, ...)` — one `Sec-Purpose`, one legacy `Purpose` — keeping the
  two existing `state`-carrying requests, and comment why both states are
  exercised. — DoD: the `stillIndexed` assertion at line 1074 fails when the
  prefetch guard (`internal/oauth/server.go:1562-1570`) is moved below the
  activation dispatch; T4 documents the manual check.

- [ ] 4. Guard `MCP_PATH=/`: in `internal/config/config.go` after `MCPPath` is
  populated (line 347), return an error from `Load` when
  `strings.Trim(c.MCPPath, "/") == ""`, naming the variable and the shadowing
  reason; in `cmd/server/main.go`, wrap `mux.Post("/", web.RootPostHint(cfg.MCPPath))`
  (line 410) in `if strings.Trim(cfg.MCPPath, "/") != ""`. — DoD: T5 passes;
  `MCP_PATH=/mcp`, `MCP_PATH=mcp`, unset and `/v1/mcp` all behave as before.

- [ ] 5. In `internal/web/landing.go`, change `RootPostHint`'s header to
  `Allow: GET, POST` and correct the doc comment to state that `POST /` is
  registered alongside `GET /` (`cmd/server/main.go:409-410`) so chi's own 405
  lists both. Update the expectation in
  `internal/web/root_post_hint_test.go` (currently `want GET`). — DoD: T6 and T7
  pass; status, `Cache-Control`, content type and the JSON-RPC `-32600` body are
  unchanged.

- [ ] 6. Split the TTL case in the pending store. In
  `internal/db/store_oauth.go`: declare
  `var ErrOAuthExpired = fmt.Errorf("oauth: expired: %w", ErrOAuthNotFound)`;
  in `ConsumeOAuthPending` (line 182) drop `AND created_at >= $2` from the
  `DELETE`, keep the single `DELETE ... RETURNING`, and after a successful scan
  return `ErrOAuthExpired` when `p.CreatedAt.Before(cutoff)`; document that an
  expired row is now consumed rather than left for the sweeper. — DoD: T8, T9
  pass; `errors.Is(ErrOAuthExpired, ErrOAuthNotFound)` is true.

- [ ] 7. Consume the split in the callback (depends on 6). In
  `internal/oauth/server.go`'s `useDB` branch (lines 1622-1633) check
  `errors.Is(err, db.ErrOAuthExpired)` **before** `db.ErrOAuthNotFound` and log
  `reasonExpiredState` there, rendering the same reused-link page; replace the
  now-stale "Known limit" paragraph in the const-block comment (lines 1518-1522)
  with a note that both stores distinguish the two cases. — DoD: T10 passes;
  `internal/oauth/demo_login.go:186-188` is unmodified and still handles both.

- [ ] 8. Prefetch guard headers and documented limits. Add
  `w.Header().Set("Vary", "Sec-Purpose, Purpose")` to both 204 refusal arms
  (`internal/web/connect.go:248`, `internal/oauth/server.go:1567`) — one `Set`,
  never `Add`, per the duplicate-token note at
  `internal/auth/middleware.go:256`. Extend both `isPrefetch` doc comments
  (`internal/web/connect.go:61`, `internal/oauth/server.go:1532`) with the
  Safari / Firefox `X-moz: prefetch` limits. — DoD: T11 passes; the doc comments
  state the guard is best-effort in both files.

- [ ] 9. Vocabulary hygiene in three edits: (a) add
  `reasonExchangeFailed = "exchange_failed"` to `internal/oauth/server.go`'s
  const block and use it at line 1690, dropping the block comment's "connect.go
  additionally has exchange_failed" sentence; (b) document the always-false
  `prefetch` attribute as retained-for-schema-stability on both
  `logConnectReject` (`internal/web/connect.go:73`) and `logCallbackReject`
  (`internal/oauth/server.go:1542`); (c) add a one-line comment on
  `friendlyErr`'s `isBadPasswordErr` arm (`internal/oauth/enable_access.go:1172`)
  naming `handleEnablePassword`'s `badPasswordRestartMsg` as the live path and
  `enable_access_friendly_test.go` as the test that keeps the arm live. — DoD:
  T12, T13 pass; no bare `"exchange_failed"` literal remains
  (`git grep '"exchange_failed"'` matches only the const declarations).

- [ ] 10. Runbook (depends on 2, 7, 9a for the final token set). Add
  `## Connect and OAuth callback rejection reasons` to `docs/runbook.md` with
  `id="connectrejectionreasons"`, linked from the table of contents (line 20):
  a table covering `missing_state`, `missing_code`, `unknown_state`,
  `expired_state`, `exchange_failed`, `oidc_error`, `prefetch_refused`,
  `recovered_redirect` — each with the route that emits it, the log level, its
  meaning and the operator's first action — plus a short subsection documenting
  the `auth provider init failed` startup headline
  (`cmd/server/main.go:437`) and that the process refuses to start. — DoD: T14
  and T15 pass; `docs/runbook_test.go`'s existing tests still pass.

## Tests

- [ ] T1. `internal/oauth/enable_access_classification_test.go`: new
  `TestAuthRestartAtCodeStep_NotDoubleFramed` — drive the phone step to
  `stepCode`, have the fake login flow fail the sign-in with
  `tgerr.New(500, "AUTH_RESTART")`, and assert the rendered body contains
  `"Telegram ended the sign-in session. Submit your phone number again to get a
  fresh code."` exactly once and contains neither `"The code was not accepted"`
  nor `"Start again to get a fresh code"`. Also assert the audit entry
  `connect:failed:auth_restart` is still written, mirroring lines 190-203.
- [ ] T2. Same file: `TestAuthRestartAtPasswordStep_NotDoubleFramed` — same
  shape at `stepPassword`, asserting the absence of `"The password was not
  accepted"`. Plus a table unit test of `framedLoginErr` over the three
  prefix/suffix pairs proving non-`AUTH_RESTART` errors keep the exact legacy
  wording byte-for-byte.
- [ ] T3. `internal/web/connect_test.go`: `TestHandleConnectDone_RecoveredRedirect`
  — with an `Identifier` that accepts the request and an unknown state, assert
  303 to `/telegram/connect/manage`, that the captured log contains
  `reason=recovered_redirect`, and that it contains neither
  `reason=unknown_state` nor `reason=expired_state`. A second subtest with a nil
  (or refusing) `Identifier` asserts `reason=unknown_state` at WARN and the
  reused page, unchanged.
- [ ] T4. `internal/oauth/server_test.go`: the amended
  `TestHandleTelegramCallback_PrefetchDoesNotConsumeState` (task 3). Verify
  manually once, before committing, that moving the prefetch guard below the
  activation dispatch makes it fail.
- [ ] T5. `internal/config/config_test.go`:
  `TestLoad_RejectsRootMCPPath` — `MCP_PATH=/` and `MCP_PATH=//` each make
  `Load` return an error mentioning `MCP_PATH`; `MCP_PATH=/mcp`, `MCP_PATH=mcp`
  and unset each succeed with the value seen today.
- [ ] T6. `internal/web/root_post_hint_test.go`: assert
  `Allow` on the `POST /` 405 parses to the method set `{GET, POST}`
  (split on `,`, trim, compare as a set — chi's ordering is not contractual).
- [ ] T7. `internal/web/root_post_hint_test.go`: new
  `TestRootPostHint_MatchesChiMethodNotAllowed` — build a real `chi.NewRouter()`
  with `Get("/", Landing(...))` and `Post("/", RootPostHint("/mcp"))`, send
  `PUT /`, `DELETE /` and `HEAD /`, and assert 405 with the same parsed method
  set as T6.
- [ ] T8. `internal/db/store_oauth_test.go` (Postgres-backed, skipping without
  `TEST_DATABASE_URL` like `internal/db/local_bridge_devices_test.go:286`):
  `TestConsumeOAuthPending_ExpiredIsDistinguishable` — `InsertOAuthPending`, then
  backdate `created_at` via raw SQL on `store.DB`, then consume with a short
  `ttl` and assert `errors.Is(err, ErrOAuthExpired)`, `errors.Is(err,
  ErrOAuthNotFound)`, and that the row is gone. A never-issued state must give
  `ErrOAuthNotFound` and NOT satisfy `errors.Is(err, ErrOAuthExpired)`.
- [ ] T9. `internal/db`: a no-database unit assertion that
  `errors.Is(ErrOAuthExpired, ErrOAuthNotFound)` is true — this is the
  compatibility contract for the four existing callers and must hold in CI
  without Postgres.
- [ ] T10. `internal/oauth/server_test.go`: extend
  `TestHandleTelegramCallback_ReusedState_FriendlyPage`'s `db-backed` subtest
  (line 934) with an `expired` case — seed a pending row through
  `/oauth/authorize`, backdate it, then call the callback and assert
  `reason=expired_state` in the captured log plus the existing "already used"
  page. Skips without `TEST_DATABASE_URL`, same as its sibling.
- [ ] T11. One test per package asserting the 204 refusal carries
  `Vary: Sec-Purpose, Purpose` exactly once: extend
  `TestHandleConnectDone_PrefetchDoesNotConsumeState`
  (`internal/web/connect_test.go:437`) and
  `TestHandleTelegramCallback_PrefetchDoesNotConsumeState`
  (`internal/oauth/server_test.go:1038`).
- [ ] T12. `internal/oauth/server_test.go`:
  `TestHandleTelegramCallback_ExchangeFailureLogsReason` — make the fake
  authenticator's `Exchange` return an error and assert the captured log
  contains `reason=`+`reasonExchangeFailed` and that the response is 401 with an
  opaque body (no Telegram id).
- [ ] T13. Schema-stability assertions: one test per package confirming a reject
  line carries the `prefetch` attribute (`prefetch=false`) — extend the existing
  reason-table tests at `internal/web/connect_test.go:360-410` and
  `internal/oauth/server_test.go:993-1002`.
- [ ] T14. `internal/web`: `TestRunbookDocumentsConnectReasons` — iterate a slice
  of every `reason*` const in `connect.go` (including
  `reasonRecoveredRedirect`) and assert each value appears in
  `../../docs/runbook.md`, modelled on
  `internal/oauth/troubleshooting_doc_test.go`.
- [ ] T15. `internal/oauth`: `TestRunbookDocumentsCallbackReasons` — the same
  over `server.go`'s const block (including `reasonExchangeFailed`), plus an
  assertion that the literal `auth provider init failed` appears in
  `docs/runbook.md`.

Full gate before the PR: `go fmt ./...`, `go vet ./...`, `golangci-lint run`,
`go test ./...` (and once more with `TEST_DATABASE_URL` set, so T8 and T10
actually run). Conventional commits; merge with
`gh pr merge <N> --merge --delete-branch`.

## Rollback

Every item is an independent revert.

- Tasks 1, 2, 3, 5, 8, 9, 10 touch only wording, log attributes, headers,
  comments, docs or tests. `git revert` of the individual commit restores the
  prior behaviour with no state to unwind.
- Task 4 is the only one that can stop a deployment from booting. If a
  previously-working environment fails startup with the new `MCP_PATH` error,
  the operational fix is to set `MCP_PATH=/mcp` (the documented default) rather
  than to revert; reverting the `config.Load` check alone is safe and leaves the
  `cmd/server/main.go` registration guard in place.
- Tasks 6 and 7 change no schema and no data. Reverting task 7 alone returns the
  callback to logging `unknown_state` for both cases while leaving the store's
  richer error in place (harmless: `ErrOAuthExpired` wraps
  `ErrOAuthNotFound`, so the old single check still matches). Reverting task 6
  alone after task 7 landed would break compilation, so revert them together or
  revert 7 first.
- Dashboards or alerts keyed on `reason=unknown_state` as "all callback state
  failures" should be widened to `reason=~"unknown_state|expired_state"` when
  task 7 lands; that query change is the only follow-up outside the repo.
