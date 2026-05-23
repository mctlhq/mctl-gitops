# Design: issue-158-non-deterministic-safety-block-on-get-me

## Current state

### Error classification path

`internal/mcp/errorcatalog.go` — `mtprotoErrResult` — handles two categories:

1. **Flood/slowmode**: `FLOOD_WAIT_X` and `SLOWMODE_WAIT_X` (parsed by
   `floodWaitSeconds`) return a JSON envelope with `retry_after_seconds`.
2. **Permanent catalog**: `mtprotoErrCatalog` (a `map[string]catalogEntry`) maps
   19 known codes (`PEER_ID_INVALID`, `CHAT_FORBIDDEN`, `CHANNEL_PRIVATE`, etc.)
   to human-readable messages. `PEER_FLOOD` is **not in the catalog**.

When `mtprotoErrResult` returns `nil` (unrecognised code), `borrowErrResult`
(`internal/mcp/tools.go:929`) falls through to:

```go
return toolErr("%s: %v", tool, err)
```

This produces a plain string like `get_messages: rpc error code 420 message
PEER_FLOOD` — visually identical to a permission error or a network failure.

### Retry loop

`borrowWithRetry` (`internal/mcp/tools.go:34-66`) retries only when
`telegram.FloodWaitSeconds(lastErr) > 0`, which covers `FLOOD_WAIT_X` and
`FLOOD_PREMIUM_WAIT_X` (`internal/telegram/floodwait.go`). `PEER_FLOOD` (code
420 but no numeric suffix) returns 0 from `FloodWaitSeconds` and is therefore
**not retried**.

### Peer resolution in GetMessages / GetUnreadMessages

`internal/telegram/messages.go`:

- `GetMessages` (line 165): calls `MessagesGetDialogs(limit=200, OffsetPeer=empty)`,
  then scans the returned dialog list to find the peer. If the peer is not
  among the most-recent 200 dialogs, it returns `peer %q not found in dialogs`
  (line 208) — a hard error.
- `GetUnreadMessages` (line 24): calls `MessagesGetDialogs(limit=100)`, then
  scans for dialogs where `UnreadCount > 0`. An explicit `peerSpec` is matched
  the same way; if not found in the top 100 dialogs the call silently returns
  zero messages.

Both functions invoke `MessagesGetDialogs` on every call — there is no caching
of the dialog list or resolved `InputPeerClass` values anywhere in the codebase.

### Peer resolution in SendMessage

`internal/telegram/send.go` calls `ResolvePeer` directly
(`internal/telegram/peers.go:20`). For `@username` peers this issues
`ContactsResolveUsername` — also uncached. Repeated resolution of the same
username can trigger Telegram's `PEER_FLOOD` anti-abuse gate.

### Send gate

`evaluateSendGate` (`internal/mcp/tools.go:865`) checks mode, `ALLOW_SEND`
flag, scope, and per-account `send_enabled` in sequence. Each failure returns a
`dryReason` string. These are local policy checks, not Telegram API calls, so
they are deterministic and not the source of the non-determinism.

### Audit logging

`s.audit` (`internal/mcp/tools.go:950`) records `status="error"` and
`msg=err.Error()` to `audit_logs` and emits a slog `Warn`. The raw MTProto
error code appears in `err.Error()` (wrapped by `fmt.Errorf`) but is not
promoted to a dedicated field — making it harder to grep/aggregate in Loki.

---

## Proposed solution

### Change 1 — Classify PEER_FLOOD and similar transient codes

**File**: `internal/mcp/errorcatalog.go`

Add a `transientErrCatalog` parallel to `mtprotoErrCatalog`:

```go
type transientEntry struct {
    message          string
    action           string
    retryAfterSeconds int
}

var mtprotoTransientCatalog = map[string]transientEntry{
    "PEER_FLOOD": {
        message:           "Telegram's anti-abuse gate temporarily blocked this peer operation.",
        action:            "Wait 60 seconds and retry the same call.",
        retryAfterSeconds: 60,
    },
}
```

Extend `mtprotoErrResult` to check `mtprotoTransientCatalog` before the
permanent catalog. On a transient match, return the same structured JSON
envelope already used for FLOOD_WAIT:

```json
{
  "error":               "RISK_GATED",
  "message":             "...",
  "retry_after_seconds": 60,
  "action":              "..."
}
```

