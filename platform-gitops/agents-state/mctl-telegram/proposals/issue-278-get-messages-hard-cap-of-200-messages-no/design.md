# Design: issue-278-get-messages-hard-cap-of-200-messages-no

## Current state

### `internal/telegram/messages.go`

`GetMessages` (line 235) has this signature:

```go
func GetMessages(ctx context.Context, c *telegram.Client, peerSpec string, limit int,
    cache *PeerCache, userID int64) ([]Message, error)
```

The limit guard at line 239 resets any out-of-range value to 50 instead of
clamping:

```go
if limit <= 0 || limit > 200 {
    limit = 50
}
```

There are three separate `MessagesGetHistoryRequest` calls within the function
(lines 273-276, 290-293, and 302-305 — the dialog-found path, the direct-
fallback path, and the cache-evict-retry path). None passes `OffsetID`; all use
only `Peer` and `Limit`.

`GetUnreadMessages` (line 27) has the same limit guard (line 28) and calls
`MessagesGetHistoryRequest` at line 98-101 also without `OffsetID`.

`tg.MessagesGetHistoryRequest` (gotd/td v0.144.0) exposes the following
relevant fields:
- `Peer tg.InputPeerClass` — required
- `Limit int` — max messages to return
- `OffsetID int` — return messages with ID strictly less than this value; zero
  means no offset (start from newest)

### `internal/mcp/tools.go`

`toolGetMessages` (line 376) declares no `before_id` input parameter. The
output type `messagesResult` (line 1124) contains only:

```go
type messagesResult struct {
    Messages []telegram.Message `json:"messages"`
    Notice   string             `json:"notice"`
}
```

The `get_my_audit_log` tool (line 693) and `get_user_audit_log` tool (line 887)
already demonstrate the keyset-pagination pattern used in this codebase: they
accept a `before` RFC3339 string, parse it, and pass it to
`Store.ListAuditFor(ctx, id.UserID, limit, before)`.

### `cmd/local/daemon.go`

`dispatchCall` (line 254) handles `"get_messages"` by deserialising only `Peer`
and `Limit` from the args struct (lines 310-313) and calling
`tg.GetMessages(ctx, c, args.Peer, args.Limit, nil, 0)` (line 323). It has no
`BeforeID` field and the response marshal (lines 327-330) does not emit
`next_before_id`. An identical gap exists for the `"get_unread_messages"` case
(lines 285-307), which is out of scope for this proposal.

---

## Proposed solution

### 1. Update `GetMessages` signature (`internal/telegram/messages.go`)

Add `beforeID int` as the last new parameter:

```go
func GetMessages(ctx context.Context, c *telegram.Client, peerSpec string, limit int,
    beforeID int, cache *PeerCache, userID int64) ([]Message, error)
```

Fix the limit guard to clamp rather than reset:

```go
if limit <= 0 {
    limit = 50
} else if limit > 200 {
    limit = 200
}
```

Pass `OffsetID: beforeID` in all three `MessagesGetHistoryRequest` call sites:

```go
hist, err := api.MessagesGetHistory(ctx, &tg.MessagesGetHistoryRequest{
    Peer:     input,
    Limit:    limit,
    OffsetID: beforeID,
})
```

This change is purely additive at the Telegram API level: when `beforeID` is 0
(the default), `messages.getHistory` with `OffsetID=0` behaves exactly as
today.

### 2. Compute pagination cursor in the tool handler (`internal/mcp/tools.go`)

Add `NextBeforeID *int` to `messagesResult`:

```go
type messagesResult struct {
    Messages     []telegram.Message `json:"messages"`
    Notice       string             `json:"notice"`
    NextBeforeID *int               `json:"next_before_id,omitempty"`
}
```

In `toolGetMessages`, parse `before_id` and pass it through:

```go
beforeID := intArg(args, "before_id", 0)
// ...
msgs, err = telegram.GetMessages(ctx, c, peer, limit, beforeID, s.PeerCache, id.UserID)
```

After the call, compute the cursor. `decodeMessages` returns messages in the
order Telegram delivers them (newest-first for `messages.getHistory`), so the
last element in the slice is the oldest and has the smallest ID:

```go
result := messagesResult{
    Messages: wrapMessages(msgs),
    Notice:   untrustedContentNotice,
}
if len(msgs) == limit {
    minID := msgs[len(msgs)-1].ID
    result.NextBeforeID = &minID
}
return jsonResult(result)
```

When `len(msgs) < limit`, `NextBeforeID` is left nil and omitted from the JSON
response, signalling end-of-history.

Update the `get_messages` tool description to document `before_id` and
`next_before_id`:

```
  before_id — optional int. When set, only messages with ID strictly less than
              this value are returned. Use the "next_before_id" of a previous
              response to walk backward through history in 200-message batches.

Output: {notice, messages: [...], next_before_id}. next_before_id is the
message ID to pass as before_id on the next call; omitted when the beginning
of the conversation has been reached.
```

Add `mcplib.WithNumber("before_id", ...)` to the tool schema.

### 3. Update `toolGetMessages` input schema

```go
mcplib.WithNumber("before_id",
    mcplib.Description("Optional: only messages with ID strictly less than this value are returned. "+
        "Use next_before_id from a previous response to page backward."),
),
```

