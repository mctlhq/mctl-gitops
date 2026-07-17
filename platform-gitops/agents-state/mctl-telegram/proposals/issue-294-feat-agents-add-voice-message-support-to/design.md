# Design: issue-294-feat-agents-add-voice-message-support-to

## Current state

`send_media` is implemented in two layers, both read during this
investigation:

- `internal/telegram/send_media.go` — the transport-agnostic core.
  - `ValidMediaTypes` (lines 23-28) is a `map[string]bool` gating
    `photo`/`video`/`document`/`animation`.
  - `SendMedia(...)` (lines 56-123) uploads bytes via `uploader.NewUploader`,
    builds a `tg.InputMediaClass` via `buildInputMedia`, and sends through
    `c.API().MessagesSendMedia`. It has a draft-by-default branch (lines
    63-75, no I/O when `realSend` is false) and a real-send branch.
  - `buildInputMedia(mediaType, uploaded, fileName, mimeType)` (lines
    153-184) is a pure function (no RPC) that switches on `mediaType` to
    build the right `tg.InputMediaClass`/attribute slice: `photo` →
    `InputMediaUploadedPhoto`; `video`/`animation`/`document` →
    `InputMediaUploadedDocument` with different `Attributes`. Comment at
    lines 146-152 documents that attribute *order* is load-bearing for
    `animation` because `DecodeMediaInfo` (the read side) classifies by
    first-matching attribute.
  - `defaultUploadName(mediaType)` (lines 130-141) supplies a generic
    filename when the caller gave none.
- `internal/mcp/media_tools.go` — the MCP tool boundary.
  - `toolSendMedia()` (lines 278-417) declares the `send_media` MCP tool:
    schema (`media_type` as a required free-text string, described inline,
    lines 316-319), argument extraction/validation (lines 344-363),
    send-gate evaluation (`evaluateSendGate` + `evaluateDirectSendLimiter`,
    lines 366-382) with a strict "denied → no I/O" contract, Local Bridge
    dispatch when the account is in local mode (lines 384-394), and the
    real-send path that resolves bytes only after the gate is confirmed
    open (`resolveSendMediaBytes`, lines 396-414, 423-441).
  - `resolveSendMediaBytes` (lines 423-441) is where MIME type is
    determined today: `http.DetectContentType` on the first 512 bytes for
    `file_base64`, or the fetch response's `Content-Type` header for
    `file_url` (via `telegram.FetchGuardedURL`,
    `internal/telegram/fetchmedia.go` lines 190-219). Neither path
    currently validates the detected/declared MIME type against
    `media_type` — `photo`/`video`/`document`/`animation` all accept
    whatever bytes arrive.
- `cmd/local/daemon.go`'s `dispatchCall` `"send_media"` case (lines
  492-546) is the Local Bridge daemon's mirror of the hosted real-send
  path: it decodes/fetches bytes locally (same size cap, same
  `http.DetectContentType`/`FetchGuardedURL` split) and calls the same
  `tg.SendMedia` core function. Its local `args` struct (lines 493-502) is
  a hand-maintained mirror of the fields `toolSendMedia` reads from
  `req.GetArguments()`.
- **Read side already supports voice.** `internal/telegram/messages.go`'s
  `DecodeMediaInfo` (lines 78-129) already classifies any
  `*tg.MessageMediaDocument` whose attributes include
  `*tg.DocumentAttributeAudio` with `Voice: true` as `media_type: "voice"`
  (lines 98-105), and extracts `Duration`. This is exercised by
  `internal/telegram/messages_test.go` (line 182,
  `&tg.DocumentAttributeAudio{Voice: true, Duration: 15}`). `get_media`/
  `prepare_get_media` (`internal/mcp/media_tools.go` lines 49-137,
  139-276) key strictly on `(peer, message_id)` and a download `Location`,
  not on media type, so downloading an existing voice note already works.
  This means the feature gap is send-only.
- `MediaInfo.MediaType` (messages.go lines 21-28) and `SendMediaResult`
  (send_media.go lines 33-44) both echo `media_type` as a plain string —
  no enum/type exists to update in a single place; `ValidMediaTypes` is the
  actual gate.
- Tests establish the pattern to extend: `internal/telegram/send_media_test.go`
  has pure-function `TestBuildInputMedia_*` tests per media type (photo,
  video, animation, document, invalid) that assert on the concrete
  `tg.InputMediaClass`/attribute shape without any RPC transport, plus
  `SendMedia`-level tests for dry-run shape, invalid type, missing peer, and
  real-send-requires-bytes. `internal/mcp/send_media_test.go` has
  `toolSendMedia`-level tests for validation, missing scope, and
  gate-blocked-returns-draft/never-fetches-URL invariants.

## Proposed solution

Extend the existing type/attribute machinery in place, rather than adding a
parallel "voice" code path, so voice inherits every existing invariant
(draft-by-default, gate ordering, upload cap, Local Bridge mirroring) for
free:

1. **`internal/telegram/send_media.go`**
   - Add `"voice": true` to `ValidMediaTypes`.
   - Add a `voice` case to `buildInputMedia` that returns
     `&tg.InputMediaUploadedDocument{File: uploaded, MimeType: mimeType,
     Attributes: []tg.DocumentAttributeClass{&tg.DocumentAttributeAudio{
     Voice: true, Duration: durationSeconds}}}`. No `DocumentAttributeFilename`
     is added for voice — Telegram's voice player does not use a filename,
     and omitting it keeps `DecodeMediaInfo`'s classification (which matches
     `DocumentAttributeAudio` unconditionally, "wins immediately", messages.go
     line 88 comment) unaffected either way.
   - `buildInputMedia` and `SendMedia` gain a `durationSeconds int`
     parameter (threaded from the new MCP-layer `duration_seconds` input,
     default 0 when unset/inapplicable). This is the minimal-diff option:
     every other media type ignores the new parameter, so no other call
     site's behavior changes. Update `defaultUploadName` with a `"voice"` →
     `"voice.ogg"` case for parity with the other types' generic names.
   - Add an OGG/Opus content-sniff helper, e.g. `isOggOpus(data []byte)
     bool`, in `send_media.go` (or a new small `internal/telegram/oggsniff.go`
     if it grows): confirm the first 4 bytes are `OggS` (Ogg page capture
     pattern) and that the identification packet payload — the first Ogg
     page's payload, which for a valid Opus stream starts with the 8-byte
     magic `OpusHead` — is present within the first page. `SendMedia`
     invokes this for `mediaType == "voice"` before uploading and returns a
     clear `fmt.Errorf("voice media must be OGG/Opus-encoded audio, got ...")`
     otherwise. This lives in the transport-agnostic core so both the
     hosted path and the Local Bridge daemon get it automatically (bridge
     calls the same `tg.SendMedia`).
2. **`internal/mcp/media_tools.go`**
   - Add `duration_seconds` as a new optional numeric input via
     `mcplib.WithNumber("duration_seconds", ...)`, parsed with the existing
     `intArg` helper (already used for `message_id`). Validate: if
     provided and `media_type != "voice"`, reject with an actionable error
     (keeps the parameter's blast radius scoped to voice, per
     requirements.md's open-question resolution); if negative, reject.
   - Extend the `media_type` validation error message and the tool's
     `mcplib.WithDescription` text to list `"voice"` and document the
     OGG/Opus requirement and `duration_seconds`.
   - Thread `durationSeconds` through to `telegram.SendMedia(...)` calls
     (both the draft branch, which just echoes metadata, and the real-send
     branch).
   - No change needed to `resolveSendMediaBytes`'s MIME detection
     mechanism itself — the new format check happens in `SendMedia`
     against the resolved bytes, which is where `buildInputMedia` already
     has access to the payload the uploader just consumed. (See
     Alternatives for why format-checking isn't done earlier at the
     `resolveSendMediaBytes` layer.)
3. **`cmd/local/daemon.go`**
   - Add `DurationSeconds int `json:"duration_seconds"`` to the `send_media`
     case's local `args` struct (line ~493-502) and pass it through to
     `tg.SendMedia(...)` (line 541). No other change: the daemon already
     calls the same core `tg.SendMedia`/`buildInputMedia`, so
     `ValidMediaTypes["voice"]` and the OGG/Opus sniff apply automatically
     once (1) lands.
4. **Tests** — extend the existing per-media-type table pattern:
   - `internal/telegram/send_media_test.go`: `TestBuildInputMedia_Voice`
     (asserts `DocumentAttributeAudio{Voice: true, Duration: N}` shape, no
     filename attribute), an OGG/Opus sniff unit test set (valid Opus
     header accepted; WAV/MP3/plain-text/truncated-Ogg-without-OpusHead
     rejected), and a `SendMedia`-level test that a non-Opus payload with
     `media_type: "voice"` errors before any upload call is reachable
     (mirrors `TestSendMedia_RealSendRequiresBytes`'s "fails loudly, no
     silent proceed" style).
   - `internal/mcp/send_media_test.go`: schema/validation tests for
     `duration_seconds` (rejected when `media_type != "voice"`, rejected
     when negative), and a gate/dry-run parity test
     (`TestToolSendMedia_GateBlockedReturnsDraftPreview` equivalent for
     `media_type: "voice"`) confirming the existing "denied gate never
     fetches/decodes" invariant holds for voice exactly like the other
     types.

## Alternatives

1. **Validate the OGG/Opus format at the MCP tool layer
   (`resolveSendMediaBytes`) instead of inside `telegram.SendMedia`.**
   Rejected: `resolveSendMediaBytes` doesn't know `media_type` today (it's
   a generic byte-resolution helper called identically for every media
   type), and, more importantly, the Local Bridge daemon (`cmd/local/daemon.go`)
   has its own independent byte-resolution code that does *not* go through
   `resolveSendMediaBytes` — putting the check in the hosted-only MCP layer
   would leave local-mode accounts unvalidated, violating the issue's "mirror
   dispatch" requirement. Putting it in the shared `telegram.SendMedia` core
   covers both dispatch paths from one place.
2. **Trust the caller-declared/sniffed generic MIME type
   (`application/ogg` from `http.DetectContentType`, or the origin's
   `Content-Type` header) instead of sniffing for the `OpusHead` codec
   identifier.** Rejected: the issue explicitly calls for enforcing
   "audio/ogg (with opus codec)", and an Ogg container can carry Vorbis,
   FLAC, or Speex instead of Opus — Telegram's voice player expects Opus
   specifically. A generic-MIME check would let container-correct-but-
   codec-wrong files through, producing a voice message Telegram may
   reject or mis-render. The extra ~10-line sniff is cheap and self-
   contained (no new dependency — the Opus identification header is a
   fixed 8-byte magic string at a fixed offset in the first Ogg page).
3. **Read `duration_seconds` from the OGG container's granule
   position/sample rate instead of taking it as a caller-supplied
   parameter.** Rejected for this iteration (see requirements.md Open
   questions): correct Ogg duration extraction means walking to the last
   page and computing `granule_position / sample_rate`, meaningfully more
   parsing logic than the identification sniff, for a field Telegram
   already tolerates as 0 (video/animation already ship with `Duration: 0`
   routinely, per the existing `videoAttributes` doc comment). Caller-
   supplied `duration_seconds` (optional, default 0) delivers the issue's
   stated need — "Telegram's voice player displays it" — without the extra
   parsing surface; container parsing is left as a documented follow-up.
4. **Add a fifth top-level branch/type name to keep voice fully isolated
   from `document`'s attribute-building code** (i.e., don't reuse
   `InputMediaUploadedDocument` machinery at all). Not really an
   alternative — `InputMediaUploadedDocument` is the only `tg` input-media
   variant that carries `DocumentAttributeAudio`, exactly as `video` and
   `animation` already reuse it with different attributes. Mentioned only
   to note the design already is this: `buildInputMedia`'s `switch` gets a
   new case, no new Telegram RPC shape.

