# Design: issue-277-get-messages-media-messages-photos-files

## Current state

### Message struct and decodeMessages — internal/telegram/messages.go

The `Message` struct (lines 16-23) carries six fields:

```go
type Message struct {
    ID        int       `json:"id"`
    Peer      string    `json:"peer"`
    PeerTitle string    `json:"peer_title,omitempty"`
    From      string    `json:"from,omitempty"`
    Text      string    `json:"text"`
    Date      time.Time `json:"date"`
}
```

`decodeMessages` (lines 175-204) iterates over `[]tg.MessageClass`, type-asserts each
to `*tg.Message`, and reads `.ID`, `.FromID`, `.Message` (the text caption/body), and
`.Date`. The field `msg.Media tg.MessageMediaClass` is present on every `tg.Message`
returned by the Telegram API but is never read. When a message carries a photo or
document with no caption, `msg.Message` is the empty string, so the returned
`Message.Text` is `""` — indistinguishable from a blank text message.

### MCP tool wiring — internal/mcp/tools.go

Both `toolGetMessages` (line 376) and `toolGetUnreadMessages` (line 222) call
`telegram.GetMessages` / `telegram.GetUnreadMessages`, which both invoke
`decodeMessages`. They then call `wrapMessages(msgs)` and return a
`messagesResult{Messages: ..., Notice: untrustedContentNotice}`.

`messagesResult` (line 1124):
```go
type messagesResult struct {
    Messages []telegram.Message `json:"messages"`
    Notice   string             `json:"notice"`
}
```

`WithOutputSchema[messagesResult]()` reflects the struct at registration time, so the
generated JSON Schema is derived from `telegram.Message`. Adding a new field to
`Message` automatically expands that schema without further changes in `tools.go`.

### Sanitization and wrapping — internal/mcp/format.go

`wrapMessages` (lines 47-68) copies the `Message` slice, sanitizes `Text`, `From`,
and `PeerTitle` via `sanitize.UserContent` / `sanitize.Name`, then wraps `Text` in
`<telegram-content>` tags via `WrapUntrustedContent`. The copy is done by value
(`out[i] = m` after modifying `m`). Any pointer field on `Message` would have its
pointer copied, not the pointed-to struct — so a `*MediaInfo` pointer is carried
through correctly as-is; `wrapMessages` need not be changed for Phase 1.

### Confirmation two-step — internal/mcp/confirm.go

`ConfirmStore` (lines 30-119) is an in-memory TTL map used by `prepare_pin_message` /
`pin_message`. `Issue` mints a `confirmation_id`; `Consume` validates and removes it
in a single-shot fashion. The store is held on `Server.Confirms` (server.go line 22).

The existing `Confirmation` struct carries `PayloadHash` (sha256 of the canonical
input) for tamper detection but does not carry an opaque payload. Adding media
download context (access_hash, file_reference, size) to `Confirmation` would pollute
the generic store; the design uses a parallel map instead.

### gotd/td media types (v0.144.0, go.mod line 7)

The `tg.MessageMediaClass` interface is implemented by:
- `*tg.MessageMediaEmpty` — no media
- `*tg.MessageMediaPhoto` — has `Photo tg.PhotoClass` (concrete `*tg.Photo`: `ID`,
  `AccessHash`, `FileReference`, `Sizes []tg.PhotoSizeClass`)
- `*tg.MessageMediaDocument` — has `Document tg.DocumentClass` (concrete
  `*tg.Document`: `ID`, `AccessHash`, `FileReference`, `MimeType string`, `Size int64`,
  `Attributes []tg.DocumentAttributeClass`)
  - Specialising attributes: `*tg.DocumentAttributeFilename` (FileName string),
    `*tg.DocumentAttributeSticker`, `*tg.DocumentAttributeVideo` (Duration int),
    `*tg.DocumentAttributeAudio` (Voice bool, Duration int),
    `*tg.DocumentAttributeAnimated`, `*tg.DocumentAttributeImageSize`