This is a backward-compatible change: the response is still a tool error
(`IsError=true`); only the content of the error string changes from an opaque
Go error to a structured JSON payload — matching what `FLOOD_WAIT_X` already
produces.

### Change 2 — Retry PEER_FLOOD in borrowWithRetry

**File**: `internal/mcp/tools.go`

Extend `borrowWithRetry` to also retry on `PEER_FLOOD`. Extract a helper that
returns `(shouldRetry bool, sleepSeconds int)` given an error:

```go
func retryPolicy(err error) (bool, int) {
    if n := telegram.FloodWaitSeconds(err); n > 0 {
        return true, n
    }
    var rpcErr *tgerr.Error
    if errors.As(err, &rpcErr) && rpcErr.Message == "PEER_FLOOD" {
        return true, 60
    }
    return false, 0
}
```

Replace the existing `FloodWaitSeconds` check in `borrowWithRetry` with a call
to `retryPolicy`. No change to `maxFloodWaitRetries` (3) or `maxFloodWaitSleep`
(60s). Metrics: the existing `TelegramFloodWaitEventsTotal` counter is extended
with a `peer_flood` label value via a new `TelegramTransientEventsTotal` counter
(or by re-using the flood-wait counter with a `"peer_flood"` label).

### Change 3 — Fallback peer resolution in GetMessages

**File**: `internal/telegram/messages.go`

When `GetMessages` reaches the end of the dialog loop without finding the peer,
instead of immediately returning `peer %q not found in dialogs`, try
`ResolvePeer` and call `MessagesGetHistory` directly:

```go
// Fallback: peer not in dialog list — resolve directly.
input, resolveErr := ResolvePeer(ctx, c, peerSpec)
if resolveErr != nil {
    return nil, fmt.Errorf("peer %q not found in dialogs and direct resolution failed: %w", peerSpec, resolveErr)
}
hist, err := api.MessagesGetHistory(ctx, &tg.MessagesGetHistoryRequest{
    Peer:  input,
    Limit: limit,
})
if err != nil {
    return nil, fmt.Errorf("MessagesGetHistory (fallback): %w", err)
}
// Build a minimal hint for decodeMessages using peerSpec as title.
hint := &Dialog{ID: peerSpec, Title: peerSpec}
return decodeMessages(hist, hint, users, chats, limit), nil
```

The fallback provides `PeerTitle` as the raw peerSpec string; a follow-up can
enrich this from the API response. The dialog-scan path is unchanged and remains
the primary path for peers that are in the recent dialog list (it provides
richer metadata).

`GetUnreadMessages` with an explicit peer: the unread-count fallback is
deferred to a follow-up (Open Question 3). For this release, when the peer is
not in the top-100 dialog list, return a clear error message:

```
"peer %q not found in recent dialogs — try get_messages for this peer's full history"
```

instead of silently returning zero messages.

### Change 4 — Peer resolution cache

**New file**: `internal/telegram/peercache.go`

A lightweight in-memory cache keyed by `(userID int64, peerSpec string)`:

```go
type PeerCache struct {
    mu  sync.Mutex
    m   map[peerCacheKey]*peerCacheEntry
    ttl time.Duration
    now func() time.Time
}

type peerCacheKey struct {
    userID   int64
    peerSpec string
}

type peerCacheEntry struct {
    peer      tg.InputPeerClass
    expiresAt time.Time
}
```

- Default TTL: 10 minutes (configurable via `WithTTL`).
- Cache is checked before `ContactsResolveUsername` in `ResolvePeer` when a
  non-nil cache is provided (via an optional parameter or a wrapper function
  `ResolvePeerCached`).
- On `PEER_ID_INVALID` error, the caller evicts the entry so stale access hashes
  are purged without waiting for TTL expiry.
- `PeerCache` is constructed in `cmd/server/main.go` and passed into
  `telegram.ClientPool` or used as a standalone dependency of `mcp.Server`. The
  cache is per-process (in-memory); multi-replica deployments may see cache
  misses on first hit after failover, which is acceptable.
- No persistence — lost on restart, which only causes one extra
  `ContactsResolveUsername` call per peer per pod.

Wire `PeerCache` into `mcp.Server` as an optional field (nil = no cache, full
backward compatibility):

