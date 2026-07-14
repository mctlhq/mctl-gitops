# Design: issue-283-add-opt-in-flag-for-auto-fetching-media

## Current state

### Message retrieval tools

`get_messages` is implemented in `toolGetMessages()` in
`internal/mcp/tools.go` (line 376). It calls `telegram.GetMessages()` in
`internal/telegram/messages.go` (line 432), which invokes
`api.MessagesGetHistory` and decodes the raw Telegram response via
`decodeMessages()` (line 323).

`decodeMessages()` populates the `telegram.Message` struct (defined at line 31
of `internal/telegram/messages.go`):

```go
type Message struct {
    ID        int        `json:"id"`
    Peer      string     `json:"peer"`
    PeerTitle string     `json:"peer_title,omitempty"`
    From      string     `json:"from,omitempty"`
    Text      string     `json:"text"`
    Date      time.Time  `json:"date"`
    MediaInfo *MediaInfo `json:"media_info,omitempty"`
}
```

`MediaInfo` (line 21) carries metadata only: `media_type`, `mime_type`,
`file_name`, `size`, `width`, `height`, `duration`. No bytes are fetched during
`GetMessages`.

`get_unread_messages` follows the same pattern via `toolGetUnreadMessages()`
(line 222) and `telegram.GetUnreadMessages()` (`internal/telegram/messages.go`,
line 176).

### Media download flow

A single-message download requires two explicit tool calls:
1. `prepare_get_media` (`internal/mcp/media_tools.go`, line 38): calls
   `telegram.PrepareMediaRef()` to fetch metadata and a `MediaFileLocation`
   (access hash, file reference), mints a `Confirmation` via `ConfirmStore`
   (TTL 10 min, single-shot), stores a `MediaDownloadRef` in `MediaStore`
   keyed by the confirmation ID.
2. `get_media` (line 128): consumes the confirmation via `ConfirmStore.Consume`,
   pops the `MediaDownloadRef` from `MediaStore`, enforces
   `MediaDownloadMaxBytes` against the ref's declared size, then calls
   `telegram.DownloadMedia()` to stream bytes via `gotd`'s downloader.
   Returns bytes as standard base64 in the `data` field.

The `MediaDownloadRef` struct (`internal/mcp/mediastore.go`, line 14) holds the
server-side file location (including `AccessHash` and `FileReference`) that is
never exposed to the MCP client.

### Why inline bulk fetch does not exist today

`telegram.GetMessages` returns `MediaInfo` populated by `DecodeMediaInfo()` but
never calls `PrepareMediaRef` or `DownloadMedia`. Adding automatic media
downloads to the history-walk would require either (a) calling
`PrepareMediaRef` per message inside the `borrowWithRetry` closure — adding N
extra round-trips per page — or (b) extracting the file location directly from
the already-fetched `tg.Message.Media` without a second API call and then
calling `DownloadMedia` inline. Option (b) is cheaper because the file location
fields (`Document.AccessHash`, `Photo.AccessHash`, `FileReference`) are already
present in the `MessagesGetHistory` response; no second Telegram API call is
needed to prepare a download ref.

## Proposed solution

### 1. Extend `telegram.Message` with `MediaData`

Add an optional field to `telegram.Message`:

```go
// MediaData holds the raw bytes of the message's media as a standard-base64
// string. It is non-nil only when the caller requested inline bulk media
// fetch (get_messages fetch_media=true) and the item was successfully
// downloaded within the per-call cap and size limits.
MediaData *string `json:"media_data,omitempty"`
```

Adding this field to the struct is a backward-compatible JSON change: existing
callers that do not set `fetch_media: true` never see it (it is `omitempty`).

### 2. Add `MediaFileLocation` extraction from `tg.Message`

`telegram.PrepareMediaRef()` already does this for the single-message flow but
it makes a second Telegram API call to look up the message. For the bulk path
the message is already in hand from `MessagesGetHistory`. Add a package-level
helper in `internal/telegram/media_download.go`:

```go
// ExtractMediaLocation extracts the file location from an already-fetched
// tg.Message without making an additional Telegram API call. Returns nil when
// the message carries no downloadable media (contact, location, poll, web page)
// or when the media type is protected (Noforwards set).
func ExtractMediaLocation(msg *tg.Message) (*MediaFileLocation, error)
```

