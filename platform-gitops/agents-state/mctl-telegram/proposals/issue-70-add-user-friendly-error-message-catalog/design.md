# Design: issue-70-add-user-friendly-error-message-catalog

## Current state

### Error flow from MTProto call to MCP result

1. A tool handler in `internal/mcp/tools.go` calls `s.Pool.Borrow()`.
2. `Borrow()` in `internal/telegram/clientpool.go` (lines 103-158) invokes the user's
   `fn(ctx, client)`. If `fn` returns an error, `sessionErrorFor()` (lines 40-49)
   checks whether it is one of the ten session-class MTProto codes
   (`AUTH_KEY_UNREGISTERED`, `AUTH_KEY_INVALID`, `SESSION_REVOKED`, `SESSION_EXPIRED`,
   `USER_DEACTIVATED`, `USER_DEACTIVATED_BAN`, `SESSION_PASSWORD_NEEDED`) using
   `tgerr.Is()` from `github.com/gotd/td/tgerr`. Matching errors are wrapped with a
   db-sentinel (`db.ErrSessionRevoked` or `db.ErrSessionUnauthorized`) and returned.
   Non-matching errors are returned as-is.
3. Back in the tool handler, `borrowErrResult(tool, err)` (lines 913-918) calls
   `sessionErrText(err)`. If that returns a non-empty string it is wrapped with
   `mcplib.NewToolResultError()`. Otherwise the code falls through to
   `toolErr("%s: %v", tool, err)` which embeds the raw Go error string — which for
   MTProto errors contains the tgerr message such as `rpc error code 420:
   FLOOD_WAIT_30`.

### What `tgerr.Error` looks like

`github.com/gotd/td/tgerr` exports an `Error` struct with an integer `Code` field
(420 for FLOOD_WAIT, 400 for most input errors) and a string `Message` field
(e.g., `"FLOOD_WAIT_30"`, `"PEER_ID_INVALID"`). The package also exports
`tgerr.Is(err, codes...)` for string-code matching and exposes the raw type for
direct inspection via `errors.As`.

### Gap

All errors outside the session-class reach callers as raw tgerr strings. Test
evidence at `internal/telegram/clientpool_test.go` lines 35-36 explicitly notes
`tgerr.New(400, "PEER_ID_INVALID")` and `tgerr.New(420, "FLOOD_WAIT_30")` as
non-session cases. The audit redact test at `internal/audit/redact_test.go` lines
32-34 further confirms `FLOOD_WAIT_30` passes through to logs verbatim. No code
today maps these to user-friendly text.

---

## Proposed solution

### New file: `internal/mcp/errorcatalog.go`

This file owns the entire catalog and the two helper functions. Locating it in the
`mcp` package is consistent with `sessionErrText()`, which already lives in
`internal/mcp/tools.go` and is the only existing user-message formatter. The
`telegram` package stays focused on MTProto transport; message formatting is an MCP
concern.

