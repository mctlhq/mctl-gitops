# Tasks: issue-70-add-user-friendly-error-message-catalog

- [ ] 1. Create `internal/mcp/errorcatalog.go` with the `catalogEntry` type, the
  `mtprotoErrCatalog` map, and the `floodWaitSeconds` helper.
  DoD: file compiles; `go vet ./internal/mcp/...` passes; catalog map contains entries
  for PEER_ID_INVALID, USERNAME_INVALID, USERNAME_NOT_OCCUPIED, CHAT_FORBIDDEN,
  CHAT_WRITE_FORBIDDEN, USER_BANNED_IN_CHANNEL, MESSAGE_ID_INVALID, MSG_ID_INVALID,
  INPUT_USER_DEACTIVATED, PHONE_NUMBER_INVALID, CHANNEL_PRIVATE,
  USER_NOT_PARTICIPANT; `floodWaitSeconds("FLOOD_WAIT_30")` returns `(30, true)` and
  `floodWaitSeconds("FLOOD_WAIT_3600")` returns `(3600, true)`.

- [ ] 2. Implement `mtprotoErrResult(tool string, err error) *mcplib.CallToolResult`
  in `internal/mcp/errorcatalog.go`. (depends on 1)
  DoD: function uses `errors.As` to extract `*tgerr.Error`; emits `slog.Warn` with
  `"code"` and `"rpc_code"` fields before returning a friendly result; returns `nil`
  for non-tgerr errors and for unrecognized codes; FLOOD_WAIT and SLOWMODE_WAIT
  return a `mcplib.NewToolResultError` whose content is valid JSON containing
  `"error"`, `"message"`, `"retry_after_seconds"`, and `"action"` fields; catalog
  entries return a plain-string `mcplib.NewToolResultError`.

- [ ] 3. Edit `borrowErrResult()` in `internal/mcp/tools.go` to call
  `mtprotoErrResult` between the existing `sessionErrText` check and the final
  `toolErr` fallback. (depends on 2)
  DoD: diff is three lines added (one `if res := mtprotoErrResult(...); res != nil`
  block); all existing session-error unit tests pass without modification;
  `go vet ./...` and `golangci-lint run` pass.

- [ ] 4. Confirm `slog.Warn` field names in `mtprotoErrResult` do not collide with
  existing slog field names used in `audit()` in `internal/mcp/tools.go`. (depends on 2)
  DoD: code review confirms no field-name collision; the `"code"` field name appears
  nowhere else in the same log call path; no changes to `internal/audit/redact.go`
  are required because MTProto code strings contain no user data.

## Tests

- [ ] T1. Unit test `TestFloodWaitSeconds` in `internal/mcp/errorcatalog_test.go`:
  table-driven; covers `FLOOD_WAIT_0` → `(0, true)`, `FLOOD_WAIT_30` → `(30, true)`,
  `FLOOD_WAIT_3600` → `(3600, true)`, `SLOWMODE_WAIT_45` → `(45, true)`,
  `PEER_ID_INVALID` → `(0, false)`, `""` → `(0, false)`, `FLOOD_WAIT_` → `(0,
  false)` (no suffix), `FLOOD_WAIT_abc` → `(0, false)` (non-numeric suffix).

- [ ] T2. Unit test `TestMtprotoErrResultCatalog` in `internal/mcp/errorcatalog_test.go`:
  for each catalog key, construct a `tgerr.New(400, key)` and assert that
  `mtprotoErrResult("test_tool", err)` returns a non-nil `IsError` result whose
  content does not contain the raw MTProto code string.

- [ ] T3. Unit test `TestMtprotoErrResultFloodWait` in `internal/mcp/errorcatalog_test.go`:
  construct `tgerr.New(420, "FLOOD_WAIT_30")`; assert result is non-nil and
  `IsError`; unmarshal content as JSON; assert `retry_after_seconds == 30`,
  `error == "flood_wait"`, `message` is a non-empty string, `action` is a non-empty
  string.

- [ ] T4. Unit test `TestMtprotoErrResultSlowmodeWait` in `internal/mcp/errorcatalog_test.go`:
  construct `tgerr.New(400, "SLOWMODE_WAIT_60")`; same JSON assertions with
  `retry_after_seconds == 60` and `error == "slowmode_wait"`.

- [ ] T5. Unit test `TestMtprotoErrResultUnknownCode` in `internal/mcp/errorcatalog_test.go`:
  construct `tgerr.New(400, "SOME_UNKNOWN_CODE_XYZ")`; assert `mtprotoErrResult`
  returns `nil` so the caller falls through to `toolErr`.

- [ ] T6. Unit test `TestMtprotoErrResultNonTgerr` in `internal/mcp/errorcatalog_test.go`:
  pass `errors.New("plain go error")`; assert `mtprotoErrResult` returns `nil`.

- [ ] T7. Unit test `TestBorrowErrResultSessionSentinelsUnchanged` in
  `internal/mcp/tools_test.go` (or extend existing): verify that
  `borrowErrResult("t", db.ErrSessionRevoked)` still returns the existing session
  revoked message string unchanged — regression guard for the session path.

- [ ] T8. Unit test `TestBorrowErrResultFloodWait` in `internal/mcp/tools_test.go`:
  wrap `tgerr.New(420, "FLOOD_WAIT_30")` with `fmt.Errorf("list_dialogs: %w", ...)`;
  assert `borrowErrResult("list_dialogs", err)` returns a non-nil `IsError` result
  containing `"retry_after_seconds"`.

## Rollback

The catalog is a purely additive, self-contained change confined to two files:
`internal/mcp/errorcatalog.go` (new) and a four-line edit to
`internal/mcp/tools.go`.

To roll back:

1. `git revert <merge-commit>` — restores `borrowErrResult` to its prior form and
   removes `errorcatalog.go`.
2. No database migrations, configuration changes, or external API changes are
   involved.
3. After rollback, FLOOD_WAIT and other MTProto errors revert to raw tgerr strings
   in tool responses. No user data is lost; no stored state is affected.