- `*tg.MessageMediaGeo`, `*tg.MessageMediaContact`, `*tg.MessageMediaWebPage`,
  `*tg.MessageMediaPoll`, `*tg.MessageMediaUnsupported`, and others

For download, MTProto uses `tg.InputDocumentFileLocation` (for documents) or
`tg.InputPhotoFileLocation` (for photos), constructed from the `ID`, `AccessHash`,
and `FileReference` captured at prepare time. `api.UploadGetFile` returns up to
512 KB per call; a download loop reassembles chunks until `Bytes` is empty.

---

## Proposed solution

The change is delivered in two independent phases. Phase 2 depends on the
`MediaInfo` struct defined in Phase 1, but Phase 1 is complete and shippable on
its own.

### Phase 1 — MediaInfo metadata on Message

**1. New struct and field in internal/telegram/messages.go**

```go
// MediaInfo describes non-text content attached to a Telegram message.
// It is nil when the message carries no media or only a web-page preview.
// All fields except MediaType are omitted when zero or not applicable.
type MediaInfo struct {
    MediaType string `json:"media_type"`
    MimeType  string `json:"mime_type,omitempty"`
    FileName  string `json:"file_name,omitempty"`
    Size      int64  `json:"size,omitempty"`
    Width     int    `json:"width,omitempty"`
    Height    int    `json:"height,omitempty"`
    Duration  int    `json:"duration,omitempty"` // seconds
}

type Message struct {
    ID        int        `json:"id"`
    Peer      string     `json:"peer"`
    PeerTitle string     `json:"peer_title,omitempty"`
    From      string     `json:"from,omitempty"`
    Text      string     `json:"text"`
    Date      time.Time  `json:"date"`
    MediaInfo *MediaInfo `json:"media_info,omitempty"` // nil for text-only messages
}
```

`MediaType` values:
| Value | Trigger |
|---|---|
| `"photo"` | `*tg.MessageMediaPhoto` |
| `"sticker"` | document + `*tg.DocumentAttributeSticker` |
| `"voice"` | document + `*tg.DocumentAttributeAudio{Voice:true}` |
| `"audio"` | document + `*tg.DocumentAttributeAudio{Voice:false}` |
| `"video"` | document + `*tg.DocumentAttributeVideo` |
| `"animation"` | document + `*tg.DocumentAttributeAnimated` |
| `"document"` | document, no specialising attribute |
| `"web_page"` | `*tg.MessageMediaWebPage` |
| `"contact"` | `*tg.MessageMediaContact` |
| `"location"` | `*tg.MessageMediaGeo` or `*tg.MessageMediaGeoLive` |
| `"poll"` | `*tg.MessageMediaPoll` |
| `"unsupported"` | `*tg.MessageMediaUnsupported` |

Attribute priority for documents (first match wins): sticker > voice > audio > video >
animation > document. This is consistent with how Telegram Desktop and most clients
classify these types.

**2. decodeMediaInfo function in internal/telegram/messages.go**

```go
func decodeMediaInfo(media tg.MessageMediaClass) *MediaInfo {
    switch m := media.(type) {
    case nil, *tg.MessageMediaEmpty:
        return nil
    case *tg.MessageMediaPhoto:
        // ... extract largest PhotoSize for width/height
    case *tg.MessageMediaDocument:
        // ... scan attributes for specialising type
        // ... populate MimeType, Size, FileName, Duration
    case *tg.MessageMediaWebPage:
        return &MediaInfo{MediaType: "web_page"}
    case *tg.MessageMediaContact:
        return &MediaInfo{MediaType: "contact"}
    case *tg.MessageMediaGeo, *tg.MessageMediaGeoLive:
        return &MediaInfo{MediaType: "location"}
    case *tg.MessageMediaPoll:
        return &MediaInfo{MediaType: "poll"}
    default:
        return &MediaInfo{MediaType: "unsupported"}
    }
}
```