### 4. Fix limit guard in `GetUnreadMessages` (`internal/telegram/messages.go`)

Apply the same clamp fix for consistency:

```go
if limit <= 0 {
    limit = 50
} else if limit > 200 {
    limit = 200
}
```

No pagination is added to `GetUnreadMessages` in this change (out of scope).

### 5. Update Local Bridge daemon (`cmd/local/daemon.go`)

In the `"get_messages"` case of `dispatchCall`, add `BeforeID` to the args
struct and forward it to `tg.GetMessages`:

```go
case "get_messages":
    var args struct {
        Peer     string `json:"peer"`
        Limit    int    `json:"limit"`
        BeforeID int    `json:"before_id"`
    }
    // ...
    msgs, err = tg.GetMessages(ctx, c, args.Peer, args.Limit, args.BeforeID, nil, 0)
    // compute next_before_id before marshaling
```

The response marshal must also emit `next_before_id` with the same semantics as
the hosted path.

---

## Alternatives

### A. Timestamp cursor (`before_date`) mirroring the audit-log tools

The audit-log tools use an RFC3339 `before` timestamp. Applying the same to
`get_messages` would mean passing `OffsetDate int` in `MessagesGetHistoryRequest`
(the Unix-second field).

Rejected: Telegram timestamps are second-granularity. Multiple messages in a
fast-moving group chat can share the same second, making a timestamp cursor
ambiguous — a page boundary at a busy second could skip or duplicate messages.
Message IDs are monotonically increasing integers unique per chat and are
already present in every returned message, making them a strictly more reliable
cursor. The audiot-log pattern used timestamps because audit rows have a high-
precision DB timestamp; Telegram message IDs are the right analog.

### B. Numeric offset via `AddOffset` in `MessagesGetHistoryRequest`

`messages.getHistory` also supports `AddOffset int` — an integer skip count
from the `OffsetID` position. This could be used to implement offset-based
pagination (skip the first N messages from the newest).

Rejected: numeric offsets are unstable. While a paginated session is in
progress, new messages arrive and push all older messages down in the offset
numbering. A caller paging through history at offset 200, 400, 600 would see
duplicate or missing messages because the total count shifts. Keyset pagination
(by message ID) is stable regardless of concurrent new messages.

### C. Stateful server-side cursor (opaque token in the DB)

Issue a short-lived opaque pagination token stored in the database, encapsulating
the peer and last-seen message ID. The client passes the token rather than a raw
message ID.

Rejected: adds DB writes and state management overhead for a read-only
operation. The client already has all the information it needs (the message IDs
are in every response). Keeping the cursor client-side matches the audit-log
pattern and keeps the server stateless with respect to pagination.

---

## Platform impact

### Backward compatibility

The change is purely additive. `before_id` is an optional parameter with a zero
default; `next_before_id` is emitted only when there are more messages to fetch.
Existing clients that do not send `before_id` see identical responses except for
the possible addition of the `next_before_id` field (which they can ignore).
The `GetMessages` Go signature change requires updating every call site:
- `internal/mcp/tools.go` line 423: `telegram.GetMessages(ctx, c, peer, limit, s.PeerCache, id.UserID)` — add `beforeID` argument.
- `cmd/local/daemon.go` line 323: `tg.GetMessages(ctx, c, args.Peer, args.Limit, nil, 0)` — add `args.BeforeID` argument.
- Any test files constructing `GetMessages` calls directly.

### Schema change

`messagesResult` gains `NextBeforeID *int \`json:"next_before_id,omitempty"\``.
Because `mcplib.WithOutputSchema[messagesResult]()` derives the JSON Schema
from the Go type at startup, the MCP tool schema exposed to clients updates
automatically with no extra wiring.

### No database migrations

There are no DB reads or writes in this change. Pagination state is client-held.

### No additional Telegram API calls

Each `get_messages` invocation still issues the same number of
`messages.getHistory` calls (one for the dialog-found path; one for the direct
fallback; one more on cache-evict retry if PEER_ID_INVALID). `OffsetID` is a
filter applied server-side by Telegram, not a separate round-trip.

### Risk: `decodeMessages` ordering assumption

The computation `msgs[len(msgs)-1].ID` assumes the returned slice is ordered
newest-first (descending message ID). This is the documented order for
`messages.getHistory` with no `add_offset`. However `decodeMessages`
(line 175) does not enforce any sort — it preserves Telegram's wire order.
If Telegram ever returns messages out of order for a specific chat type
(unlikely but undocumented guarantee), the cursor would be wrong. Mitigation:
in the handler, take `min(msgs[i].ID for all i)` instead of
`msgs[len(msgs)-1].ID` for safety; cost is a trivial linear scan over at most
200 elements.

### Local Bridge daemon compatibility

Older bridge daemon binaries that have not been rebuilt after this change will
silently ignore `before_id` (the existing args struct has no `BeforeID` field,
so `json.Unmarshal` discards it) and will not emit `next_before_id`. The hosted-
side MCP server still passes the args dict wholesale via `bridgeCall`, so no
new protocol field is needed in `bridge.Envelope`. The daemon rebuild is
required for full pagination support in local mode; partial builds are
functionally safe (pagination simply does not work, same as before the change).