## Platform impact

- **Migrations:** none. No schema or persisted-state change — voice notes
  are ordinary Telegram documents in transit; nothing new is stored
  server-side beyond the existing upload-then-send flow.
- **Backward compatibility:** additive only. `ValidMediaTypes` gains a key;
  existing `photo`/`video`/`document`/`animation` code paths, schemas, and
  `SendMedia`/`buildInputMedia` signatures for those types are unchanged
  in behavior (the new `durationSeconds` parameter is threaded through but
  ignored by non-voice branches). The Local Bridge protocol
  (`internal/bridge/protocol.go`) is extended with one new optional JSON
  field (`duration_seconds`) on an existing envelope — old daemons talking
  to a new server (or vice versa) simply see a zero-value/absent field,
  no version bump needed per the existing envelope's tolerance of unknown/
  missing fields elsewhere in `dispatchCall`.
- **Resource impact:** negligible. The OGG/Opus sniff reads only the first
  Ogg page (well under 1 KiB) of an already-buffered upload; no additional
  network calls, no new background work, no change to
  `MEDIA_UPLOAD_MAX_BYTES`/`DefaultMediaUploadMaxBytes` (20 MiB) caps —
  voice notes are typically far smaller than that ceiling.
- **Risks + mitigations:**
  - *Risk:* a caller sends non-Opus audio (e.g. plain mp3) as
    `media_type: "voice"`, expecting server-side transcoding. Mitigation:
    explicit issue scope says this is caller responsibility; the new sniff
    turns a silent Telegram-side rendering failure into an immediate,
    actionable client-side error, which is strictly safer than today's
    "sent as document" fallback.
  - *Risk:* the `OpusHead` sniff is a simplified check (first-page magic,
    not full Ogg/Opus RFC 7845 validation) and could accept a malformed
    stream Telegram itself then rejects at RPC time. Mitigation:
    `MessagesSendMedia`'s own RPC error still surfaces through the normal
    `err` return path (`SendMedia`'s existing error propagation,
    send_media.go lines 110-112) — the sniff is a fast-fail UX
    improvement, not the only line of defense.
  - *Risk:* `duration_seconds` scoped-to-voice validation
    (`media_type != "voice"` → reject) could be seen as an inconsistent
    API surface versus silently ignoring it for other types. Mitigation:
    documented explicitly in requirements.md's Open questions and in the
    tool description; an explicit rejection is more debuggable for a
    caller who mistakenly expects it to affect video duration.
  - *Risk:* `cmd/local/daemon.go`'s hand-maintained `args` struct (no
    shared schema with `internal/mcp/media_tools.go`) drifting further out
    of sync as fields are added. Not newly introduced by this proposal
    (already true for every existing `send_media` field) — noted for a
    possible future refactor, out of scope here.
