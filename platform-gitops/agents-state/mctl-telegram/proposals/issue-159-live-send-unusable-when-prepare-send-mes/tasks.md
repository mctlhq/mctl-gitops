# Tasks: issue-159-live-send-unusable-when-prepare-send-mes

- [ ] 1. Implement `toolPrepareSendMessage()` in `internal/mcp/tools.go` — DoD:
  method exists on `*Server`; tool is registered with
  `mcplib.WithReadOnlyHintAnnotation(true)` and no destructive annotation; accepts
  `peer` (required) and `text` (required); returns `tool_error` when either is
  empty; applies `s.Limiter.AllowPeer(id, peerRedacted, audit.PeerSendCap,
  audit.PeerWindow)` and returns `tool_error` on limit exhaustion; calls
  `HashSendPayload(peer, text)` then `s.Confirms.Issue(id.UserID, "send", hash)`;
  returns JSON `{confirmation_id, peer_redacted, expires_at, payload_hash}` on
  success; audits under event `prepare_send_message` on success and
  `prepare_send_message:rate_limited` on limit hit; does NOT call `Pool.Borrow`
  or `s.bridgeCall`; `go vet ./internal/mcp/...` passes.

- [ ] 2. Register `toolPrepareSendMessage()` in `internal/mcp/server.go` (depends
  on 1) — DoD: `srv.AddTool(s.toolPrepareSendMessage())` is added in
  `HTTPHandler()` immediately after the `srv.AddTool(s.toolSendMessage())` call
  (line 75); the server starts without error; an MCP `tools/list` call returns a
  tool named `prepare_send_message` with `readOnly: true` in the annotations
  block.

- [ ] 3. Improve `send_message` dry-reason for missing/expired confirmation token
  in `internal/mcp/tools.go` — DoD: in the `default` branch of the `Consume`
  error switch inside `toolSendMessage()` (currently tools.go line 299), the
  `dryReason` string is updated to read
  `"confirmation_id not found, expired, or already used — call prepare_send_message to obtain a fresh token"`;
  the `ErrConfirmationMismatch` and `ErrConfirmationWrongUser` branch messages are
  left unchanged; `go vet ./internal/mcp/...` passes.

- [ ] 4. Update `send_message` tool description to mention the two-step flow and
  `prepare_send_message` (depends on 1 and 3) — DoD: the description string in
  `toolSendMessage()` (tools.go line 250) includes a paragraph explaining that
  `prepare_send_message` can be called first to obtain a `confirmation_id` (read-
  only, valid 5 minutes), and that omitting `confirmation_id` applies the per-peer
  rate limit directly; all existing description text is preserved.

## Tests

- [ ] T1. Add `TestToolPrepareSendMessage_Success` to
  `internal/mcp/tools_test.go`: construct a `Server` with an in-memory store, a
  `ConfirmStore`, and a nil `Limiter`; call the `toolPrepareSendMessage` handler
  with `peer="@testuser"` and `text="hello"`; assert the result is not a
  `tool_error`; unmarshal the JSON content; verify `confirmation_id` starts with
  `"cs_"` and has length 35; verify `peer_redacted` equals
  `telegram.RedactPeer("@testuser")`; verify `expires_at` is in the future;
  verify `payload_hash` equals `HashSendPayload("@testuser", "hello")`; verify the
  issued token can be consumed by `s.Confirms.Consume(id, userID,
  HashSendPayload("@testuser", "hello"))` without error.

- [ ] T2. Add `TestToolPrepareSendMessage_RateLimited` to
  `internal/mcp/tools_test.go`: construct a `Server` with a `RateLimiter` that
  has exhausted the per-peer bucket for the test identity and peer; call the
  handler; assert the result is a `tool_error`; assert no token was issued
  (confirm store remains empty).

- [ ] T3. Add `TestToolPrepareSendMessage_MissingArgs` to
  `internal/mcp/tools_test.go`: call the handler with an empty `peer` and/or
  empty `text`; assert a `tool_error` is returned without panicking.

- [ ] T4. Add `TestSendMessage_ExpiredConfirmationDryReason` to
  `internal/mcp/tools_test.go`: call `s.Confirms.Issue(userID, "send",
  HashSendPayload(peer, text))` directly; advance the ConfirmStore clock past
  `ConfirmationTTL`; invoke the `send_message` handler with the expired
  `confirmation_id`; assert the result JSON contains a `dry_reason` field whose
  value contains the substring `"prepare_send_message"`.

- [ ] T5. Add `TestHTTPHandler_ToolList_PrepareSendMessage` to
  `internal/mcp/tools_test.go` (or a new integration-style test): call
  `s.HTTPHandler()` and issue an HTTP `POST /mcp` request with
  `method: "tools/list"`; parse the response; assert a tool named
  `"prepare_send_message"` is present; assert its annotations include
  `readOnly: true`.

## Rollback

1. Remove `srv.AddTool(s.toolPrepareSendMessage())` from `HTTPHandler()` in
   `internal/mcp/server.go`.
2. Delete the `toolPrepareSendMessage()` method from `internal/mcp/tools.go`.
3. Optionally revert the dry-reason string in `toolSendMessage()` (task 3) and the
   description update (task 4) — neither has functional impact if left in place.

No database changes were made; the `ConfirmStore` is in-memory and any
outstanding send confirmation tokens expire within 5 minutes of the deploy.
Rollback can be accomplished by reverting a single feature commit and re-deploying.
No multi-step migration or data backfill is required.