```
package mcp

// catalogEntry holds a user-facing message and an optional next-action hint.
type catalogEntry struct {
    message string
    action  string
}

// mtprotoErrCatalog maps exact MTProto error code strings (the Message field of
// tgerr.Error, uppercase with underscores) to user-facing entries. Codes with a
// numeric suffix (FLOOD_WAIT_X, SLOWMODE_WAIT_X) are matched by prefix in
// mtprotoErrResult; list only the base prefix here when the number varies.
var mtprotoErrCatalog = map[string]catalogEntry{
    "PEER_ID_INVALID": {
        message: "The peer ID is not valid for this account. Use @username, user:<id>, chat:<id>, or channel:<id>.",
        action:  "Check the peer argument and retry.",
    },
    "USERNAME_INVALID": {
        message: "The username is not valid.",
        action:  "Verify the @username and retry.",
    },
    "USERNAME_NOT_OCCUPIED": {
        message: "No Telegram account or channel has that username.",
        action:  "Verify the @username and retry.",
    },
    "CHAT_FORBIDDEN": {
        message: "The connected Telegram account does not have access to that chat.",
        action:  "Confirm the account is a member of the chat.",
    },
    "CHAT_WRITE_FORBIDDEN": {
        message: "The connected Telegram account cannot send messages to that chat.",
        action:  "Confirm the account has send permission.",
    },
    "USER_BANNED_IN_CHANNEL": {
        message: "The connected account has been banned from that channel.",
        action:  "The account cannot be used with this channel.",
    },
    "MESSAGE_ID_INVALID": {
        message: "That message ID does not exist in the chat.",
        action:  "Verify the message ID and retry.",
    },
    "MSG_ID_INVALID": {
        message: "That message ID does not exist in the chat.",
        action:  "Verify the message ID and retry.",
    },
    "INPUT_USER_DEACTIVATED": {
        message: "The target account has been deactivated.",
        action:  "",
    },
    "PHONE_NUMBER_INVALID": {
        message: "The phone number format is not valid.",
        action:  "Use E.164 format (e.g. +12025551234).",
    },
    "CHANNEL_PRIVATE": {
        message: "That channel is private and the account is not a member.",
        action:  "The account must be invited before it can access this channel.",
    },
    "USER_NOT_PARTICIPANT": {
        message: "The account is not a participant of that chat or channel.",
        action:  "Confirm the account has been added to the chat.",
    },
}
```

**Prefix-matched codes** (`FLOOD_WAIT_X`, `SLOWMODE_WAIT_X`): these cannot be in the
map because the numeric suffix varies. They are handled by a dedicated parsing helper.

#### `floodWaitSeconds(code string) (seconds int, ok bool)`

Strips the `FLOOD_WAIT_` prefix (or `SLOWMODE_WAIT_`) and parses the trailing integer.
Returns `(0, false)` when the code does not match or the suffix is not a valid integer.

#### `mtprotoErrResult(tool string, err error) *mcplib.CallToolResult`

1. Uses `errors.As(err, &rpcErr)` to extract the `*tgerr.Error`.
2. If the code is not a `tgerr.Error` at all, returns `""` (no match).
3. Logs the original MTProto code at `slog.Warn("mcp mtproto error", "tool", tool, "code", rpcErr.Message, "rpc_code", rpcErr.Code)` so it is always preserved in Loki regardless of what the user sees.
4. Checks `floodWaitSeconds` for `FLOOD_WAIT_` and `SLOWMODE_WAIT_` prefix; on match,
   returns `mcplib.NewToolResultError(jsonFloodWait(...))` with a JSON payload (see
   below).
5. Looks up `rpcErr.Message` in `mtprotoErrCatalog`; on match, returns
   `mcplib.NewToolResultError(entry.message + " " + entry.action)` (plain string, with
   action appended only when non-empty).
6. Returns `nil` on no match, so the caller can fall through.

#### FLOOD_WAIT JSON envelope

```json
{
  "error": "flood_wait",
  "message": "Telegram rate limit reached. Wait 30 seconds before retrying.",
  "retry_after_seconds": 30,
  "action": "Wait 30 seconds, then retry the same tool call."
}
```

`json.Marshal` is used to produce a canonical JSON string; the result is passed
directly to `mcplib.NewToolResultError`. Agents that inspect error content as JSON
get machine-readable `retry_after_seconds`; agents that treat error text as prose
still receive a readable sentence in the `message` field.

SLOWMODE_WAIT uses the same envelope shape with `"error": "slowmode_wait"`.

### Minimal change to `internal/mcp/tools.go`

`borrowErrResult()` gains one additional call between the existing `sessionErrText`
check and the final fallback:

```go
func borrowErrResult(tool string, err error) *mcplib.CallToolResult {
    if friendly := sessionErrText(err); friendly != "" {
        return mcplib.NewToolResultError(friendly)
    }
    if res := mtprotoErrResult(tool, err); res != nil {
        return res
    }
    return toolErr("%s: %v", tool, err)
}
```