**3. Wire into decodeMessages**

In the loop body (messages.go ~line 191), after constructing `Message{...}`:

```go
msg2 := Message{
    ID:        msg.ID,
    Peer:      hint.ID,
    PeerTitle: hint.Title,
    From:      resolveSender(msg.FromID, users, chats),
    Text:      msg.Message,
    Date:      time.Unix(int64(msg.Date), 0).UTC(),
    MediaInfo: decodeMediaInfo(msg.Media),
}
out = append(out, msg2)
```

**4. wrapMessages in internal/mcp/format.go**

No code change required. `wrapMessages` copies `Message` by value (`m` is a local
copy of the struct); `m.MediaInfo` is a pointer, so the copy carries the same pointer
to the underlying `MediaInfo` struct. Since `wrapMessages` never writes to `MediaInfo`,
the pointer copy is safe and correct. A comment should be added to document this
invariant.

**5. Tool description updates in internal/mcp/tools.go**

The output schema for `get_messages` and `get_unread_messages` is reflected from
`messagesResult` which embeds `[]telegram.Message`. Adding `MediaInfo *MediaInfo` with
`omitempty` to `Message` automatically adds the field to the reflected JSON Schema;
no call-site change is needed in `tools.go` beyond updating the prose description
strings to mention `media_info`.

---

### Phase 2 — prepare_get_media / get_media tools

**Overall flow** (mirrors `prepare_pin_message` / `pin_message`):

```
Client                     Server
  |                           |
  |-- prepare_get_media ----> |  1. fetch message via MessagesGetMessages
  |                           |  2. validate media is downloadable
  |                           |  3. store MediaDownloadRef keyed by confID
  |                           |  4. issue ConfirmStore entry
  |<-- {confirmation_id, ...} |
  |                           |
  |-- get_media ------------> |  5. ConfirmStore.Consume (validates TTL + hash)
  |                           |  6. look up MediaDownloadRef
  |                           |  7. check size <= MEDIA_DOWNLOAD_MAX_BYTES
  |                           |  8. UploadGetFile loop via Pool.Borrow
  |<-- {data (base64), ...}   |
```

**MediaDownloadRef — new struct, internal/mcp/tools.go or a new file**

```go
type MediaDownloadRef struct {
    Peer          string
    MessageID     int
    MediaType     string
    MimeType      string
    FileName      string
    Size          int64
    // MTProto file location fields needed for UploadGetFile:
    IsDocument    bool
    DocID         int64
    AccessHash    int64
    FileReference []byte
    // For photos:
    PhotoID       int64
    ThumbSize     string // largest available
}
```

This struct is stored server-side — the client never sees `AccessHash` or
`FileReference`, which are MTProto-internal tokens. The `confirmation_id` is the
only handle the client holds.

**mediaStore — parallel in-memory map on Server (internal/mcp/server.go)**

```go
type Server struct {
    // ...existing fields...
    mediaStore *MediaStore // Phase 2
}

type MediaStore struct {
    mu  sync.Mutex
    m   map[string]*MediaDownloadRef
    now func() time.Time
    ttl time.Duration
}
```

`MediaStore` is initialised in `mcp.New` alongside `ConfirmStore`. TTL matches
`ConfirmationTTL` (10 minutes). `Set(confID, ref)` and `Pop(confID)` (atomic get +
delete) are the only needed methods. `Sweep()` removes expired entries on the same
schedule as `ConfirmStore`.

**prepare_get_media tool**

- Annotation: `ReadOnly=true`, `Destructive=false`, `OpenWorld=true` (reaches
  Telegram).
- Scope check: `telegram:messages:read` (same as `get_messages`; reading media
  metadata is not more privileged than reading message text).
- Calls `api.MessagesGetMessages` with the resolved `InputPeer` and the given
  `message_id` to fetch the specific message and its media fields.
