# Media Visibility in Messages: Surface Type Metadata and Add get_media Download Tool

## Context

The `Message` struct in `internal/telegram/messages.go` carries only `ID`, `Peer`,
`PeerTitle`, `From`, `Text`, and `Date`. The `decodeMessages` function in the same file
reads `.Message` (the text body) from each `tg.Message` but silently ignores the
`.Media tg.MessageMediaClass` field. When a Telegram message is a photo, document,
sticker, voice note, or video — and carries no caption — the returned `Message` has
an empty `Text` field with no other indicator that content was present. An MCP client
(or LLM assistant calling `get_messages`) cannot distinguish a media-only message from
a genuinely blank text message.

Telegram conversations routinely mix text and media: screenshots being discussed in
the next message, forwarded PDFs, voice notes, stickers. Dropping media presence
silently means any summary or analysis an LLM produces from `get_messages` output is
incomplete without the caller knowing it is incomplete. The issue asks for (1) at
minimum, media type and document attributes surfaced on `Message` so callers are not
blind to non-text content, and (2) ideally, a way to download the actual bytes for a
given `(peer, message_id)` via a tool pair that follows the existing
`prepare_pin_message` / `pin_message` two-step confirmation pattern in
`internal/mcp/tools.go`.

## User stories

- AS an MCP client (LLM assistant) I WANT to know the media type and basic attributes
  of every message SO THAT I can accurately describe conversation content to the user
  without silently omitting media messages.
- AS an MCP client I WANT to download the bytes of a specific media attachment SO THAT
  I can display or process a photo or file on behalf of the user.
- AS an operator I WANT media downloads to require a prepare-then-confirm step SO THAT
  potentially large or sensitive files are never transferred without explicit user intent.

## Acceptance criteria (EARS)