```go
type Server struct {
    // ...
    PeerCache *telegram.PeerCache
}
```

`toolGetMessages` and `toolSendMessage` pass the cache through to the telegram
layer.

### Change 5 — Structured MTProto error code in audit slog line

**File**: `internal/mcp/tools.go` — `audit` method, and `internal/mcp/errorcatalog.go` — `mtprotoErrResult`

When `mtprotoErrResult` matches a transient or permanent catalog entry, promote
the raw MTProto code to a dedicated slog field `mtproto_code`. This field is
already scrubbed of peer/user data; the error code itself is safe to log:

```go
slog.Warn("mcp mtproto error", "tool", tool, "mtproto_code", rpcErr.Message, "http_code", rpcErr.Code)
```

The existing line in `mtprotoErrResult` already does this for the `tool` field
(line 103 in `errorcatalog.go`); extend it to explicitly include the code for
all matched entries including the transient catalog.

---

## Alternatives

### A. Only improve error messages, do not fix peer resolution

Add `PEER_FLOOD` to the error catalog and return `retry_after_seconds` without
touching `GetMessages` resolution logic. This improves the error UX and allows
clients to retry intelligently but does not eliminate the non-determinism in
`GetMessages`. Users with more than 200 dialogs would still see intermittent
"peer not found" failures. Rejected because it addresses only half the issue.

### B. Always use ResolvePeer (bypass dialog scan entirely)

Replace the `MessagesGetDialogs` scan in `GetMessages` with a direct call to
`ResolvePeer`, then call `MessagesGetHistory`. This eliminates the dialog-limit
non-determinism. However:
- `user:<id>` peers resolved via `ResolvePeer` produce `InputPeerUser{UserID:
  id, AccessHash: 0}`. Telegram requires the access hash for most operations on
  users who are not in the contact list. This causes `PEER_ID_INVALID` for those
  cases, which is a regression.
- The dialog scan provides correct access hashes for all known dialog peers.
  Removing it entirely would break the common case.
  Rejected; dialog scan should remain the primary path with the fallback as a
  supplement.

### C. Database-backed peer cache

Persist resolved `(userID, peerSpec) -> InputPeerClass` in a new `peer_cache`
table. Survives pod restarts and works across replicas. The access hash is a
Telegram-internal value that changes on channel migration; a persistent stale
entry could block a user until the TTL expires or an operator flushes the row.
In-memory cache (Change 4) is sufficient for the expected request rate and
avoids a schema migration. Rejected for this release; revisit if multi-replica
cache misses become a measured problem.

---

## Platform impact

### Migrations

None. No new database tables or columns. The peer cache is entirely in-memory.

### Backward compatibility

- MCP error response content changes for `PEER_FLOOD`: plain string becomes a
  JSON envelope. The envelope format matches the existing `FLOOD_WAIT_X` format,
  so any client already handling `FLOOD_WAIT_X` structured errors handles
  `PEER_FLOOD` the same way. Clients that treat the error string as opaque
  continue to work — they display the JSON blob as an error message.
- `GetMessages` fallback: previously returned error; now may return results.
  Strictly more capable, no regression.
- `PeerCache` field on `mcp.Server`: optional (nil = current behaviour).

### Resource impact

- `PeerCache`: bounded by `(distinct userIDs) * (distinct peerSpecs per user)`.
  For a typical deployment with O(10) users each accessing O(100) peers the
  cache holds O(1000) entries. Each entry is a pointer to a small struct
  (~100 bytes). Negligible.
- One extra `MessagesGetHistory` call per cold-miss peer resolution (fallback
  path). This replaces the previous outright failure, so it is net positive.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| `PEER_FLOOD` retry doubles latency (60s cap) | Already matches `maxFloodWaitSleep`; no change to user-visible worst case |
| Stale cache access hash causes `PEER_ID_INVALID` | Evict cache entry on `PEER_ID_INVALID`; next call re-resolves |
| Fallback `ResolvePeer` for `user:<id>` without access hash fails | Document limitation in tool description; return a clear error distinguishing "not found in dialogs and cannot resolve numerically" |
| New transient catalog needs maintenance as Telegram adds codes | Catalog is a simple Go map; adding entries is a one-line change, no migration |