- `decodeMediaInfo` is reused to classify the media type; if `MediaInfo` is nil
  (no downloadable media), returns a tool error.
- Stores the `MediaDownloadRef` in `mediaStore`.
- Issues a `ConfirmStore` confirmation with action `"media"` and
  `HashMediaPayload(peer, messageID)` as the payload hash.
- Returns `prepareGetMediaResult`:

```go
type prepareGetMediaResult struct {
    ConfirmationID string    `json:"confirmation_id"`
    PeerRedacted   string    `json:"peer_redacted"`
    MessageID      int       `json:"message_id"`
    MediaType      string    `json:"media_type"`
    MimeType       string    `json:"mime_type,omitempty"`
    FileName       string    `json:"file_name,omitempty"`
    Size           int64     `json:"size,omitempty"`
    ExpiresAt      time.Time `json:"expires_at"`
}
```

**get_media tool**

- Annotation: `ReadOnly=true`, `Destructive=false`, `OpenWorld=true`.
- Scope check: `telegram:messages:read`.
- `ConfirmStore.Consume(confID, userID, HashMediaPayload(peer, messageID))` —
  validates TTL, user, and payload hash.
- `mediaStore.Pop(confID)` — retrieves and deletes the `MediaDownloadRef`.
- Size gate: if `ref.Size > s.MediaDownloadMaxBytes`, return tool error without
  downloading.
- `borrowWithRetry` with inner function that calls `api.UploadGetFile` in a loop,
  accumulating chunks until the response `Bytes` slice is empty. A per-download
  context timeout (default 60 s, added to the borrowed context) prevents runaway
  sessions.
- Returns `getMediaResult`:

```go
type getMediaResult struct {
    MediaType string `json:"media_type"`
    MimeType  string `json:"mime_type,omitempty"`
    FileName  string `json:"file_name,omitempty"`
    Size      int64  `json:"size"`
    Data      string `json:"data"` // standard base64
}
```

**HashMediaPayload**

```go
func HashMediaPayload(peer string, messageID int64) string {
    h := sha256.New()
    h.Write([]byte(peer))
    h.Write([]byte{0})
    var b [8]byte
    for i := 0; i < 8; i++ {
        b[7-i] = byte(messageID >> (8 * i))
    }
    h.Write(b[:])
    return hex.EncodeToString(h.Sum(nil))
}
```

**Config — internal/config/config.go**

Add `MediaDownloadMaxBytes int64` parsed from `MEDIA_DOWNLOAD_MAX_BYTES` (default
`20971520`). Wire to `Server.MediaDownloadMaxBytes int64`.

**HTTPHandler registration — internal/mcp/server.go**

```go
{t, h := s.toolPrepareGetMedia(); s.addTool(srv, t, h)}
{t, h := s.toolGetMedia(); s.addTool(srv, t, h)}
```

Both are added after the existing pin tools. Both pass `toolPassesFilter` for the
`"all"` filter; neither passes `"read-only"` since they reach Telegram (open-world).
Actually, since both are read-only hint = true, they do pass the read-only filter —
this is consistent with `get_messages` having `ReadOnly=true` despite touching
Telegram. The filter controls write risk, not network reach.

---

## Alternatives

### Alternative A — Inline file bytes in get_messages (no prepare-confirm)

Automatically download and include base64 bytes for every media message returned
by `get_messages`. This avoids new tools and new confirmation logic. However, it
downloads files the caller did not explicitly request — a conversation with 50 media
messages would download all 50 at once, potentially gigabytes. It also violates the
principle that read tools should not trigger irreversible or expensive side effects.
Dropped.

### Alternative B — HTTP streaming download URL

