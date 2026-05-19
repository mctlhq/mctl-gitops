# Add user-friendly error message catalog for MTProto errors

## Context

Tool responses in mctl-telegram currently expose raw MTProto error codes such as
`SESSION_REVOKED`, `AUTH_KEY_INVALID`, `FLOOD_WAIT_30`, and `PEER_ID_INVALID` directly
to callers via `mcplib.NewToolResultError`. These codes are Telegram protocol internals:
they are opaque to human users and require special interpretation by LLM agents that
consume MCP tool output. The problem is systematic — every non-session MTProto error
falls through `borrowErrResult()` in `internal/mcp/tools.go` to a generic
`toolErr("%s: %v", tool, err)` which embeds the raw tgerr string verbatim.

A partial fix already exists for session errors: `sessionErrText()` in
`internal/mcp/tools.go` maps four db-sentinel errors (`ErrSessionRevoked`,
`ErrSessionExpired`, `ErrSessionUnauthorized`, `ErrNoActiveSession`) to actionable
prose. This proposal extends that pattern to the remaining MTProto error classes,
with additional structure for rate-limit errors so agents can backoff correctly.

## User stories

- AS a human user I WANT tool error messages that explain what went wrong in plain
  English SO THAT I can take a corrective action without having to look up Telegram
  protocol documentation.
- AS an LLM agent I WANT FLOOD_WAIT errors to include the exact wait duration as a
  machine-readable field SO THAT I can sleep the correct number of seconds and retry
  without guessing or polling.
- AS an LLM agent I WANT peer-resolution errors to describe what format the peer
  argument accepts SO THAT I can correct the argument without a trial-and-error loop.
- AS a developer diagnosing a production issue I WANT the original MTProto error code
  preserved in server logs SO THAT I can correlate user-visible messages with Telegram
  protocol documentation.

## Acceptance criteria (EARS)

- WHEN a tool call returns a FLOOD_WAIT_X MTProto error THE SYSTEM SHALL return an
  `IsError` MCP result whose content is a JSON object containing `"error": "flood_wait"`,
  a human-readable `"message"` field, a numeric `"retry_after_seconds"` field equal to X,
  and an `"action"` field telling the agent to wait and retry.
- WHEN a tool call returns a SLOWMODE_WAIT_X MTProto error THE SYSTEM SHALL return an
  `IsError` MCP result whose content is a JSON object containing `"error":
  "slowmode_wait"`, a human-readable `"message"` field, and a numeric
  `"retry_after_seconds"` field equal to X.
- WHEN a tool call returns PEER_ID_INVALID, USERNAME_INVALID, or
  USERNAME_NOT_OCCUPIED THE SYSTEM SHALL return a friendly error message explaining the
  peer reference could not be resolved and listing the accepted peer formats
  (`@username`, `user:<id>`, `chat:<id>`, `channel:<id>`).
- WHEN a tool call returns CHAT_FORBIDDEN or CHAT_WRITE_FORBIDDEN THE SYSTEM SHALL
  return a friendly error message explaining the connected Telegram account does not
  have permission to access or write to that chat.
- WHEN a tool call returns INPUT_USER_DEACTIVATED THE SYSTEM SHALL return a friendly
  error message stating the target account has been deactivated.
- WHEN a tool call returns MESSAGE_ID_INVALID or MSG_ID_INVALID THE SYSTEM SHALL
  return a friendly error message stating the message ID does not exist in the given
  chat.
- WHEN the catalog matches a MTProto error THE SYSTEM SHALL emit a `slog.Warn` log
  line containing the original MTProto error string before returning the friendly
  message, so the raw code is visible in Loki/structured logs.
- WHEN a MTProto error code is not covered by the catalog THE SYSTEM SHALL fall
  through to the existing generic `toolErr("%s: %v", tool, err)` behaviour unchanged.
- IF an error matches a session sentinel (ErrSessionRevoked, ErrSessionExpired,
  ErrSessionUnauthorized, or ErrNoActiveSession) THEN THE SYSTEM SHALL continue to use
  the existing `sessionErrText()` path with no change in behaviour or message text.
- WHILE constructing a friendly error message THE SYSTEM SHALL NOT include raw MTProto
  error codes in the `message` or `action` fields shown to end users.
- WHEN a catalog entry has an associated action hint THE SYSTEM SHALL include it as an
  `"action"` field (JSON errors) or as a trailing sentence (plain-string errors).

## Out of scope

- Error catalog coverage for the OAuth / enable-access flows in `internal/oauth/`.
- Retry logic or automatic backoff inside the server itself; agents are responsible
  for waiting and retrying.
- Internationalization or localization of error messages.
- Changes to the Local Bridge daemon error path; bridge errors already have hand-written
  friendly messages in `bridgeCall()`.
- Modifying the MCP tool schema or adding new tool output fields; the catalog affects
  only the error result text, not success response shapes.
- Coverage for gotd connection-layer errors (TLS, DNS) beyond a generic network
  fallback entry.

## Open questions

1. **FLOOD_WAIT JSON envelope vs. plain string.** The issue asks for FLOOD_WAIT
   duration as "structured data". The current error path uses
   `mcplib.NewToolResultError(string)`. The proposal encodes a JSON object as that
   string. Callers that already parse error text as plain prose will still receive
   readable content, but callers that expect plain text may receive a JSON literal.
   Confirm whether all known consumers (Claude Desktop, mctl CLI, third-party MCP
   clients) can handle a JSON-encoded error string, or whether a different encoding
   (e.g., a comment prefix) is preferred.

2. **Hardcoded re-authentication URL.** The issue example mentions
   `tg.mctl.ai/account`. Action hints for session errors already contain this URL via
   `sessionErrText()`. The catalog's action hints for non-session errors (e.g.,
   CHAT_FORBIDDEN where re-auth is not relevant) will not include it. Confirm whether
   the re-auth URL should also be injected for access-denied errors where the fix
   might be to reconnect with a different account.

3. **SLOWMODE_WAIT format.** `SLOWMODE_WAIT_X` is a 400-class error (not 420 like
   FLOOD_WAIT) and its X is in seconds. Confirm whether agents need the same
   structured JSON envelope for SLOWMODE_WAIT, or whether a plain friendly string
   ("Slow mode is active; wait X seconds") is sufficient.
