# Tasks: issue-278-get-messages-hard-cap-of-200-messages-no

- [ ] 1. Fix limit clamp in `GetMessages` and `GetUnreadMessages`
  (`internal/telegram/messages.go` lines 239 and 28) — change
  `if limit <= 0 || limit > 200 { limit = 50 }` to
  `if limit <= 0 { limit = 50 } else if limit > 200 { limit = 200 }` in both
  functions.
  DoD: `go vet ./...` passes; existing unit tests in `internal/telegram/messages_test.go`
  continue to pass; a new table-driven test covering limit=0, limit=1, limit=200,
  limit=201, and limit=500 verifies the clamp outputs 50, 1, 200, 200, 200
  respectively.

- [ ] 2. Add `beforeID int` parameter to `GetMessages`
  (`internal/telegram/messages.go` line 235) — update the function signature and
  pass `OffsetID: beforeID` in all three `MessagesGetHistoryRequest` call sites
  (lines 273-276, 290-293, 302-305). (depends on 1)
  DoD: function compiles; all three call sites in the function body pass
  `OffsetID`; callers in `internal/mcp/tools.go` (line 423) and
  `cmd/local/daemon.go` (line 323) are updated to supply the new argument;
  `go build ./...` passes with no unused-variable or type-mismatch errors.

- [ ] 3. Add `NextBeforeID *int` to `messagesResult`
  (`internal/mcp/tools.go` line 1124) — add the field with
  `json:"next_before_id,omitempty"`.
  DoD: `messagesResult` struct compiles; the JSON Schema derived by
  `mcplib.WithOutputSchema[messagesResult]()` includes `next_before_id` as an
  optional integer field (verify with the existing `output_schema_test.go`
  pattern).

- [ ] 4. Update `toolGetMessages` handler in `internal/mcp/tools.go`
  (function starting line 376) — parse `before_id` via
  `intArg(args, "before_id", 0)`, pass it to `telegram.GetMessages`, and
  populate `result.NextBeforeID` using a min-ID scan over the returned slice
  when `len(msgs) == limit`. (depends on 2, 3)
  DoD: handler compiles; when `before_id` is absent or zero the response is
  identical to current output (no `next_before_id` field if fewer than `limit`
  messages are returned); when `before_id` is set the `MessagesGetHistoryRequest`
  carries `OffsetID` equal to the supplied value (verifiable via unit test with
  a mock API or integration test).

- [ ] 5. Add `before_id` to the `get_messages` MCP tool schema
  (`internal/mcp/tools.go` line 393-399) — add
  `mcplib.WithNumber("before_id", mcplib.Description("..."))` and update the
  `WithDescription` string to document `before_id` and `next_before_id`.
  (depends on 4)
  DoD: tool description and schema match; `go build ./...` clean; manual
  inspection of the rendered tool description shows both the new input parameter
  and the output field documented.

- [ ] 6. Update Local Bridge daemon `cmd/local/daemon.go` — in the
  `"get_messages"` case of `dispatchCall` (line 309), add `BeforeID int
  \`json:"before_id"\`` to the args struct; forward it as the new `beforeID`
  argument to `tg.GetMessages`; compute and emit `next_before_id` in the
  response JSON using the same min-ID logic as the hosted path. (depends on 2)
  DoD: bridge daemon compiles; manual test with `mctl-telegram-local` against a
  live account confirms `before_id` is honoured and `next_before_id` is returned
  when a full page is available.

## Tests

- [ ] T1. **Unit: limit clamp** — table-driven test in
  `internal/telegram/messages_test.go` exercising the new clamp logic for
  `GetMessages` (and optionally `GetUnreadMessages`) with inputs 0, -1, 1, 200,
  201, 500; assert the effective limit passed to `MessagesGetHistoryRequest` is
  50, 50, 1, 200, 200, 200 respectively. A fake `tg.MessagesMessages` response
  with enough fake messages can be returned from a stub to avoid needing a live
  Telegram connection.

- [ ] T2. **Unit: `before_id` plumbing** — test in
  `internal/telegram/messages_test.go` (or a new
  `internal/telegram/messages_pagination_test.go`) that constructs a fake
  `MessagesGetHistoryRequest` recorder, calls `GetMessages` with
  `beforeID=12345`, and asserts `OffsetID` is 12345 in the recorded request.

- [ ] T3. **Unit: `next_before_id` computation** — test in
  `internal/mcp/tools_test.go` (following patterns in the existing
  `TestToolGetMessages`-style tests if present) that:
  - When `len(msgs) == limit`, `next_before_id` equals `min(msg.ID)` across the
    returned slice.
  - When `len(msgs) < limit`, `next_before_id` is absent from the JSON.
  - When `len(msgs) == 0`, `next_before_id` is absent.

- [ ] T4. **Unit: bridge daemon args** — test in `cmd/local/daemon_test.go`
  (following `TestDispatchCall`-style patterns if present) that constructs a
  bridge `Envelope` with `before_id` in the args JSON, calls `dispatchCall`, and
  asserts:
  - `GetMessages` was called with the correct `beforeID`.
  - The JSON response contains `next_before_id` when a full page was returned.

- [ ] T5. **Integration (optional, live account)** — manual or semi-automated
  test against a test Telegram account with a conversation of at least 400
  messages: call `get_messages` with no `before_id`, verify `next_before_id` is
  present; call again with that value as `before_id`, verify a different,
  non-overlapping batch of messages is returned; repeat until `next_before_id` is
  absent; verify the union of all batches covers the full conversation.

## Rollback

The change is additive: `before_id=0` produces the same wire call as today.

To roll back if something goes wrong after deployment:

1. Revert the commits touching `internal/telegram/messages.go`,
   `internal/mcp/tools.go`, and `cmd/local/daemon.go`.
2. Redeploy the server (standard release-please flow — tag, trigger
   `mctl-gitops/.github/workflows/release-deploy.yaml`).
3. Existing clients that did not yet use `before_id` are unaffected by the
   revert; clients already using the cursor will receive an error or a full page
   (no offset) until they drop the parameter.
4. No DB migrations were added, so no schema rollback is needed.
5. Local Bridge daemon users must rebuild from the reverted source. Older
   daemon binaries were already silently ignoring `before_id`, so they
   auto-degrade gracefully.