This mirrors the location-extraction block already in `PrepareMediaRef` (lines
124-143 of `internal/telegram/media_download.go`) but operates directly on the
`*tg.Message` present in the `MessagesGetHistory` response rather than fetching
it separately.

### 3. Add `fetchMediaInline()` helper

Create `internal/mcp/bulk_media.go`:

```go
package mcp

import (
    "context"
    "encoding/base64"

    gotdtelegram "github.com/gotd/td/telegram"
    "github.com/mctlhq/mctl-telegram/internal/telegram"
)

// BulkMediaFetchCap is the maximum number of media items fetched inline per
// get_messages or get_unread_messages call when fetch_media=true. It guards
// against runaway context growth when a history page is dense with large files.
const BulkMediaFetchCap = 5

// FetchMediaSummary is included in messagesResult when fetch_media=true.
type FetchMediaSummary struct {
    Fetched int `json:"fetched"`
    Skipped int `json:"skipped"`
    Cap     int `json:"cap"`
}

// fetchMediaInline attempts to download media bytes for each message in msgs,
// up to BulkMediaFetchCap items. It mutates the MediaData field on each
// message it successfully downloads. Items skipped due to the cap, size limit,
// non-downloadable type, or download error are left with MediaData == nil.
// The summary counts fetched and skipped items.
func (s *Server) fetchMediaInline(
    ctx context.Context,
    userID int64,
    rawMsgs []*tg.Message,
    msgs []telegram.Message,
) (FetchMediaSummary, error)
```

The implementation iterates `rawMsgs` in parallel with `msgs` (both ordered by
message position). For each message it calls `telegram.ExtractMediaLocation`.
If the location is nil (non-downloadable type or protected), it skips silently.
If the file's known size exceeds `s.MediaDownloadMaxBytes`, it increments
`skipped` and continues. If `fetched` already equals `BulkMediaFetchCap`, all
remaining downloadable items increment `skipped`. Otherwise it calls
`telegram.DownloadMedia` inside `s.borrowWithRetry` and, on success, encodes
the bytes as standard base64 and stores it in `msgs[i].MediaData`.

Individual download errors increment `skipped` and are logged at DEBUG level
(not returned as call errors).

### 4. Thread raw messages through to the MCP handler

`telegram.GetMessages()` currently returns `[]telegram.Message`. To run
`fetchMediaInline` the handler needs the `*tg.Message` raw messages (to call
`ExtractMediaLocation` without a second API call). There are two options:

**Option A (preferred):** Add a parallel `[](*tg.Message)` return value from
`decodeMessages()` / `GetMessages()` only when `fetch_media=true` is requested.
Since `fetch_media` is an MCP-layer concept, the cleanest approach is to keep
`telegram.GetMessages()` signature unchanged and instead re-expose the raw
message objects via a new low-level helper `telegram.GetMessagesRaw()` that
returns both the decoded `[]telegram.Message` and the underlying
`[](*tg.Message)`. The MCP handler calls `GetMessagesRaw` when `fetch_media`
is set and `GetMessages` (unchanged) otherwise.

**Option B:** Expand `telegram.Message` to carry a private `raw *tg.Message`
pointer and access it only within the `mcp` package. This couples the wire type
to an implementation detail and is harder to test cleanly. Rejected.

### 5. Extend `messagesResult` and MCP tool descriptors

In `internal/mcp/tools.go`, extend `messagesResult`:

```go
type messagesResult struct {
    Messages         []telegram.Message `json:"messages"`
    Notice           string             `json:"notice"`
    NextBeforeID     *int               `json:"next_before_id,omitempty"`
    FetchMediaSummary *FetchMediaSummary `json:"fetch_media_summary,omitempty"`
}
```

`FetchMediaSummary` is populated only when `fetch_media: true` was set.

In `toolGetMessages()` and `toolGetUnreadMessages()`:
- Add `mcplib.WithBoolean("fetch_media", ...)` input parameter (default false).
- Update the `mcplib.WithDescription(...)` string to document the parameter,
  the cap, the cost/latency implications, and that individual items exceeding
  `MediaDownloadMaxBytes` are silently skipped.
- When `fetch_media=true` is set and the account is in Local Bridge mode,
  return a clear tool error: "fetch_media=true is not supported in Local Bridge
  mode — use prepare_get_media and get_media per item instead."

