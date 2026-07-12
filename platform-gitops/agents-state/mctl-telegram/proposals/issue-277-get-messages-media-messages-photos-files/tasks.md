# Tasks: issue-277-get-messages-media-messages-photos-files

Phase 1 (tasks 1-5) is independently shippable. Phase 2 (tasks 6-10) depends on
tasks 1 and 2 for the `MediaInfo` struct and `decodeMediaInfo` function, and can be
developed in parallel with tasks 3-5.

---

## Phase 1 — Media metadata on Message

- [ ] 1. Define `MediaInfo` struct and add `MediaInfo *MediaInfo \`json:"media_info,omitempty"\``
  to `Message` in `internal/telegram/messages.go`.
  DoD: code compiles; existing `TestGetUnreadMessages_*` and `TestMatchUsername` tests
  in `internal/telegram/messages_test.go` pass unchanged; `go vet` clean.

- [ ] 2. Implement `decodeMediaInfo(media tg.MessageMediaClass) *MediaInfo` in
  `internal/telegram/messages.go`. Cover the full type switch: `nil` and
  `*tg.MessageMediaEmpty` return nil; `*tg.MessageMediaPhoto` returns `MediaType:
  "photo"` with width/height from the largest `tg.PhotoSizeClass` that is a
  `*tg.PhotoSize`; `*tg.MessageMediaDocument` scans attributes in priority order
  (sticker > voice > audio > video > animation > document) and populates `MimeType`,
  `Size`, `FileName`, `Duration`; remaining types return the appropriate string
  constant; unknown concrete types return `MediaType: "unsupported"`.
  DoD: unit tests T1-T5 (see Tests section below) pass; no external network calls.

- [ ] 3. Wire `decodeMediaInfo(msg.Media)` into the `decodeMessages` loop in
  `internal/telegram/messages.go` (depends on tasks 1, 2): assign result to
  `Message.MediaInfo`. (depends on 1, 2)
  DoD: a table-driven unit test in `messages_test.go` that constructs a
  `*tg.MessagesMessages` with a synthetic `*tg.MessageMediaDocument` confirms the
  returned `Message.MediaInfo` is non-nil and fields are correct.

- [ ] 4. Add a comment to `wrapMessages` in `internal/mcp/format.go` documenting that
  `MediaInfo *MediaInfo` is a pointer, so the value-copy of `Message` carries the
  pointer unchanged, and no further handling is required. Add test T6 to
  `internal/mcp/format_test.go` asserting `MediaInfo` is preserved after
  `wrapMessages`. (depends on 1)
  DoD: existing `TestWrapMessages_*` tests pass; T6 passes; no code change to the
  function body required (pointer is already copied correctly by the existing
  `out[i] = m` assignment).

- [ ] 5. Update the prose `Description` strings for `get_messages` and
  `get_unread_messages` in `internal/mcp/tools.go` to mention
  `media_info: {media_type, mime_type, file_name, size, duration}` in the output
  description. No code-path change needed; `WithOutputSchema[messagesResult]()` picks
  up the new field automatically via reflection once task 1 lands. (depends on 1, 3)
  DoD: description strings reference `media_info`; `TestOutputSchema_*` tests in
  `internal/mcp/output_schema_test.go` (if they exist) pass; `go vet` clean.

---

## Phase 2 — prepare_get_media / get_media tools

- [ ] 6. Add `MediaStore` struct (sync.Mutex-guarded map keyed by confirmation_id,
  with TTL matching `ConfirmationTTL`) and `MediaDownloadRef` struct to
  `internal/mcp/` (new file `internal/mcp/mediastore.go`). Implement `Set`,
  `Pop` (atomic get-and-delete), and `Sweep` methods. Wire `mediaStore *MediaStore`
  onto `Server` in `internal/mcp/server.go`; initialise in `mcp.New`.
  DoD: unit tests for `Set`/`Pop` covering normal path, expiry, and double-pop;
  `Sweep` removes expired entries; `go vet` clean.

- [ ] 7. Add `HashMediaPayload(peer string, messageID int64) string` to
  `internal/mcp/confirm.go`, following the pattern of `HashPinPayload`.
  DoD: unit test asserts same inputs produce same hash; different peer or messageID
  produce different hash.

- [ ] 8. Implement `toolPrepareGetMedia` in `internal/mcp/tools.go`. Inputs: `peer`
  (required), `message_id` (required). Flow: resolve peer via `ResolvePeerCached` or
  the dialog list (reuse the same peer resolution path as `GetMessages`); call
  `api.MessagesGetMessages` with the target message_id; classify media via
  `decodeMediaInfo`; return error if nil; populate `MediaDownloadRef` and call
  `mediaStore.Set` and `ConfirmStore.Issue`; return `prepareGetMediaResult`. Register
  the tool in `HTTPHandler`. (depends on 1, 2, 6, 7)
  DoD: test T7 passes; audit row recorded; bridgeCall routing for local-mode accounts
  present (routes to daemon, which may return an unsupported-tool error until task 10
  lands — that is acceptable).

- [ ] 9. Implement `toolGetMedia` in `internal/mcp/tools.go`. Inputs: `peer`
  (required), `message_id` (required), `confirmation_id` (required). Flow: consume
  confirmation via `ConfirmStore.Consume`; pop `MediaDownloadRef` from `mediaStore`;
  enforce `MediaDownloadMaxBytes` size cap (skip check if size is 0, i.e. unknown);
  `borrowWithRetry` with inner function that constructs the appropriate
  `tg.InputDocumentFileLocation` or `tg.InputPhotoFileLocation` and calls
  `api.UploadGetFile` in a loop accumulating chunks; base64-encode result; return
  `getMediaResult`. Register the tool in `HTTPHandler`. (depends on 6, 7, 8)
  DoD: tests T8, T9, T10 pass; size cap enforced before any MTProto call; audit row
  recorded; context cancellation exits the download loop; `go vet` clean.