### Phase 1 — media metadata on Message

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaPhoto`, THEN the returned `Message.MediaInfo.MediaType` SHALL equal
  `"photo"`.

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaDocument` and the document has a `*tg.DocumentAttributeSticker`
  attribute, THEN `Message.MediaInfo.MediaType` SHALL equal `"sticker"`.

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaDocument` and the document has a `*tg.DocumentAttributeAudio`
  attribute with `Voice == true`, THEN `Message.MediaInfo.MediaType` SHALL equal
  `"voice"`.

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaDocument` and the document has a `*tg.DocumentAttributeVideo`
  attribute, THEN `Message.MediaInfo.MediaType` SHALL equal `"video"`.

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaDocument` and the document has a `*tg.DocumentAttributeAnimated`
  attribute, THEN `Message.MediaInfo.MediaType` SHALL equal `"animation"`.

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaDocument` and no specialising attribute matches, THEN
  `Message.MediaInfo.MediaType` SHALL equal `"document"`.

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaDocument`, THEN `Message.MediaInfo.MimeType` SHALL be populated
  from `tg.Document.MimeType`, `Message.MediaInfo.Size` SHALL be populated from
  `tg.Document.Size`, and `Message.MediaInfo.FileName` SHALL be populated from the
  `*tg.DocumentAttributeFilename.FileName` attribute if present (empty string when
  absent).

- WHEN `decodeMessages` processes a `*tg.Message` whose `Media` field is
  `*tg.MessageMediaDocument` and the document has a `*tg.DocumentAttributeAudio` or
  `*tg.DocumentAttributeVideo` attribute, THEN `Message.MediaInfo.Duration` SHALL be
  populated from the attribute's `Duration` field (seconds).

- WHEN a message has no media (`Media` is `nil` or `*tg.MessageMediaEmpty`), THEN
  `Message.MediaInfo` SHALL be `nil` and the JSON output SHALL omit the field
  entirely.

- WHEN `wrapMessages` in `internal/mcp/format.go` processes a `Message` with a
  non-nil `MediaInfo`, THEN it SHALL copy `MediaInfo` through unchanged; the field
  SHALL NOT be nil-ed out or overwritten.

- WHILE any `Message` has `MediaInfo != nil`, THE SYSTEM SHALL preserve all
  `MediaInfo` fields through the `messagesResult` JSON marshalling path so MCP clients
  receive them on the wire.

### Phase 2 — prepare_get_media / get_media tools

- WHEN an MCP client calls `prepare_get_media` with a valid `(peer, message_id)`
  referring to a message whose media is a photo or document, THE SYSTEM SHALL return a
  `confirmation_id` valid for 10 minutes plus `{peer_redacted, message_id, media_type,
  mime_type, file_name, size, expires_at}`.

- WHEN an MCP client calls `prepare_get_media` with a `(peer, message_id)` that has
  no downloadable media (text-only, unsupported type, or message not found), THE
  SYSTEM SHALL return a tool error that names the reason.

- WHEN an MCP client calls `get_media` with a valid `confirmation_id` and matching
  `(peer, message_id)` within 10 minutes, AND the file size does not exceed the
  configured cap (`MEDIA_DOWNLOAD_MAX_BYTES`, default 20971520 = 20 MB), THE SYSTEM
  SHALL return `{media_type, mime_type, file_name, size, data}` where `data` is the
  file bytes encoded as standard base64.

- WHEN an MCP client calls `get_media` and the resolved file size exceeds
  `MEDIA_DOWNLOAD_MAX_BYTES`, THE SYSTEM SHALL return a tool error that states the
  actual size and the cap, and SHALL NOT initiate any MTProto download.

- WHEN an MCP client calls `get_media` with an expired, already-consumed, or payload-
  mismatched `confirmation_id`, THE SYSTEM SHALL return a tool error.

- WHEN a `get_media` download is in flight and the context is cancelled, THE SYSTEM
  SHALL abort the download and return an error; it SHALL NOT leave the `Pool.Borrow`
  session open indefinitely.

- IF an account is in `local` mode, THEN `prepare_get_media` and `get_media` SHALL
  route through `bridgeCall` to the Local Bridge daemon, identical to the routing
  pattern used by `get_messages` and `pin_message` in `internal/mcp/tools.go`.

## Out of scope

- Uploading or sending media files to Telegram.
- HTTP streaming download URLs or signed short-lived download endpoints (no new HTTP
  routes; bytes are returned inline as base64 within the MCP tool response).
- Forwarded message metadata (`tg.MessageFwdHeader`).
- Detailed payload decoding for non-file media types (`*tg.MessageMediaGeo`,
  `*tg.MessageMediaContact`, `*tg.MessageMediaPoll`, `*tg.MessageMediaWebPage`): these
  are represented as their `media_type` string only; further field extraction is a
  follow-on feature.
- Thumbnail extraction or image resizing.
- Local Bridge daemon implementation for `prepare_get_media` / `get_media` (tracked
  as a follow-on task in the tasks file; the cloud-hosted path is the primary scope
  here).

## Open questions

1. What should the default per-download size cap be? The issue does not specify. This
   proposal uses 20 MB (20971520 bytes) as the default, controlled by
   `MEDIA_DOWNLOAD_MAX_BYTES`. If voice notes are the primary use case a lower cap is
   reasonable; if document sharing (PDFs, archives) is common the cap may need to be
   higher. The operator should be able to override via env var.

2. Should `get_media` return bytes as a base64 string in the JSON response body, or as
   a binary MCP resource content block? MCP 2025-03 defines resource content blocks,
   but the code uses `mark3labs/mcp-go v0.54.0` and it was not confirmed that binary
   resource blocks are fully supported in that version for tool results. This proposal
   assumes base64 in a JSON string; if the library supports binary resource blocks,
   that would reduce payload size and is preferred.

3. The `prepare_get_media` step must call `MessagesGetMessages` to look up the media
   location. This is one extra Telegram API call per prepare invocation. If the
   user-facing latency of the prepare step is a concern, the implementation could
   optionally accept a `file_reference` hint to skip the lookup — but that couples the
   caller to MTProto internals. The extra round trip is the simpler default.
