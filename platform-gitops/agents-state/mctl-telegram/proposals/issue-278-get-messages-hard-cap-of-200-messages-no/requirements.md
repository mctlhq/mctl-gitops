# Add `before_id` pagination to `get_messages`

## Context

`get_messages` (and `get_unread_messages`) enforce a hard cap of 200 messages
per call with no way to retrieve older messages. The limit clamp in
`internal/telegram/messages.go` (`if limit <= 0 || limit > 200 { limit = 50 }`)
also silently resets any out-of-range limit to 50 rather than clamping it to the
maximum, so callers cannot even tell whether the request was honoured. There is
no `before` or offset parameter on the tool, so any conversation with more than
200 messages is silently truncated to the most recent slice with no indication
that more history exists.

The Telegram MTProto `messages.getHistory` API (used under the hood in all
`MessagesGetHistoryRequest` calls) already exposes an `OffsetID` field: passing
a message ID causes the API to return `limit` messages strictly before that ID,
enabling backward keyset pagination. The codebase already applies a keyset
pattern for the audit-log tools (`get_my_audit_log`, `get_user_audit_log`) via a
`before` timestamp parameter in `internal/mcp/tools.go` (~lines 693-951). This
proposal applies the same pattern to `get_messages` using message IDs as the
cursor, which are more precise than timestamps (Telegram timestamps are
second-granularity and non-unique within a conversation).

## User stories

- AS an MCP client I WANT to pass a `before_id` message ID to `get_messages`
  SO THAT I can page backward through conversation history beyond the first 200
  messages.
- AS an MCP client I WANT the `get_messages` response to include a
  `next_before_id` cursor SO THAT I can issue the next page without having to
  inspect or compute message IDs myself.
- AS an MCP client I WANT `get_messages` to clamp an out-of-range `limit` to
  200 (not silently reset it to 50) SO THAT I get predictable behavior when I
  request more than the maximum.
- AS a developer I WANT the Local Bridge daemon (`cmd/local/daemon.go`) to
  honour `before_id` SO THAT local-mode users get the same pagination
  capability as hosted-mode users.

## Acceptance criteria (EARS)

- WHEN `get_messages` is called with a positive integer `before_id`, THE SYSTEM
  SHALL pass that value as `OffsetID` in every `MessagesGetHistoryRequest` sent
  to Telegram, returning only messages whose ID is strictly less than
  `before_id`.

- WHEN `get_messages` is called without `before_id` (or with `before_id` equal
  to zero), THE SYSTEM SHALL issue the `MessagesGetHistoryRequest` with
  `OffsetID` equal to zero, preserving the current behaviour of returning the
  most recent `limit` messages.

- WHEN `get_messages` returns one or more messages and the number of messages
  returned equals `limit`, THE SYSTEM SHALL include a `next_before_id` integer
  in the JSON response equal to the smallest message ID in the returned batch,
  so a client can pass it as `before_id` on the next call.

- WHEN `get_messages` returns fewer messages than `limit`, THE SYSTEM SHALL omit
  `next_before_id` from the JSON response (or set it to null), indicating that
  the beginning of the conversation history has been reached.

- WHEN `get_messages` is called with `limit` greater than 200, THE SYSTEM SHALL
  clamp `limit` to 200 and proceed (not reset it to 50).

- WHEN `get_messages` is called with `limit` less than or equal to zero, THE
  SYSTEM SHALL use the default of 50.

- WHILE paginating backward with successive `before_id` values, THE SYSTEM SHALL
  preserve the full peer-resolution path unchanged: dialog-list scan, direct
  fallback via `ResolvePeerCached`, and cache-evict retry on
  `PEER_ID_INVALID`/`CHANNEL_INVALID`.

- IF the Local Bridge daemon (`cmd/local`) handles the call (account mode is
  "local"), THE SYSTEM SHALL honour `before_id` and return `next_before_id` with
  the same semantics as the hosted path.

- WHILE `get_messages` is executing, THE SYSTEM SHALL record an audit row via
  `s.audit` regardless of whether `before_id` is present, using the same
  redacted peer identifier as today.

## Out of scope

- Pagination for `get_unread_messages`. Unread-message state is a
  point-in-time snapshot across all dialogs; meaningful pagination would require
  per-dialog read-pointer tracking beyond the current implementation. This is
  deferred.
- Forward pagination via an `after_id` parameter. Not requested in the issue.
- Raising the per-page cap above 200. Rate-limit and per-call cost
  considerations are unchanged.
- Changes to `list_dialogs`.
- Changes to `send_message`, `pin_message`, or any write path.

## Open questions

1. Should the limit clamp in `GetUnreadMessages` also be fixed from
   "reset to 50 if > 200" to "clamp to 200 if > 200"? The issue does not
   mention it, but it is the same inconsistency in the same file. This proposal
   recommends fixing both for consistency; the reviewer can descope
   `GetUnreadMessages` if preferred.

2. The `next_before_id` field could alternatively be `0` (int zero) rather than
   omitted when there are no more pages. This proposal uses `omitempty` on a
   `*int` pointer (nil = no more pages) to keep the response self-describing and
   consistent with Go/JSON convention. If the connector clients expect a
   concrete `0`, change the field type to `int` and drop `omitempty`.

3. Telegram's `messages.getHistory` with `OffsetID=X` returns messages with ID
   strictly less than X. This means passing the minimum ID of the current page as
   `before_id` on the next call is correct. If the Telegram API documentation for
   a specific chat type (e.g. basic groups via `MessagesMessages` vs channels via
   `MessagesChannelMessages`) behaves differently, the implementer should verify
   with a live test account.