- [ ] 10. Add `MEDIA_DOWNLOAD_MAX_BYTES` to `internal/config/config.go`. Parse as
  `int64`, default `20971520` (20 MB). Wire into `Server.MediaDownloadMaxBytes int64`
  via the existing config-to-server wiring in `cmd/server/main.go`. (depends on 9)
  DoD: `config_test.go` covers default and an override value; the field is present
  on `Server`; `toolGetMedia` reads it; `go vet` clean.

- [ ] 11. Implement `prepare_get_media` and `get_media` handlers in the Local Bridge
  daemon (`cmd/local/daemon.go`), mirroring the hosted-path logic using the local
  MTProto client. (depends on 8, 9)
  DoD: `bridgeCall` for both tools succeeds end-to-end in a local-mode integration
  test; the daemon returns the same JSON shape as the hosted path.

---

## Tests

- [ ] T1. `TestDecodeMediaInfo_Photo` in `internal/telegram/messages_test.go`: pass a
  `*tg.MessageMediaPhoto` with `Photo: &tg.Photo{ID: 1, AccessHash: 2,
  Sizes: []tg.PhotoSizeClass{&tg.PhotoSize{Type:"s",W:100,H:100},
  &tg.PhotoSize{Type:"m",W:320,H:320}}}`. Assert `MediaType=="photo"`,
  `Width==320`, `Height==320`.

- [ ] T2. `TestDecodeMediaInfo_DocumentFile` in `internal/telegram/messages_test.go`:
  pass `*tg.MessageMediaDocument` with `Document: &tg.Document{MimeType:
  "application/pdf", Size: 1024, Attributes: []tg.DocumentAttributeClass{
  &tg.DocumentAttributeFilename{FileName: "report.pdf"}}}`. Assert
  `MediaType=="document"`, `FileName=="report.pdf"`, `MimeType=="application/pdf"`,
  `Size==1024`.

- [ ] T3. `TestDecodeMediaInfo_Voice` in `internal/telegram/messages_test.go`: pass
  `*tg.MessageMediaDocument` with `DocumentAttributeAudio{Voice: true, Duration: 15}`.
  Assert `MediaType=="voice"`, `Duration==15`.

- [ ] T4. `TestDecodeMediaInfo_Sticker` in `internal/telegram/messages_test.go`: pass
  `*tg.MessageMediaDocument` with `DocumentAttributeSticker{}`. Assert
  `MediaType=="sticker"`.

- [ ] T5. `TestDecodeMediaInfo_Empty` in `internal/telegram/messages_test.go`:
  (a) `decodeMediaInfo(nil)` returns nil; (b) `decodeMediaInfo(&tg.MessageMediaEmpty{})`
  returns nil.

- [ ] T6. `TestWrapMessages_MediaInfoPreserved` in `internal/mcp/format_test.go`:
  construct a `telegram.Message{ID:1, Peer:"user:42", Text:"",
  MediaInfo: &telegram.MediaInfo{MediaType:"photo"}}`. Call `wrapMessages`. Assert
  `out[0].MediaInfo != nil` and `out[0].MediaInfo.MediaType == "photo"`.

- [ ] T7. `TestPrepareGetMedia_NoMedia` in `internal/mcp/tools_test.go` (or a new
  `internal/mcp/media_test.go`): mock `MessagesGetMessages` returning a text-only
  `*tg.Message` with nil `Media`. Assert the tool result `IsError == true` and the
  error message mentions "no downloadable media".

- [ ] T8. `TestGetMedia_SizeCapEnforced` in `internal/mcp/media_test.go`: set
  `Server.MediaDownloadMaxBytes = 1`. Store a `MediaDownloadRef{Size: 1048576}` in
  `mediaStore`. Call the `get_media` handler with a valid confirmation. Assert
  `IsError == true`, error mentions "size" and the cap value, and no `UploadGetFile`
  call was made.

- [ ] T9. `TestGetMedia_ConfirmationExpiry` in `internal/mcp/media_test.go`: call
  `prepare_get_media`, advance the confirmation store's clock past `ConfirmationTTL`,
  then call `get_media`. Assert `IsError == true` with a not-found/expired message.

- [ ] T10. `TestGetMedia_Download` in `internal/mcp/media_test.go`: mock
  `UploadGetFile` to return two calls: first `{Bytes: []byte{1,2,3,4}}`, second
  `{Bytes: []byte{}}` (EOF). Assert `get_media` returns `data` equal to the base64
  encoding of `[]byte{1,2,3,4}` and `size == 4`.

---

## Rollback

**Phase 1 rollback.** `MediaInfo` is additive. Revert the `Message` struct change
(remove `MediaInfo *MediaInfo`) and the `decodeMediaInfo` call in `decodeMessages`,
then redeploy. Existing MCP clients stop receiving `media_info` on the next request.
No database schema, no persistent state, no migration required.

**Phase 2 rollback.** The two new tools (`prepare_get_media`, `get_media`) and the
`mediaStore` are entirely in-memory. To roll back: remove the two `addTool` lines
from `HTTPHandler` in `server.go`, redeploy. Clients calling those tools receive a
standard MCP "tool not found" response. Any `MediaDownloadRef` entries in the old
pod's `mediaStore` are lost on pod shutdown, which is safe — they were short-lived
(TTL 10 min) and held no persistent state.

If a flawed `get_media` build causes Pool session exhaustion (e.g. a stuck
`borrowWithRetry`), the fix is to roll back the binary and restart the pod. The
per-download context timeout (60 s) is the primary in-process mitigation; if it
fails, a pod restart is always safe because all state is in-memory and short-lived.