### 6. `WithOutputSchema` consistency

`get_messages` and `get_unread_messages` both use
`mcplib.WithOutputSchema[messagesResult]()`. After extending `messagesResult`
the schema already includes the new optional fields via Go struct reflection.
`telegram.Message` with the new optional `MediaData *string` field is also
reflected correctly. No additional schema wiring is needed.

### 7. `wrapMessages` in `format.go`

`wrapMessages()` (line 48 of `internal/mcp/format.go`) copies `[]telegram.Message`
and sanitizes user-controlled text fields. `MediaData` contains binary bytes
rendered as base64 and is not user-controlled text — it must be copied
verbatim and must not pass through `sanitize.UserContent`. The copy loop
already preserves all fields; since `MediaData` is a pointer to a string, the
copy is a pointer copy (safe — the string is immutable).

## Alternatives

### Alternative A: server-configurable flag only (no per-call parameter)

Add a `BulkMediaFetchEnabled bool` field to `mcp.Server` (configured via an
env var like `BULK_MEDIA_FETCH=true`) and silently fetch media on every
`get_messages` call when the flag is on. This would make the behavior
operator-controlled rather than caller-controlled.

Rejected because the issue explicitly calls for a per-call flag so the caller
declares intent and accepts the cost. An operator flag would not let a careful
caller opt out of the cost on specific calls.

### Alternative B: new dedicated `get_messages_with_media` tool

Add a separate tool `get_messages_with_media` that combines history fetch and
inline download in one call, leaving `get_messages` completely unchanged.

Rejected because it doubles the tool surface area for what is a simple boolean
parameter, and MCP tool lists are already long. The flag approach is consistent
with how `send_message` uses boolean parameters to alter behavior.

### Alternative C: extend `prepare_get_media` to accept a list of message IDs

Let callers pass `[message_id, ...]` to `prepare_get_media`, minting one
confirmation per message and returning a list of confirmation IDs. `get_media`
would accept a list too. This preserves the existing confirmation flow for
bulk fetches.

Rejected because it multiplies the number of MCP tool calls in proportion to
the batch size (one `prepare` + one `get` per message ID), and the confirmation
store's in-memory TTL design was not built for batches. The inline approach
avoids an extra Telegram API call per message by reusing location data already
present in the `MessagesGetHistory` response.

## Platform impact

### Backward compatibility

- `telegram.Message` gains one optional `*string` field (omitempty). Existing
  JSON consumers that deserialize into a `map[string]any` or a struct without
  `media_data` are unaffected.
- `messagesResult` gains one optional `*FetchMediaSummary` field (omitempty).
  Same compatibility guarantee.
- `get_messages` and `get_unread_messages` gain one optional boolean parameter
  `fetch_media`. MCP clients that do not pass it receive the current behavior.

### Resource impact

- Each `fetch_media=true` call can download up to `BulkMediaFetchCap` (5) files
  inside the `borrowWithRetry` closure, which holds a pool slot for the full
  duration. With `MediaDownloadMaxBytes` defaulting to 20 MiB and a cap of 5,
  the worst-case response is roughly 100 MiB in-memory before base64 encoding
  (~133 MiB encoded). Most MCP clients spill this to disk rather than
  returning it inline, which is the behavior the issue already notes. The cap
  must be low enough that even a worst-case page does not OOM the process.
- The `BulkMediaFetchCap` constant should be tunable if load testing shows 5
  is too high. Start conservative; the value can be raised in a follow-up.

### Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Caller accidentally sets `fetch_media: true` in a loop over thousands of pages | Cap at `BulkMediaFetchCap` per call; each call is independent and bounded. |
| Large files inflate MCP response past client limit | Existing `MediaDownloadMaxBytes` guard skips oversized items; summary tells caller how many were skipped. |
| Confirm/download race from #282 | Not applicable: the inline path does not use `ConfirmStore` or `MediaStore`. |
| Local Bridge protocol mismatch | Detected and rejected at the MCP handler before any bridge call is made. |
| `ExtractMediaLocation` diverges from `PrepareMediaRef` behavior | Share the location-extraction block as a common helper; `PrepareMediaRef` calls it instead of duplicating the switch. |