No other call sites change. The session sentinel path is fully preserved.

### Logging invariant

The `slog.Warn` inside `mtprotoErrResult` uses the field name `"code"` (not
`"message"` or `"error"`) so it does not conflict with existing slog field names in
`audit()`. Because MTProto error codes like `FLOOD_WAIT_30` contain no sensitive data
(they are protocol constants, not user content), no redaction is needed. The existing
`audit.ScrubText` call in `audit()` already handles the err string separately.

---

## Alternatives

### Alternative 1: catalog in `internal/telegram/errors.go`

The `telegram` package already contains `sessionErrorFor()` which classifies
session-class errors. Extending it with a `FriendlyMessage(err error) string`
function would keep all MTProto error knowledge in one package.

**Rejected** because `internal/telegram` is responsible for MTProto transport and
session lifecycle, not for user-facing copy. Placing message strings there would
violate the existing separation (the `mcp` package already owns `sessionErrText` and
all other user-visible text). It would also require the `telegram` package to import
formatting concerns (JSON marshaling) currently absent from it.

### Alternative 2: extend `sessionErrorFor()` to cover all error types

`sessionErrorFor()` in `clientpool.go` could be generalised to return a new
multi-valued type carrying both a Go sentinel and a friendly string. All callsites
would need to be updated.

**Rejected** because `clientpool.go` manages pool lifecycle and session validity
checks (TTL, revocation). Embedding presentation-layer text there increases coupling
and makes the file harder to reason about. The existing function has a clear,
narrow contract; changing its signature would require updates across `clientpool.go`,
`tools.go`, and any future callers.

### Alternative 3: a dedicated error wrapper type in `internal/telegram`

Define a `type FriendlyError struct { Cause error; Message string }` wrapping
tgerr errors at the call sites in `messages.go`, `send.go`, `dialogs.go`, etc.

**Rejected** because it requires modifying every function in `internal/telegram` that
calls Telegram API methods, a large blast radius for minimal benefit. The catalog
lookup at the MCP boundary achieves the same result with changes confined to two
files (`errorcatalog.go` and a four-line edit in `tools.go`).

---

## Platform impact

### Migrations

None. The catalog is pure Go code with no database schema changes.

### Dependencies

None. `github.com/gotd/td/tgerr` is already an indirect transitive dependency
imported in `internal/telegram/clientpool.go`. The `errors.As` pattern and
`encoding/json` are from the standard library.

### Backward compatibility

- Success tool responses: unchanged.
- Session-error tool responses: unchanged (existing `sessionErrText` path runs first).
- Non-catalog MTProto errors: unchanged (still fall through to generic `toolErr`).
- Catalog-matched plain-string errors: callers that parse error text as prose receive
  a more readable string. This is a breaking change only if a caller pattern-matches
  on the old raw code string — no known callers do this.
- FLOOD_WAIT / SLOWMODE_WAIT errors: these now return JSON instead of a raw tgerr
  string. Any caller that expected the raw tgerr form must be updated. In practice
  the prior format was not documented or machine-parseable, so no regression contract
  exists.

### Resource impact

The catalog map is a package-level `var` (small constant memory). The `errors.As`
call adds negligible overhead per tool invocation (errors only).

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| A catalog entry contains incorrect advice that misleads users | Entries reviewed in PR; catalog is small and explicit |
| FLOOD_WAIT JSON string confuses an MCP client expecting plain text | JSON always contains a readable `message` field; document the format in the code comment |
| A future tgerr.Error code matches a catalog entry prefix unexpectedly | Full-code exact-match for catalog; prefix match only for FLOOD_WAIT_ and SLOWMODE_WAIT_ families |
| slog.Warn call leaks sensitive data in the code field | MTProto codes are protocol constants with no user content; confirmed by audit/redact_test.go line 32-34 |
