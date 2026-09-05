# Tasks: issue-510-add-self-identification-tool-get-my-iden

- [ ] 1. Add `identityResult` struct to `internal/mcp/tools.go` (near
      `sendStatusResult`/`identitiesResult`): `telegram_id int64`,
      `username string` (`omitempty`), `display_name string` (`omitempty`),
      `connected bool`. — DoD: struct compiles, matches the JSON shape in
      requirements.md's acceptance criteria (issue's example payload plus
      `connected`).

- [ ] 2. Implement `func (s *Server) toolGetMyIdentity() (mcplib.Tool,
      mcpserver.ToolHandlerFunc)` in `internal/mcp/tools.go`, placed after
      `toolGetMySendStatus` (depends on 1) — DoD:
      - Returns `mcplib.NewToolResultError("authentication required")` when
        `auth.From(ctx)` is nil.
      - Seeds `telegram_id`/`username` from `id.TelegramID`/`id.TelegramUsername`
        with no I/O.
      - When `s.Store != nil`, calls `s.Store.GetActiveAccount(ctx, id.UserID)`
        exactly once; on success sets `connected` and, when connected,
        prefers `acct.Username`/`acct.DisplayName` over the OIDC-claim
        username.
      - On a `GetActiveAccount` error, logs a warning (same style as
        `toolGetMySendStatus`'s "account read failed" branch) and still
        returns the identity-only fields with `connected=false`, no error.
      - No `requireScope` call (self-service, any authenticated identity).
      - No `s.audit(...)` call (matches `get_my_audit_log`/`get_my_send_status`
        precedent recorded in requirements.md Open questions).
      - Tool built with `WithTitleAnnotation`, `WithReadOnlyHintAnnotation(true)`,
        `WithDestructiveHintAnnotation(false)`, `WithOpenWorldHintAnnotation(false)`,
        `WithOutputSchema[identityResult]()`, and a `WithDescription` that
        states the `connected=false` fallback behavior explicitly.

- [ ] 3. Register the tool in `internal/mcp/server.go` next to the
      `toolGetMySendStatus` registration block (depends on 2) — DoD:
      `get_my_identity` appears in the running server's tool list.

- [ ] 4. Add `get_my_identity` to `internal/mcp/output_schema_test.go`'s
      table (depends on 2) — DoD: `TestToolOutputSchemas` passes and would
      fail if the outputSchema were dropped.

- [ ] 5. Add `get_my_identity` to `internal/mcp/annotations_test.go`'s table
      with `readOnly=true, destructive=false, openWorld=false` (depends on 2)
      — DoD: annotations test passes.

- [ ] 6. Update `README.md`'s tool table, `LLMS.md`, and
      `docs/public/llms.txt` with a `get_my_identity` entry, following the
      existing one-line style used for `get_my_audit_log`/`get_my_send_status`
      (depends on 2) — DoD: all three files mention the new tool; no
      contradictions with tools.go's actual description text.

## Tests

- [ ] T1. Unauthenticated call (no `auth.Identity` on context) returns an
      error result with "authentication required", matching every other
      self-service tool's test coverage.
- [ ] T2. Authenticated caller with `s.Store == nil` (or `GetActiveAccount`
      erroring) returns `telegram_id`/`username` from the auth identity,
      `connected=false`, `display_name` omitted, and no tool-level error.
- [ ] T3. Authenticated caller with an active connected account
      (`GetActiveAccount` returns `Connected:true` plus display_name/username)
      returns those account-row values for `username`/`display_name`,
      `connected=true`, and the correct `telegram_id`.
- [ ] T4. Authenticated caller who has signed in via the widget but never
      connected an MTProto session (`GetActiveAccount` returns
      `Connected:false`, empty display/username) still returns `telegram_id`
      and the OIDC-claim `username`, `connected=false`, `display_name` empty
      — this is the exact "guessing via heuristics" case the issue names.
- [ ] T5. `TestToolOutputSchemas` and the annotations table test both
      include and pass for `get_my_identity`.
- [ ] T6. `go vet` and `golangci-lint` clean on the changed files, per repo
      convention.

## Rollback

The change is additive only (one new tool, one new struct, one
registration line, table-only edits to two existing test files, doc
bullets). To roll back:

1. Revert the commit/PR that introduced `toolGetMyIdentity`,
   `identityResult`, its registration in `server.go`, and the
   `output_schema_test.go` / `annotations_test.go` table entries.
2. No data migration exists to reverse — no schema or stored data changed.
3. If the tool has already shipped to production and needs to be pulled
   without a full revert/redeploy, it can be treated as a normal tool
   removal (drop its `s.addTool(...)` registration in `server.go`) since it
   holds no state and no other tool depends on it.
