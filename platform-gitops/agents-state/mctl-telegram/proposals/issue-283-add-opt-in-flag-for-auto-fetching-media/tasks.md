# Tasks: issue-283-add-opt-in-flag-for-auto-fetching-media

- [ ] 1. Extract a shared `ExtractMediaLocation` helper in
  `internal/telegram/media_download.go` — DoD: a new package-level function
  `ExtractMediaLocation(msg *tg.Message) (*MediaFileLocation, error)` that
  mirrors the location-extraction switch block already in `PrepareMediaRef`
  (lines 124-143) but operates on an already-fetched `*tg.Message`. Update
  `PrepareMediaRef` to call `ExtractMediaLocation` instead of the inlined
  block. All existing `TestPrepareMediaRef` tests still pass.

- [ ] 2. Add `MediaData *string` field to `telegram.Message` (depends on 1) —
  DoD: `internal/telegram/messages.go` `Message` struct gains
  `MediaData *string \`json:"media_data,omitempty"\``. The field is never
  populated by `GetMessages` or `GetUnreadMessages` (it stays nil). JSON
  round-trip test confirms the field is absent when nil and present when set.

- [ ] 3. Add `GetMessagesRaw()` to `internal/telegram/messages.go` (depends on 2) —
  DoD: a new function `GetMessagesRaw(ctx, client, peerSpec, limit, beforeID,
  cache, userID) ([]Message, []*tg.Message, int, error)` that performs the same
  logic as `GetMessages` but also returns the raw `[]*tg.Message` slice from
  `decodeMessagesRaw()` (a new private helper that splits decode and wrap so
  raw access is possible). `GetMessages` is refactored to call `GetMessagesRaw`
  and discard the raw slice. All existing `GetMessages` tests still pass.

- [ ] 4. Create `internal/mcp/bulk_media.go` (depends on 1, 2, 3) — DoD: the file
  defines `const BulkMediaFetchCap = 5`, the `FetchMediaSummary` struct with
  fields `Fetched int`, `Skipped int`, `Cap int` (JSON snake_case), and a
  method `(s *Server) fetchMediaInline(ctx, userID int64, rawMsgs []*tg.Message,
  msgs []telegram.Message) (FetchMediaSummary, error)`. The method: iterates
  rawMsgs/msgs in parallel; calls `ExtractMediaLocation` for each; skips nil
  locations silently; skips items whose declared size exceeds
  `s.MediaDownloadMaxBytes`; once `fetched == BulkMediaFetchCap` increments
  `skipped` for all remaining downloadable items; for eligible items calls
  `s.borrowWithRetry` + `telegram.DownloadMedia` and on success writes
  base64-encoded bytes to `msgs[i].MediaData`; on download error increments
  `skipped` and logs at DEBUG; returns the summary. Unit tests cover: zero
  downloadable items (empty summary), cap reached (first 5 fetched, rest
  skipped), size-exceeded items (counted as skipped, not fetched),
  non-downloadable types (not counted anywhere).

- [ ] 5. Add `fetch_media` parameter to `toolGetMessages` (depends on 4) — DoD:
  `internal/mcp/tools.go` `toolGetMessages()` gains
  `mcplib.WithBoolean("fetch_media", mcplib.Description(...))`. When the
  handler reads `fetch_media=true`: (a) if account is in Local Bridge mode,
  return `toolErr("fetch_media=true is not supported in Local Bridge mode — use
  prepare_get_media and get_media per item instead")`; (b) otherwise call
  `GetMessagesRaw` instead of `GetMessages`, pass rawMsgs to `fetchMediaInline`,
  attach `FetchMediaSummary` to `messagesResult`. When `fetch_media` is absent
  or false the handler is byte-for-byte identical to today. The
  `mcplib.WithDescription` string is updated to document the parameter, the cap,
  and the cost implications. `WithOutputSchema[messagesResult]()` is unchanged
  (the struct is updated in task 6).

- [ ] 6. Extend `messagesResult` with `FetchMediaSummary` (depends on 5) — DoD:
  `internal/mcp/tools.go` `messagesResult` struct gains
  `FetchMediaSummary *FetchMediaSummary \`json:"fetch_media_summary,omitempty"\``.
  JSON output for a default (`fetch_media=false`) call contains no
  `fetch_media_summary` key. JSON output for a `fetch_media=true` call always
  contains the key (even when `fetched=0`). The `WithOutputSchema` reflection
  automatically includes the new optional field; no manual schema change needed.

- [ ] 7. Add `fetch_media` parameter to `toolGetUnreadMessages` (depends on 4, 6) —
  DoD: mirrors task 5 for `toolGetUnreadMessages`. The handler calls
  `telegram.GetUnreadMessages` (unchanged) to obtain `[]telegram.Message`, then
  calls `fetchMediaInline` if `fetch_media=true`. Because `GetUnreadMessages`
  does not expose raw `*tg.Message` objects today, a `GetUnreadMessagesRaw()`
  variant must also be added (same pattern as task 3). See open question 4 in
  requirements.md — confirm scope before starting this task.

- [ ] 8. Add audit-log coverage for `fetch_media=true` calls (depends on 5, 7) —
  DoD: the `s.audit()` call for `get_messages` logs an additional field
  `fetch_media_fetched` when `fetch_media=true` so operators can see how many
  items were downloaded per call. The field must be added to the `attrs` slice
  inside the `audit()` call only when non-zero (avoid inflating every audit row).
  The `internal/audit/redact.go` slog handler does not need changes (this is a
  count, not a sensitive value).

## Tests

- [ ] T1. `internal/telegram/media_download_test.go`: add a test for
  `ExtractMediaLocation` covering a photo message (returns non-nil loc, not a
  document), a document message (IsDocument=true), a poll message (returns nil,
  no error), and a Noforwards-flagged message (returns an error).

- [ ] T2. `internal/telegram/messages_test.go`: add a test for `GetMessagesRaw`
  confirming the raw `[]*tg.Message` slice has the same length as the decoded
  `[]telegram.Message` slice and that raw message IDs match decoded message IDs.

- [ ] T3. `internal/mcp/bulk_media_test.go` (new file): table-driven unit tests for
  `fetchMediaInline`: (a) all items non-downloadable -> `{0, 0, 5}`; (b) three
  downloadable items under cap -> `{3, 0, 5}`; (c) seven downloadable items ->
  `{5, 2, 5}`; (d) one item exceeds size cap -> `{0, 1, 5}` (or `{N-1, 1, 5}`);
  (e) download error on one item -> counts as skipped, not fetched.

- [ ] T4. `internal/mcp/tools_test.go`: extend the existing `TestGetMessages`
  table with a case for `fetch_media=false` (default, unchanged output shape)
  and a case for `fetch_media=true` with a stubbed `Pool.Borrow` that returns
  a page with one photo and one document: assert `fetch_media_summary` is
  present, `fetched=2`, `skipped=0`, and both messages have a non-empty
  `media_data`.

- [ ] T5. `internal/mcp/tools_test.go`: add a case for `fetch_media=true` on a
  Local Bridge mode account: assert the response is a tool error containing
  "Local Bridge mode".

## Rollback

All changes are backward-compatible: the new `fetch_media` parameter defaults
to false, the new `media_data` and `fetch_media_summary` JSON fields are
omitempty. Rolling back means reverting the commits that introduced
`bulk_media.go`, the parameter wiring in `tools.go`, the `MediaData` field on
`telegram.Message`, and `GetMessagesRaw`. No database schema changes or
migrations are involved. No environment variables are added. A simple `git
revert` of the feature commits restores the previous behavior for all callers.
