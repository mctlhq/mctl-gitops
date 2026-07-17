# Tasks: issue-294-feat-agents-add-voice-message-support-to

- [ ] 1. Add `"voice"` to `ValidMediaTypes` in `internal/telegram/send_media.go`
      — DoD: `ValidMediaTypes["voice"] == true`; `go vet` / existing tests
      still pass unmodified.
- [ ] 2. Implement the OGG/Opus content sniff (e.g. `isOggOpus(data []byte) bool`
      in `internal/telegram/send_media.go`) checking for the `OggS` page
      capture pattern followed by an `OpusHead` identification packet in the
      first Ogg page (depends on 1) — DoD: pure function, unit-tested
      against a valid minimal Opus-in-Ogg fixture (accept), and WAV/MP3/
      plain-text/truncated-Ogg-without-OpusHead fixtures (all reject).
- [ ] 3. Add `durationSeconds int` parameter to `buildInputMedia` and
      `SendMedia` in `internal/telegram/send_media.go`; add the `voice` case
      to `buildInputMedia` returning `InputMediaUploadedDocument` with
      `DocumentAttributeAudio{Voice: true, Duration: durationSeconds}` and no
      filename attribute; add `"voice"` → `"voice.ogg"` to
      `defaultUploadName`; call `isOggOpus` in `SendMedia`'s real-send branch
      for `mediaType == "voice"` and return an actionable error (no upload)
      when it fails (depends on 2) — DoD: `buildInputMedia("voice", ...)`
      produces the expected attribute shape; a non-Opus payload with
      `media_type: "voice"` and `realSend: true` errors before
      `uploader.Upload` is reachable.
- [ ] 4. Update every existing caller of `SendMedia`/`buildInputMedia` for the
      new `durationSeconds` parameter (`internal/mcp/media_tools.go`'s
      `toolSendMedia`, `cmd/local/daemon.go`'s `dispatchCall` `send_media`
      case) to compile with the new signature, passing `0` until tasks 5-6
      wire it up for real (depends on 3) — DoD: `go build ./...` succeeds.
- [ ] 5. Add `duration_seconds` as an optional numeric input to the
      `send_media` MCP tool schema in `internal/mcp/media_tools.go`
      (`mcplib.WithNumber`), parsed via the existing `intArg` helper;
      validate it is rejected when supplied with `media_type != "voice"` and
      when negative; update the `media_type` validation error message and
      the tool's `mcplib.WithDescription` to list `"voice"` and document the
      OGG/Opus + `duration_seconds` requirements; thread the parsed value
      into both the draft-branch and real-send-branch `telegram.SendMedia`
      calls (depends on 4) — DoD: schema reflects `voice`/`duration_seconds`;
      invalid combinations return an `mcplib.NewToolResultError` before any
      gate evaluation or I/O.
- [ ] 6. Mirror the same field in the Local Bridge daemon: add
      `DurationSeconds int `json:"duration_seconds"`` to the `send_media`
      case's `args` struct in `cmd/local/daemon.go` and pass it through to
      `tg.SendMedia(...)` (depends on 4) — DoD: a `send_media` call with
      `media_type: "voice"` dispatched through the daemon produces the same
      `DocumentAttributeAudio` shape as the hosted path.
- [ ] 7. Confirm round-trip parity: manually trace (or add a targeted test)
      that a document built by task 3's `voice` branch is classified back as
      `media_type: "voice"` with the correct `Duration` by `DecodeMediaInfo`
      in `internal/telegram/messages.go` (no production code change expected
      here — this is a verification task) (depends on 3) — DoD: confirmed in
      test or written note in the PR description; add a regression test only
      if a gap is found.

## Tests

- [ ] T1. `TestBuildInputMedia_Voice` (`internal/telegram/send_media_test.go`)
      — asserts `buildInputMedia("voice", ...)` returns
      `*tg.InputMediaUploadedDocument` with exactly one
      `*tg.DocumentAttributeAudio{Voice: true, Duration: N}` attribute and no
      `DocumentAttributeFilename`.
- [ ] T2. Ogg/Opus sniff table test (`internal/telegram/send_media_test.go`
      or a new `oggsniff_test.go`) — valid minimal Opus-in-Ogg header
      accepted; non-Ogg (WAV/MP3/plain text) rejected; Ogg-container-but-
      non-Opus (e.g. Vorbis `OggS` + `\x01vorbis` identification packet)
      rejected; truncated/empty input rejected without panicking.
- [ ] T3. `TestSendMedia_VoiceRejectsNonOpus` — `SendMedia(ctx, nil, "@bob",
      "voice", <non-opus bytes>, "", "audio/mpeg", "", true, "", nil, 0)`
      returns an error and (implicitly, since `c` is `nil`) never reaches the
      uploader.
- [ ] T4. `TestSendMedia_VoiceDryRunShape` — mirrors
      `TestSendMedia_DryRunShape` for `media_type: "voice"`: `realSend=false`
      returns `sent=false`, `mode="draft"`, echoes `media_type: "voice"`,
      performs no I/O, regardless of payload validity (draft path must not
      sniff/validate bytes it never received).
- [ ] T5. `TestToolSendMedia_DurationSecondsRejectedForNonVoice`
      (`internal/mcp/send_media_test.go`) — `duration_seconds` set with
      `media_type: "photo"` (or any non-voice type) returns a tool error
      before gate evaluation.
- [ ] T6. `TestToolSendMedia_DurationSecondsRejectedWhenNegative` — negative
      `duration_seconds` with `media_type: "voice"` returns a tool error.
- [ ] T7. `TestToolSendMedia_GateBlockedReturnsDraftPreview_Voice` — mirrors
      `TestToolSendMedia_GateBlockedReturnsDraftPreview_FileBase64` /
      `TestToolSendMedia_GateBlockedNeverFetchesURL` for
      `media_type: "voice"`: gate-denied call returns a dry-run preview and
      never fetches `file_url` or decodes `file_base64` (same invariant,
      new media type).
- [ ] T8. Local Bridge dispatch test (wherever `cmd/local/daemon.go`'s
      `dispatchCall` `send_media` case is exercised today, or a new test if
      none exists) — a `voice` call through `dispatchCall` produces a
      `tg.SendMediaResult` with `media_type: "voice"`, exercising the same
      OGG/Opus rejection as the hosted path.
- [ ] T9. Round-trip regression (from task 7, only if a gap is found) —
      feed a `buildInputMedia("voice", ...)`-shaped attribute list into
      `DecodeMediaInfo` (via a constructed `*tg.MessageMediaDocument`) and
      assert `MediaType == "voice"` and `Duration` matches.

## Rollback

- The change is additive and gated entirely by the `media_type` value —
  reverting is a single revert of the PR (or the squash-merge commit per
  this repo's `CLAUDE.md` workflow) with no data migration to undo: no
  schema changes, no persisted voice-specific state, and no change to the
  request/response shape for `photo`/`video`/`document`/`animation`.
- If only the OGG/Opus sniff proves too strict in production (false
  rejections of valid Opus streams) while the rest of the feature is sound,
  the narrower rollback is to relax/remove the `isOggOpus` call in
  `SendMedia`'s `voice` branch (task 3) in a follow-up patch, rather than
  reverting the whole feature — the attribute-building and schema/tool
  changes are independent of the sniff and do not need to be undone
  together.
- No feature flag is introduced; `ValidMediaTypes["voice"]` being present is
  the sole activation switch, consistent with how `animation` (#287/#293)
  shipped without a flag.
