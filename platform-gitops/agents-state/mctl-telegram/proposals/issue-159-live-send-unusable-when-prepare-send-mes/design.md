# Design: issue-159-live-send-unusable-when-prepare-send-mes

## Current state

### send_message tool

`internal/mcp/tools.go` line 244 defines `toolSendMessage()`. It accepts four
inputs: `peer`, `text`, `mode` ("send" or "draft", default "send"), and the
optional `confirmation_id`. The handler logic is:

1. `evaluateSendGate()` (tools.go:865) — checks mode, `ALLOW_SEND` server flag,
   identity scope `telegram:messages:send`, and per-account `send_enabled` from
   the database. Returns `(realSend bool, dryReason string)`.
2. If `realSend && confID != ""` — calls `s.Confirms.Consume(confID, userID,
   HashSendPayload(peer, text))` (confirm.go:81). Any `Consume` error downgrades
   `realSend` to `false` and sets a `dryReason` string.
3. If `realSend && confID == ""` — calls `evaluateDirectSendLimiter()` (line 891)
   which applies the per-peer rate limit (`PeerSendCap=20/PeerWindow=1h` from
   `internal/audit/ratelimit.go`).
4. Executes either a dry-run preview or a real send via `Pool.Borrow` /
   `bridgeCall`.

The `confirmation_id` parameter was made optional in v0.29.1. The
`destructiveHintAnnotation` was removed from `send_message` in v0.29.3 (CHANGELOG
line 17; comment at tools.go:245-247 explains the rationale). Current default mode
was changed from "draft" to "send" in v0.29.4.

### prepare_send_message — removed

`prepare_send_message` was removed in v0.29.2 (CHANGELOG lines 27-28). No tool
currently calls `ConfirmStore.Issue()` for the "send" action. The confirmation
infrastructure in `internal/mcp/confirm.go` is fully intact:
- `ConfirmStore.Issue(userID, action, payloadHash)` mints a token (line 43).
- `HashSendPayload(peer, text)` computes the canonical SHA-256 hash (line 124).
- `ConfirmationTTL = 5 * time.Minute` (line 14).
- Token ID format is `"c" + action[:1] + "_" + hex(16 random bytes)`, producing
  `cs_<32-hex>` for action "send" (line 49).

### prepare_pin_message — the working reference

`toolPreparePinMessage()` (tools.go:406) is the analogous tool for the pin flow.
Key characteristics:
- Registered with `mcplib.WithReadOnlyHintAnnotation(true)` (line 409).
- No destructive annotation.
- Applies `s.Limiter.AllowPeer(id, peerRedacted, audit.PeerSendCap,
  audit.PeerWindow)` before issuing (line 442).
- Calls `s.Confirms.Issue(id.UserID, action, hash)` (line 451).
- Returns `{confirmation_id, peer_redacted, message_id, unpin, payload_hash,
  expires_at}`.
- Makes no Telegram MTProto call.
- Audits under `prepare_pin_message` (line 455).

`toolPinMessage()` (tools.go:468) pairs with it, using `WithDestructiveHintAnnotation(true)`.
The pin flow is confirmed working through the ChatGPT connector.

### MCP server registration

`internal/mcp/server.go` line 66, function `HTTPHandler()`, registers all tools
via `srv.AddTool()`. Current list (lines 72-84) does not include
`prepare_send_message`. Registration order is cosmetic; there is no dependency
between `AddTool` calls.

### Connector-layer blocking

The ChatGPT connector intercepts MCP tool calls before forwarding them to the
server. Tools annotated `destructive=true` are blocked pre-call. Tools annotated
`readOnly=true` appear to pass through. Non-annotated tools may pass or be blocked
based on the tool name and description text. The server has no visibility into a
blocked call — the handler is never invoked. This matches the issue description
("This tool call was blocked by OpenAI's safety checks") and the observation that
the Claude connector does not apply the same filter.

## Proposed solution

Re-introduce `prepare_send_message` as a read-only tool that exactly mirrors
`prepare_pin_message`, adapting it for the send payload.

### internal/mcp/tools.go — add toolPrepareSendMessage()

Add a new method on `*Server` after `toolSendMessage()`:

```go
func (s *Server) toolPrepareSendMessage() (mcplib.Tool, mcpserver.ToolHandlerFunc) {
    tool := mcplib.NewTool("prepare_send_message",
        mcplib.WithTitleAnnotation("Prepare a message send"),
        mcplib.WithReadOnlyHintAnnotation(true),
        mcplib.WithDescription(`Snapshot a send_message call you intend to confirm momentarily.

Returns a one-shot confirmation_id valid for 5m that send_message must echo back.
The token is bound to (peer, text) — changing either between prepare and confirm
invalidates it. The prepare step is read-only and makes no Telegram network call.

Inputs (required): peer, text.
Output: {confirmation_id, peer_redacted, expires_at, payload_hash}.`),
        mcplib.WithString("peer",
            mcplib.Required(),
            mcplib.Description("Peer to send to (@username, user:<id>, chat:<id>, channel:<id>)."),
        ),
        mcplib.WithString("text",
            mcplib.Required(),
            mcplib.Description("Message text to send."),
        ),
    )
    handler := func(ctx context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
        startedAt := time.Now()
        id := auth.From(ctx)
        if id == nil {
            return mcplib.NewToolResultError("authentication required"), nil
        }
        args := req.GetArguments()
        peer := stringArg(args, "peer", "")
        text := stringArg(args, "text", "")
        if peer == "" || text == "" {
            return mcplib.NewToolResultError("peer and text are required"), nil
        }
        peerRedacted := telegram.RedactPeer(peer)
        if s.Limiter != nil && !s.Limiter.AllowPeer(id, peerRedacted, audit.PeerSendCap, audit.PeerWindow) {
            s.audit(ctx, id, "prepare_send_message:rate_limited", peerRedacted, nil, startedAt)
            return mcplib.NewToolResultError("per-peer rate limit reached (20/hour to one peer) — wait or pick a different recipient"), nil
        }
        hash := HashSendPayload(peer, text)
        c, err := s.Confirms.Issue(id.UserID, "send", hash)
        if err != nil {
            return toolErr("prepare_send_message: %v", err), nil
        }
        s.audit(ctx, id, "prepare_send_message", peerRedacted, nil, startedAt)
        return jsonResult(map[string]any{
            "confirmation_id": c.ID,
            "peer_redacted":   peerRedacted,
            "expires_at":      c.ExpiresAt.UTC(),
            "payload_hash":    hash,
        })
    }
    return tool, handler
}
```

