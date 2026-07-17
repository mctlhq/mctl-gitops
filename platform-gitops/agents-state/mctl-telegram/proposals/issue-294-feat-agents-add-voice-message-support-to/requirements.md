# Add voice message support to send_media

## Context

`send_media` (added in #287/#293, `internal/telegram/send_media.go` +
`internal/mcp/media_tools.go`) currently sends `photo`, `video`, `document`,
and `animation` media types to Telegram peers. Telegram voice notes are a
distinct media kind: a `messageMediaDocument` whose document carries a
`DocumentAttributeAudio{Voice: true, Duration: ...}` attribute and an
OGG/Opus-encoded payload. Telegram clients render this attribute as a
waveform player, not a generic file attachment — sending a voice note today
requires routing it through `media_type: "document"`, which omits the audio
attribute and renders as a plain file, not a voice player.

The read side already understands voice notes: `DecodeMediaInfo` in
`internal/telegram/messages.go` (lines 98-105) classifies any
`DocumentAttributeAudio{Voice: true}` document as `media_type: "voice"` and
surfaces its `Duration`, and `internal/mcp/media_tools.go`'s
`get_media`/`prepare_get_media` already download voice notes fine — they key
only on the message's media location, not on media type. This issue closes
the gap on the send path so an agent can send a voice note that Telegram
renders correctly, mirroring the fidelity `send_media` already gives
photo/video/animation on the send side and voice already has on the read
side.

## User stories

- AS an agent operating a Telegram account via `send_media` I WANT to send a
  voice note that Telegram renders as a waveform player SO THAT the
  recipient sees a native voice message instead of a generic file
  attachment.
- AS an agent I WANT clear rejection of non-OGG/Opus audio for
  `media_type: "voice"` SO THAT I get an actionable error instead of a
  silently mis-rendered or broken message.
- AS an operator running the Local Bridge daemon (`cmd/local/daemon.go`) I
  WANT voice sends to work identically in local mode SO THAT accounts using
  the bridge have the same capability as hosted accounts.

## Acceptance criteria (EARS)

- WHEN a caller invokes `send_media` with `media_type: "voice"` and a
  real-send gate that is fully open THE SYSTEM SHALL upload the given bytes
  and send them as `tg.InputMediaUploadedDocument` carrying a
  `DocumentAttributeAudio{Voice: true, Duration: <duration_seconds>}`
  attribute.
- WHEN a caller invokes `send_media` with `media_type: "voice"` and the send
  gate denies (or is not fully open) THE SYSTEM SHALL return a dry-run
  preview (`sent: false`, `mode: "draft"`) with a `dry_reason`, without
  fetching `file_url` or decoding `file_base64` — matching the existing
  draft-by-default contract for photo/video/document/animation.
- WHEN `media_type: "voice"` is combined with `file_base64` or a
  `file_url`-fetched payload whose sniffed content is not OGG-container /
  Opus-codec audio THE SYSTEM SHALL reject the call with an actionable error
  before upload, and SHALL NOT send the message.
- IF `duration_seconds` is supplied for `media_type: "voice"` THEN THE
  SYSTEM SHALL pass it through as the `DocumentAttributeAudio.Duration`
  value (rounded/truncated to a non-negative integer number of seconds).
- IF `duration_seconds` is omitted for `media_type: "voice"` THEN THE SYSTEM
  SHALL default `Duration` to `0`, mirroring how `video`/`animation` already
  leave `Duration` at zero when unknown (`videoAttributes` in
  `send_media.go`).
- WHILE a message is being classified for read (`DecodeMediaInfo`) THE
  SYSTEM SHALL continue to report `media_type: "voice"` for any
  `DocumentAttributeAudio{Voice: true}` document, unchanged by this
  proposal — the send path must produce documents this existing read-path
  logic classifies correctly (round-trip parity), not a parallel
  classification.
- WHEN the Local Bridge daemon (`cmd/local/daemon.go`, `dispatchCall`'s
  `send_media` case) receives a `send_media` call with
  `media_type: "voice"` THE SYSTEM SHALL apply the same validation,
  MIME/format enforcement, and attribute-building behavior as the hosted
  path, so local-mode accounts get the same capability and the same
  rejections.
- WHEN `send_media`'s tool schema is inspected (its `mcplib.WithDescription`
  and `media_type`/new `duration_seconds` parameter docs) THE SYSTEM SHALL
  document `"voice"` as a valid `media_type` and describe the OGG/Opus
  requirement and `duration_seconds` semantics.
- IF `media_type: "voice"` is used with a `file_name` THEN THE SYSTEM SHALL
  accept it as an optional display name (mirroring photo/video/animation),
  since Telegram voice players do not use it for playback, but SHALL NOT
  require it (voice is not `document`).

## Out of scope

- Server-side transcoding of non-OGG/Opus audio (e.g. mp3, wav, m4a) to
  OGG/Opus. The caller must supply properly encoded OGG/Opus bytes; the
  server only detects and rejects, per the issue's explicit "Not in scope."
- Reading `duration_seconds` from container metadata automatically when the
  caller omits it (deferred — see Open questions).
- Any change to the read/download path (`get_media`, `prepare_get_media`,
  `DecodeMediaInfo`) — voice notes already download correctly today; this
  proposal only adds send-side support.
- Waveform-data generation/upload (Telegram's `DocumentAttributeAudio` also
  has an optional `Waveform []byte` field for the visual amplitude preview);
  not requested by the issue and Telegram renders a reasonable default
  without it.

## Open questions

- Should the server parse `duration_seconds` from the OGG container itself
  when the caller omits it, instead of defaulting to 0? The issue floats
  this ("or read from container metadata if feasible") but does not require
  it. Interpretation adopted: make `duration_seconds` optional, default to
  0, and defer container-metadata parsing to a follow-up — consistent with
  how `video`/`animation` already ship with `Duration: 0` when unknown
  (`send_media.go`'s `videoAttributes` doc comment explicitly accepts this
  tradeoff for agent-generated files).
- Exact MIME/format detection strategy: `http.DetectContentType` (used
  today by `resolveSendMediaBytes` for `file_base64`, and Telegram's
  server-supplied `Content-Type` header for `file_url`) recognizes the OGG
  container signature (`OggS`) but reports it as `application/ogg`, and
  does not distinguish an Opus-encoded stream from Vorbis/FLAC-in-Ogg.
  Interpretation adopted: add an explicit Ogg/Opus content sniff (checking
  for the `OpusHead` identification-packet magic within the first Ogg page)
  rather than trusting a caller- or origin-supplied MIME string, and reject
  anything that doesn't match — see design.md.
- Should `media_type: "voice"` reject a `file_name` outright (since
  Telegram's voice player ignores it) rather than silently accepting it as
  optional? Interpretation adopted: accept-but-ignore-for-display, matching
  the existing permissiveness for `photo`/`video`/`animation`'s optional
  `file_name`, to avoid a surprising new hard-error class.
- Should the caller-facing `duration_seconds` be a top-level `send_media`
  parameter (affecting `photo`/`video`/`document`/`animation` too, all of
  which currently leave `Duration` at 0) or scoped only to `voice`?
  Interpretation adopted: introduce it as a new optional parameter usable
  only when `media_type == "voice"` (validated), leaving video/animation's
  existing zero-duration behavior untouched — narrower blast radius, matches
  the issue's scope which only calls out voice.
