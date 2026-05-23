# Restore prepare_send_message and Improve Connector-Blocked Send Diagnostics

## Context

The ChatGPT connector applies an OpenAI content-safety filter that can block MCP
tool calls before they ever reach `mctl-telegram`. The server never executes the
handler; from its perspective the call simply never arrived. `send_message`
requires either a direct unconfirmed path (rate-limited) or a `confirmation_id`
from a prepare step. The `prepare_send_message` tool was removed in v0.29.2 to
address a previous issue, but that removal left the `confirmation_id` path in
`send_message` with no tool to seed it. Simultaneously, the direct path through
`send_message` may itself be blocked by the connector's safety filter, leaving
users with only the `mode="draft"` fallback. Reads are also affected: the same
filter blocks `get_unread_messages` and `get_messages` calls when the peer title
or input text contains non-ASCII characters (observed: Cyrillic). The analogous
pin flow (`prepare_pin_message` + `pin_message`) works because
`prepare_pin_message` carries `readOnlyHintAnnotation=true`, which the filter
appears to treat more permissively.

The net result is that a ChatGPT connector user cannot deliver messages or read
channel content even though their Telegram session, scopes, and per-account
`send_enabled` flag are all valid. The Claude connector handles the identical
workflow without interference, confirming this is a connector-layer issue rather
than a server misconfiguration.

## User stories

- AS a ChatGPT connector user I WANT a read-only prepare step for sends SO THAT
  the safety filter can clear the first step independently from the mutating send
  step, giving me a path to real delivery.
- AS a ChatGPT connector user I WANT the error returned when a prepare or send is
  safety-gated to be clearly distinguishable from a scope or flag permission
  failure SO THAT I (or the LLM acting on my behalf) can take the correct
  recovery action rather than treating it as a permanent block.
- AS an MCP client developer I WANT `prepare_send_message` to mirror the
  `prepare_pin_message` pattern SO THAT the two destructive write flows are
  consistent and the two-step prepare-confirm model is uniformly available.
- AS an operator I WANT the prepare step to apply the same per-peer rate limit as
  the direct send path SO THAT adding the prepare tool does not bypass existing
  abuse controls.

## Acceptance criteria (EARS)

- WHEN `prepare_send_message` is called with a non-empty `peer` and `text`, THE
  SYSTEM SHALL issue a confirmation token with ID prefix `cs_` (format
  `cs_<32-hex>`), 5-minute TTL, and return
  `{confirmation_id, peer_redacted, expires_at, payload_hash}` without making any
  Telegram MTProto network call.
- WHEN `prepare_send_message` is called and the per-peer rate limit (20 sends per
  hour, `audit.PeerSendCap` / `audit.PeerWindow`) is already exhausted for the
  calling identity and peer, THE SYSTEM SHALL return a `tool_error` result and
  SHALL NOT issue a confirmation token.
- WHEN `prepare_send_message` is called with `peer` or `text` empty, THE SYSTEM
  SHALL return a `tool_error` result stating both fields are required.
- WHEN `send_message` is called with a `confirmation_id` issued by
  `prepare_send_message` and the (peer, text) pair matches the prepared values,
  THE SYSTEM SHALL consume the token (single-shot), skip the direct rate-limit
  check, and proceed to real send if all runtime gates pass.
- WHEN a `confirmation_id` passed to `send_message` has expired (older than 5
  minutes) or was already consumed, THE SYSTEM SHALL fall back to dry-run and
  include `"dry_reason"` text that explicitly names `prepare_send_message` as the
  tool to call to obtain a fresh token.
- WHILE a `confirmation_id` has been consumed once (on success or on hash
  mismatch), THE SYSTEM SHALL reject all subsequent uses of the same ID.
- WHEN `prepare_send_message` is registered on the MCP server, THE SYSTEM SHALL
  expose it with `readOnlyHintAnnotation=true` and no destructive annotation so
  that connectors that distinguish read-only from destructive tools can allow the
  prepare step through independently.
- WHEN `prepare_send_message` completes (success or rate-limited), THE SYSTEM
  SHALL write an audit log entry under event name `prepare_send_message` or
  `prepare_send_message:rate_limited`, matching the pattern used by
  `prepare_pin_message`.
- IF the caller provides a `confirmation_id` to `send_message` that belongs to a
  different identity, THEN THE SYSTEM SHALL fall back to dry-run with a reason
  indicating the token belongs to another identity (existing
  `ErrConfirmationWrongUser` path, message unchanged).
- WHEN `send_message` is called without a `confirmation_id`, THE SYSTEM SHALL
  continue to apply the direct per-peer rate limit and attempt real send if gates
  pass (existing behavior preserved, no regression).

## Out of scope

- Changing how OpenAI's connector implements its safety filter — this is external
  and cannot be modified by this proposal.
- Forcing `send_message` to require `confirmation_id` (making it non-optional) —
  the direct unconfirmed path is preserved for connectors that do not use the
  two-step flow.
- Fixing read blocking caused by Cyrillic or other non-ASCII text in
  `get_unread_messages` / `get_messages` tool inputs or channel titles — the
  blocking occurs at the connector layer on tool inputs before the server
  responds; no server-side change can address it without removing the
  `<telegram-content untrusted="true">` safety wrapper, which is out of scope
  here.
- Changes to the Local Bridge (`bridgeCall`) path — `prepare_send_message` makes
  no Telegram network calls and therefore does not need a bridge dispatch route.
- Changes to `prepare_pin_message` or `pin_message` — those tools function
  correctly.
- Background sweeping of expired confirmations — the existing `Sweep()` method on
  `ConfirmStore` exists but is not wired to a goroutine; that is a pre-existing
  gap and not introduced by this change.

## Open questions

- Should `prepare_send_message` consume a rate-limit slot at prepare time, or
  defer it to the actual `send_message` call? Current proposal: consume at prepare
  time (matching `prepare_pin_message`). If a user calls prepare but never calls
  send, the slot is used. This is conservative and safe; revisit if UX complaints
  arise.
- The read-blocking issue affects `get_unread_messages` and `get_messages`. Is
  the block triggered by Cyrillic text in the tool INPUT (peer argument / channel
  title in dialog scan) or in the RESPONSE content? If input-based, no server
  change helps. If response-based, adjusting the `<telegram-content>` wrapper
  tags or encoding scheme could be considered in a follow-up issue.
- Issue #158 is referenced as the same non-deterministic gate. Does #158 already
  propose a mechanism for clients to distinguish connector-gated errors from true
  server errors at the protocol level? If yes, the dry-reason improvements in this
  proposal may partially overlap; they are still worth applying as they are
  server-side and independent of any #158 protocol change.