Notable design choices:
- `readOnlyHintAnnotation=true` — the critical flag. No Telegram call happens, so
  the annotation is accurate and should allow the tool past the connector's safety
  filter.
- `AllowPeer` rate-limit applied at prepare time using the same constants as the
  direct send path (`PeerSendCap=20`, `PeerWindow=1h`). Prevents unlimited token
  minting for a single peer.
- No `Pool.Borrow` or `bridgeCall` — the tool is pure server-side logic. Local
  Bridge mode does not apply.
- `HashSendPayload(peer, text)` is already exported from `confirm.go:124` and
  used by `send_message`'s `Consume` call — no new hashing code needed.

### internal/mcp/server.go — register the tool

In `HTTPHandler()` (line 75), add after `srv.AddTool(s.toolSendMessage())`:

```go
srv.AddTool(s.toolPrepareSendMessage())
```

### internal/mcp/tools.go — improve dry-reason for expired/missing token

In the `switch` block inside `toolSendMessage()` at lines 293-299 (the
`ErrConfirmationNotFound` / `default` branch), change the `dryReason` string from:

```go
dryReason = "confirmation_id not found, expired, or already used"
```

to:

```go
dryReason = "confirmation_id not found, expired, or already used — call prepare_send_message to obtain a fresh token"
```

This explicitly routes the LLM to the correct recovery tool rather than leaving
it to infer the next step.

### internal/mcp/tools.go — update send_message description

Append to the existing description of `toolSendMessage()` (line 250-259):

```
Two-step flow (recommended for connectors that apply safety checks): call
prepare_send_message first to get a confirmation_id, then pass it here. The
prepare step is read-only and valid for 5 minutes. Single-step (no prepare): omit
confirmation_id — the per-peer rate limit is applied directly instead.
```

No other files require changes.

## Alternatives

### Alternative 1: Keep prepare_send_message removed; rely solely on the direct send_message path

The v0.29.1-0.29.4 changes (remove destructiveHint, make confirmation_id optional,
change default mode to "send") are all iterations of this approach. The issue
demonstrates it is insufficient: `send_message` itself is still blocked by the
connector's safety filter despite having no destructive annotation. The filter
appears to evaluate tool name and description semantics beyond just annotations.
The read-only prepare-then-confirm pattern used by the working pin flow offers a
structural workaround that does not depend on the connector understanding our
annotations correctly. Dropped because the direct path demonstrably fails on
ChatGPT.

### Alternative 2: Rename send_message to reduce safety-filter triggering

Tool name changes (e.g., `compose_message`, `deliver_message`) are a breaking API
change for all existing integrations and documentation. There is no confirmed
evidence that the blocking is name-based rather than annotation- or
description-based. The risk to existing Claude connector users and any direct API
consumers is not justified by the speculative benefit. Dropped.

### Alternative 3: Remove the <telegram-content untrusted="true"> wrapper on read responses

The issue notes reads are also blocked, possibly by Cyrillic text in channel
titles or message content. The `<telegram-content>` wrapper (tools.go:237-240) is
a deliberate prompt-injection defence. Removing it trades a demonstrated security
control for an uncertain fix to a connector-layer problem. Even if the wrapper
tags trigger the filter, the underlying message text would still do so without the
wrapper. This alternative does not address the send problem at all. Dropped; the
read blocking is noted as an open question for a separate investigation.

## Platform impact

- **Backward compatibility**: `confirmation_id` remains optional in `send_message`.
  Existing clients that do not call `prepare_send_message` are completely
  unaffected. The new tool is purely additive.
- **In-memory state**: `ConfirmStore` (confirm.go:29) already holds pin
  confirmations. Send confirmations add entries of the same fixed size. The 5-
  minute TTL bounds growth; a pod serving heavy traffic would accumulate at most
  one entry per outstanding prepare call. `Sweep()` (confirm.go:106) exists for
  future active eviction if memory pressure warrants it.
- **Rate-limit interaction**: A user who calls `prepare_send_message` and then
  calls `send_message` with the returned `confirmation_id` consumes one rate-limit
  slot at prepare time and bypasses the direct-send limiter check in `send_message`
  (tools.go:302-308, guarded by `confID == ""`). A user who skips prepare and
  calls `send_message` directly consumes a slot at send time. There is no
  double-counting because the two paths are mutually exclusive.
- **Pod restarts**: Confirmations are in-memory and are lost on restart. This is
  existing behaviour for pin confirmations and is documented (confirm.go:17-19).
  The 5-minute TTL means the user simply calls `prepare_send_message` again.
- **No database schema changes or migrations.**
- **No changes to Dockerfile, docker-compose, or deploy manifests.**
- **Rollback**: Delete `toolPrepareSendMessage()` from `tools.go` and remove its
  `AddTool` call from `server.go`. The dry-reason string update and description
  update can be left in place with no side-effects or separately reverted. No
  persistent state is affected.
