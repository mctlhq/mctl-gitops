# Distinguish Transient Risk Gates from Permanent Permission Failures

## Context

`get_messages`, `get_unread_messages`, and `send_message` intermittently fail
with an error that is indistinguishable from a hard permission denial. The same
call with identical parameters later succeeds. The root cause is a combination
of two problems: (1) unclassified Telegram-side transient errors (e.g.,
`PEER_FLOOD`) that fall through the existing error catalog and surface as opaque
failures; and (2) non-deterministic peer resolution in `GetMessages` /
`GetUnreadMessages`, which uses a capped `MessagesGetDialogs` scan (limit 200 /
100) to locate a peer — a peer absent from the current top-N results causes a
spurious "peer not found in dialogs" failure on some calls and succeeds on
others as dialog ordering shifts.

Both problems produce errors that the caller cannot distinguish from a genuine
permission failure, leading to confusing UX and difficulty diagnosing the issue
in the audit log. The fix must classify transient errors distinctly, provide
retry guidance, improve peer resolution reliability, and emit enough audit
detail for operators to diagnose gate decisions without logging sensitive data.

## User stories

- AS a connector user I WANT transient Telegram rate or risk-gate errors to
  carry a clear `error_type` and `retry_after_seconds` hint SO THAT I can
  distinguish them from permanent permission failures and retry automatically.
- AS a connector user I WANT `get_messages` to succeed for peers that are not
  in the top-N most-recent dialogs SO THAT the tool is reliable regardless of
  how many dialogs I have.
- AS an operator I WANT the audit log to record the specific Telegram error code
  when a tool call fails with a gate-like error SO THAT I can diagnose
  non-deterministic failures without blind retrying.
- AS an MCP client developer I WANT a machine-readable `error_type` field in
  all error responses SO THAT my client can branch on `RISK_GATED` vs
  `PERMISSION_DENIED` vs `RATE_LIMITED` programmatically.

## Acceptance criteria (EARS notation)

### Error classification

- WHEN a Telegram API call returns a `PEER_FLOOD` error THE SYSTEM SHALL return
  a structured JSON error envelope with `error_type="RISK_GATED"`,
  `retry_after_seconds=60`, a human-readable `message`, and an `action` hint
  — not a generic `<tool>: <err>` string.
- WHEN a Telegram API call returns a `FLOOD_WAIT_X` or `SLOWMODE_WAIT_X` error
  THE SYSTEM SHALL continue to return the existing envelope with
  `error_type="flood_wait"` or `error_type="slowmode_wait"` and the parsed
  `retry_after_seconds` value (existing behaviour, preserved).
- WHEN an MTProto error code is not in the known-permanent catalog and is not
  a recognised transient code THE SYSTEM SHALL include the raw MTProto error
  code (e.g., `PEER_FLOOD`) in the slog audit line at `Warn` level so it
  appears in Loki without logging peer or message body.
- IF the local send gate (`evaluateSendGate`) blocks a send due to a missing
  scope or flag THEN THE SYSTEM SHALL return a dry-run result with
  `dry_reason` clearly identifying whether the block is a missing scope, a
  server flag, or a per-account flag — without changing the existing
  `dry_reason` strings (they already satisfy this; no change needed).

### Peer resolution reliability

- WHEN `get_messages` is called with a peer that is not present in the
  `MessagesGetDialogs` response (due to pagination limits or ordering) THE
  SYSTEM SHALL fall back to direct peer resolution via `ResolvePeer` and
  attempt `MessagesGetHistory` with the resolved `InputPeerClass` before
  returning a "peer not found" error.
- WHEN `get_unread_messages` is called with an explicit `peer` argument and
  that peer is not found in the first 100 dialogs THE SYSTEM SHALL fall back
  to direct peer resolution to check unread count and fetch messages.
- WHILE a peer has been successfully resolved within the last 10 minutes for a
  given user THE SYSTEM SHALL reuse the cached `InputPeerClass` to avoid
  re-issuing a `ContactsResolveUsername` or dialog-scan API call on each
  invocation.

### Retry behaviour

- WHEN a `PEER_FLOOD` error is returned from a Telegram API call and fewer than
  `maxFloodWaitRetries` attempts have been made THE SYSTEM SHALL wait 60 seconds
  (capped, same as `maxFloodWaitSleep`) and retry, consistent with the existing
  `FLOOD_WAIT_X` retry loop in `borrowWithRetry`.
- WHILE retrying a transient error THE SYSTEM SHALL honour context cancellation
  and return `ctx.Err()` immediately if the context is done.

### Audit log

- WHEN any tool call fails with a Telegram MTProto error THE SYSTEM SHALL write
  the raw MTProto error code to `slog` at `Warn` level (already done in
  `mtprotoErrResult`; extended to cover previously unhandled codes).
- WHEN a peer resolution falls back to the direct-resolution path THE SYSTEM
  SHALL emit a `slog.Debug` line noting `"peer not in dialog list, falling back
  to direct resolution"` so the resolution path is traceable.

## Out of scope

- Changes to OAuth, session management, or access tier logic.
- Database schema changes (no new columns or tables).
- Changes to the ChatGPT connector or any other connector — the shared layer is
  `mctl-telegram`; connector-specific configuration is out of scope.
- Full distributed peer-resolution cache backed by Redis or the database.
- Automatic account-level send_enabled toggling based on risk signals.
- Changes to the Local Bridge daemon path (`bridgeCall`); the bridge forwards
  calls as-is and any gate errors it returns are surfaced unchanged.

## Open questions

1. **PEER_FLOOD exact retry duration**: The `PEER_FLOOD` error (code 420) does
   not always carry a numeric suffix. The proposal defaults to 60 seconds.
   Should this be a configurable env var (`PEER_FLOOD_RETRY_SECONDS`) or is the
   hardcoded 60-second cap sufficient given `maxFloodWaitSleep` is already 60s?

2. **Peer resolution cache scope**: The proposal caches resolved `InputPeerClass`
   per `(userID, peerSpec)` in memory for 10 minutes. If a user's peer changes
   access hash (e.g., channel migration), a stale cache entry causes a 10-minute
   window of failures. Is a shorter TTL (e.g., 5 minutes) preferred, or should
   cache invalidation be error-driven (evict on `PEER_ID_INVALID`)?

3. **GetUnreadMessages fallback scope**: The fallback for `get_unread_messages`
   with an explicit peer requires resolving the peer and then calling
   `MessagesGetHistory` — but the current implementation relies on
   `dialog.UnreadCount` from the dialog list. Without the dialog, unread count
   is not available. The fallback would fetch recent messages and cannot
   accurately filter to only unread ones. Should the tool (a) skip the unread
   filter and return recent messages with a notice, or (b) only fall back for
   `get_messages` and leave `get_unread_messages` returning an empty result
   (current behaviour) with an improved error message?