Issue a signed short-lived URL (e.g. `/media/{token}`) that an HTTP client can
GET to stream bytes directly. This avoids base64 inflation (factor ~1.37) and is
cleaner for browser or GUI clients. However: (a) it requires a new HTTP route on the
chi mux in `cmd/server/main.go`; (b) in `local` mode the MTProto client runs on the
user's machine via the Local Bridge daemon, so the cloud server cannot proxy the
download without a second relay channel; (c) it requires the download token to be
accessible to an unauthenticated HTTP client or to carry its own auth header, adding
another auth surface. This can be layered on top of Phase 2 as an optional HTTP
endpoint that converts the `confirmation_id` into a stream; it is deferred.

### Alternative C — Extend ConfirmStore to carry an opaque Payload field

Add `Payload []byte` to `Confirmation` so `ConfirmStore` owns the full media download
ref lifecycle. This reduces the number of maps but couples the generic confirmation
mechanism (used by pin) to media-specific fields. `ConfirmStore` becomes a leaky
abstraction. The parallel `mediaStore` map keeps the concerns separated with minimal
complexity: two methods (`Set`, `Pop`) and one mutex. Dropped.

---

## Platform impact

**Backward compatibility.** `MediaInfo` is an `omitempty` pointer field added to
`Message`. Existing JSON consumers that do not know about it receive no new fields
for text-only messages. Consumers that do parse the messages array may now see an
additional `media_info` object on media messages; this is additive and should not
break compliant JSON parsers.

**Output schema.** `WithOutputSchema[messagesResult]()` in `toolGetMessages` and
`toolGetUnreadMessages` reflects `messagesResult` at server startup. Adding the
`*MediaInfo` field to `Message` expands the reflected schema automatically. MCP
clients that cache the schema and compare it strictly may detect a schema change on
the next server restart; no client-breaking field is removed or renamed.

**Memory.** The `mediaStore` map is bounded by `ConfirmationTTL` (10 minutes) times
request rate. At 10 prepare calls per second (an extreme rate for an MCP assistant),
~6000 entries accumulate, each around 200 bytes: ~1.2 MB. Negligible. A `Sweep()`
call on the same tick as `ConfirmStore.Sweep()` keeps it bounded.

**Download size risk.** Without the size cap, a single `get_media` call for a 4 GB
video would exhaust pod memory. The cap (default 20 MB) is enforced before any
MTProto call is made by checking `ref.Size` (stored at prepare time from
`tg.Document.Size`). Photos do not carry a byte size from `MessagesGetMessages` in
all Telegram API versions; for photos the check is skipped and a separate per-call
byte counter in the download loop terminates if accumulated bytes exceed the cap.

**MTProto chunk loop latency.** `api.UploadGetFile` returns up to 512 KB per call.
A 20 MB file requires ~41 Telegram API round trips, each ~100–300 ms on a good
connection: total 4–12 seconds. This is within MCP client timeout expectations for
a download tool. The per-download context timeout (60 s) acts as a hard backstop.

**Local Bridge.** `prepare_get_media` and `get_media` are routed through `bridgeCall`
for `local`-mode accounts, following the same pattern as `get_messages` (tools.go
~line 412). The Local Bridge daemon (`cmd/local/daemon.go`) must implement handlers
for these two tool names. This is a follow-on task and is tracked in tasks.md as
task 10. Until the daemon implements the handlers, `prepare_get_media` returns the
standard "local-bridge daemon not connected" or "unsupported tool" error from the
bridge protocol, which is a safe fallback.

**Audit.** Both new tools call `s.audit(...)` with `telegram:messages:read` action
names and the redacted peer. No sensitive fields (bytes, access_hash, file_reference)
are written to the audit log.

**Redaction.** `MediaInfo` contains no user-authored free text that requires
sanitization — only mime type strings, filenames (which may contain user-chosen
names), and numeric sizes. `FileName` should be passed through `sanitize.Name` in
`wrapMessages` if it could contain adversarial content (e.g. a filename that looks
like a prompt-injection instruction). This is a conservative measure; filenames are
metadata, not content. The `internal/audit/redact.go` slog handler does not need
updating because `MediaInfo` fields are not slog-emitted.
