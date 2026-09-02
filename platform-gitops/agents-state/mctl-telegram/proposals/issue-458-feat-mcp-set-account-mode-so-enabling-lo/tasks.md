# Tasks: issue-458-feat-mcp-set-account-mode-so-enabling-lo

- [ ] 1. Add `db.ModeLocal` / `db.ModeHosted` constants next to `TierNone`/`TierClient`
      (`internal/db/store.go:267-271`) — DoD: two new exported string constants
      (`ModeLocal = "local"`, `ModeHosted = "hosted"`), no behavior change, `go build ./...` passes.

- [ ] 2. Add `Store.SetAccountMode(ctx, userID, mode) (int64, error)` in `internal/db/store.go`, next
      to `SetSendEnabled` (depends on 1) — DoD: single `UPDATE telegram_accounts SET mode = $2 WHERE
      user_id = $1 AND revoked_at IS NULL`, returns `RowsAffected`, wraps errors with
      `fmt.Errorf("set account mode: %w", err)`, doc comment cross-references `SetSendEnabled` and
      explains the zero-rows-affected contract, matching the style of the surrounding methods.

- [ ] 3. Add `Store.IsModeExempt(tgID int64) bool` in `internal/db/store.go`, next to
      `WithAbsoluteTTLExempt` — DoD: returns `s.ttlExempt[tgID]`; doc comment explains it exists for
      `set_account_mode` to refuse an unsafe `mode="local"` change, referencing `SweepIdleSessions`.

- [ ] 4. Add `setAccountModeResult` type in `internal/mcp/tools.go`, next to `setAccountSendResult`
      (depends on 1) — DoD: `{TelegramID int64, Mode string, OK bool}` with matching JSON tags
      (`telegram_id`, `mode`, `ok`), same shape as `setAccessResult`/`setAccountSendResult`.

- [ ] 5. Implement `toolSetAccountMode` in `internal/mcp/tools.go`, immediately after
      `toolSetAccountSend` (depends on 2, 3, 4) — DoD: tool name `set_account_mode`; annotations
      `ReadOnlyHint=false`, `DestructiveHint=true`, `OpenWorldHint=false`; `admin:users` scope
      required before any DB access; validates `mode` against `db.ModeLocal`/`db.ModeHosted`;
      refuses `mode=local` when `!s.Store.IsModeExempt(tgID)` with an actionable error naming
      `SESSION_TTL_EXEMPT_TG_IDS`; resolves `telegram_id` via `UserIDByTelegramID`, mapping
      `db.ErrUserNotFound` to a "sign in once first" error; calls `Store.SetAccountMode` and treats
      `rows == 0` as a hard error ("must connect an account first"), never a silent `OK: true`; calls
      `s.audit(ctx, id, "set_account_mode", "", err, startedAt)` on every exit path that reaches the
      DB layer (both the `UserIDByTelegramID` and `SetAccountMode` steps), matching
      `toolSetAccountSend`'s two-audit-call pattern.

- [ ] 6. Register the tool in `internal/mcp/server.go`, next to the existing
      `{t, h := s.toolSetAccountSend(); s.addTool(srv, t, h)}` line (`internal/mcp/server.go:167`)
      (depends on 5) — DoD: `set_account_mode` is registered under the same admin-tool grouping and
      appears in the server's tool list at startup.

- [ ] 7. Update `docs/local-bridge.md` and the relevant section of `docs/runbook.md` (depends on 6)
      — DoD: both documents describe `set_account_mode` as the primary way to enable Local Bridge for
      an account, and keep the `SESSION_TTL_EXEMPT_TG_IDS` gitops edit documented as the still-
      required prerequisite step rather than the whole procedure. Remove or clearly mark superseded
      any instructions describing the one-shot gitops `Job` as the way to flip `mode`.

## Tests

- [ ] T1. `TestToolSetAccountMode_RequiresAdminScope` in `internal/mcp/tools_test.go`, mirroring
      `TestToolSetAccountSend_RequiresAdminScope` (`internal/mcp/tools_test.go:419`) — a caller
      without `admin:users` gets rejected before any DB call.

- [ ] T2. `TestToolSetAccountMode_HappyPath_Local` and `TestToolSetAccountMode_HappyPath_Hosted` —
      an admin caller flips an existing active account's mode both directions; assert the DB row's
      `mode` column and the tool's JSON result; for the `local` case, seed the store's TTL-exempt set
      via `WithAbsoluteTTLExempt` first (mirroring `internal/db/store_test.go:416`) so the exemption
      check passes.

- [ ] T3. `TestToolSetAccountMode_RejectsInvalidMode` — `mode="bogus"` is rejected with a validation
      error and no DB write occurs.

- [ ] T4. `TestToolSetAccountMode_UserNotFound` — mirroring
      `TestToolSetAccountSend_UserNotFound` (`internal/mcp/tools_test.go:470`) — an unknown
      `telegram_id` returns an actionable error, not a silent success.

- [ ] T5. `TestToolSetAccountMode_NoActiveSession` — mirroring
      `TestToolSetAccountSend_NoActiveSession` (`internal/mcp/tools_test.go:490`) — a known user with
      no active `telegram_accounts` row (never connected, or previously revoked) gets a hard error
      when either `mode` value is requested; zero DB rows affected must not produce `OK: true`.

- [ ] T6. `TestToolSetAccountMode_RefusesLocalWithoutTTLExemption` — an admin sets `mode="local"` for
      an active account whose `telegram_id` is not in the store's TTL-exempt set; assert the call is
      refused with an error mentioning `SESSION_TTL_EXEMPT_TG_IDS`, and that the row's `mode` column
      is left unchanged (query the DB directly after the call to confirm no write happened).

- [ ] T7. `TestToolSetAccountMode_HostedNeverRequiresExemption` — an admin sets `mode="hosted"` for a
      non-exempt account and it succeeds — the exemption check only ever gates `mode="local"`.

- [ ] T8. `internal/db/store_test.go`: `TestSetAccountMode` covering both the successful update
      (active row) and the zero-rows-affected case (no active row for that user), mirroring the
      existing `SetSendEnabled` tests in that file; `TestIsModeExempt` covering both a Telegram id
      present in and absent from a store constructed via `WithAbsoluteTTLExempt`.

- [ ] T9. `internal/mcp/annotations_test.go` and `internal/mcp/output_schema_test.go`: add
      `{"set_account_mode", first(s.toolSetAccountMode()), ...}` rows alongside the existing
      `set_account_send` rows so the new tool's annotations and output schema are covered by the same
      table-driven checks as every other tool.

- [ ] T10. `go vet ./...`, `golangci-lint run`, `go fmt ./...` all pass on the changed files, per
      CONTRIBUTING.md conventions.

## Rollback

The change is purely additive at the API and schema level: a new `Store` method, a new accessor, one
new MCP tool, one new result type, two new constants, and a new registration line. No migration runs
and no existing behavior is altered, so rollback is a plain revert:

1. Revert the PR (single squash-merged commit per repo convention) to remove the new tool, its
   registration, and its `Store` methods.
2. No data cleanup is needed: any `mode` values already written by `set_account_mode` before the
   revert are ordinary column values, identical in shape to ones written by the old gitops `Job` —
   `GetAccountMode` and the bridge's mode check keep working against them unchanged either way.
3. If the tool shipped a bad TTL-exemption refusal that blocked legitimate operators before the
   revert lands, the pre-existing gitops-`Job` / manual-`UPDATE` path documented in
   `docs/local-bridge.md` / `docs/runbook.md` remains available as a fallback throughout — this
   proposal does not remove or disable it.
