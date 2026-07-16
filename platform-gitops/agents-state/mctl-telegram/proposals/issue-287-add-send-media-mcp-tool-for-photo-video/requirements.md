# Add send_media MCP tool for photo/video/document/animation attachments

## Context

`mctl-telegram` (`tg.mctl.ai`, currently v0.41.9) exposes a Telegram user account
over MCP. Today `send_message` (`internal/mcp/tools.go`) only accepts
`{peer, text}` — there is no tool that can attach a photo, video, document, or
gif to an outgoing message. This blocks workflows like "analyze a video sent to
the bot, then reply with an annotated screenshot or gif," which is exactly the
kind of round-trip the Claude/`tg-preview-mctl` connector is meant to support.

The read side of this already exists: `prepare_get_media` / `get_media`
(`internal/mcp/media_tools.go`) download message attachments through
`internal/telegram/media_download.go`, which wraps `gotd/td`'s
`telegram/downloader` package. Issue #287 asks for the send-side counterpart:
a `send_media` tool that uploads bytes (from an inline base64 payload or a
fetched URL) and attaches them to a new message, gated by the same
draft-by-default send controls that already protect `send_message`.

## User stories

- AS a Claude/ChatGPT agent acting on a connected Telegram account, I WANT to
  send a photo, video, document, or gif back to a chat SO THAT I can complete
  workflows that require returning generated or forwarded media, not just text.
- AS an operator running tg.mctl.ai, I WANT `send_media` to honor the exact
  same `ALLOW_SEND` / scope / per-account `send_enabled` gate as
  `send_message` SO THAT enabling media sending does not create a second,
  divergent path to bypass the draft-by-default safety posture.
- AS an operator, I WANT oversized or malformed media inputs rejected with a
  clear error SO THAT a bad agent call cannot hang a request, exhaust server
  memory, or silently fail with a raw timeout/500.
- AS a security reviewer, I WANT the `file_url` input path to be constrained
  (no fetching internal/private network addresses) SO THAT `send_media` cannot
  be used as a server-side request forgery (SSRF) primitive.

## Acceptance criteria (EARS)

- WHEN `send_media` is called with a required `peer`, `media_type`, and
  exactly one of `file_url` / `file_base64` THE SYSTEM SHALL validate the
  inputs before attempting any Telegram or network I/O.
- IF `media_type` is not one of `photo`, `video`, `document`, `animation` THEN
  THE SYSTEM SHALL return a validation error and make no Telegram call.
- IF both `file_url` and `file_base64` are supplied, or neither is supplied,
  THEN THE SYSTEM SHALL return a validation error identical in shape to the
  existing "X and Y are required" pattern used by `send_message`.
- IF `media_type` is `document` and the source is `file_base64` and `file_name`
  is empty THEN THE SYSTEM SHALL return a validation error (mirrors the
  issue's explicit requirement).
- WHEN the send gate evaluated by `evaluateSendGate` (in
  `internal/mcp/tools.go`) denies the call THE SYSTEM SHALL return a
  successful dry-run preview (`sent=false`, populated `dry_reason`, no
  Telegram API call), identical in semantics to `send_message`'s draft path.
- WHEN the send gate allows the call and the account is in Local Bridge
  ("local") mode THE SYSTEM SHALL route the call through the bridge daemon
  (`s.Hub`/`cmd/local/daemon.go`) the same way `send_message`,
  `prepare_get_media`, and `get_media` already do.
- WHEN the send gate allows the call and the account is in hosted mode
  THE SYSTEM SHALL upload the media bytes via the `gotd/td` client already
  held in `s.Pool` (the same pool `get_media` borrows from) and send it as a
  Telegram media message, returning a real `message_id`.
- WHILE the resolved (or decoded) media payload size is known THE SYSTEM SHALL
  reject the call before uploading if the size exceeds the configured upload
  cap (new `MEDIA_UPLOAD_MAX_BYTES`, mirroring `MEDIA_DOWNLOAD_MAX_BYTES`'s
  default of 20 MiB), returning a clear, non-timeout error naming the limit.
- WHILE streaming a `file_url` fetch or a `file_base64` decode THE SYSTEM
  SHALL enforce the same cap as a hard mid-stream abort if the declared size
  was absent or understated, so no unbounded read can occur.
- IF `file_url` resolves (directly or via redirect) to a loopback, link-local,
  or private-range address THEN THE SYSTEM SHALL refuse the fetch (SSRF
  guard) and return a clear error.
- IF `media_type` is `animation` THE SYSTEM SHALL send the file as a Telegram
  animation/gif (`DocumentAttributeAnimated`, matching how
  `internal/telegram/messages.go:DecodeMediaInfo` already classifies
  `animation` on the read path) and SHALL NOT relabel it as `video`.
- WHEN a real send succeeds THE SYSTEM SHALL return the same result shape as
  `send_message` (`sent`, `mode`, `peer`, `message_id`) plus `media_type`, and
  SHALL audit the call via `s.audit(...)` exactly as every other write tool
  does, with the peer redacted through `telegram.RedactPeer`.
- WHEN a real send fails with a recognized MTProto error THE SYSTEM SHALL
  surface it through the existing `mtprotoErrResult` / `sessionErrText` /
  `borrowErrResult` translation layer rather than a raw error string.
- IF the caller's identity fails `requireScope(id, "telegram:messages:send")`
  THEN THE SYSTEM SHALL refuse before any gate evaluation or I/O, matching the
  scope check pattern used by every other scoped tool.
- WHEN `send_media` is registered THE SYSTEM SHALL apply the per-peer send
  rate limiter (`evaluateDirectSendLimiter` / `audit.RateLimiter`) the same
  way `send_message` does, so media sends count against the same per-peer
  budget rather than opening a second unmetered channel.
- WHEN the MCP tool list is queried THE SYSTEM SHALL show `send_media` with a
  description that documents `media_type` values, the two source options, and
  the draft-by-default behavior (mirrors the acceptance criteria in the
  issue and the documentation style already used by `get_media` /
  `send_message`).

## Out of scope

- `edit_message_media` (replacing media on an already-sent message) — the
  issue explicitly calls this a "nice-to-have, separate issue if scope is too
  big." Not included here.
- Multi-file / album sends (`media_group`) — the issue only asks for a single
  attachment per call.
- Sticker sending — the tool's `media_type` enum does not include `sticker`,
  matching the issue's four listed types.
- Big-file (>upload cap) multi-connection upload tuning beyond what
  `gotd/td`'s uploader already provides — see Open Questions.
- Changes to the Local Bridge daemon's other tool dispatch entries beyond
  adding the new `send_media` case needed for local-mode parity.
- Changing `get_media`'s existing `MEDIA_DOWNLOAD_MAX_BYTES` default or
  semantics.

## Open questions

- **Upload size ceiling.** The issue asks to "mirror `get_media`'s
  `MEDIA_DOWNLOAD_MAX_BYTES` (default 20 MiB) as an upload cap too, or
  document if Telegram Bot API's own 50MB limit should be the ceiling
  instead." This server uses the MTProto **user-account** API (`gotd/td`
  `telegram.Client`), not the Bot API, so the Bot API's 50MB figure does not
  directly apply — MTProto user accounts can upload far larger files (up to
  Telegram's ~2 GiB / 4 GiB-with-Premium protocol limits). Resolution adopted
  here: introduce a new, independently configurable `MEDIA_UPLOAD_MAX_BYTES`
  (default 20 MiB, same default as the download cap for symmetry and to keep
  v1 conservative) rather than reusing `MEDIA_DOWNLOAD_MAX_BYTES` directly, so
  operators can raise the upload ceiling without also raising the unrelated
  download cap. Proceeding with this interpretation; flagged for operator
  review before rollout.
- **`file_url` fetch semantics.** The issue's phrasing ("Telegram fetches it
  server-side") describes Bot API behavior. MTProto has no server-side
  "fetch this URL" primitive for user-account sends — this mctl-telegram
  server itself must fetch `file_url` over HTTP and re-upload the bytes via
  MTProto. This is a new outbound-HTTP code path with no existing precedent
  in the codebase (no SSRF-guarded fetcher exists today; `internal/netctx` is
  unrelated — it tracks inbound socket peer addresses, and
  `internal/fileutil/pathguard.go` guards local filesystem paths, not URLs).
  Proceeding with: build a small guarded fetcher (deny loopback/link-local/
  private ranges on the initial resolution and on every redirect hop, enforce
  an HTTP timeout, and cap bytes read via a `io.LimitReader`-style guard tied
  to `MEDIA_UPLOAD_MAX_BYTES`). Flagged for security review — this is the
  single highest-risk piece of this proposal.
- **Exact `gotd/td` upload API.** `internal/telegram/media_download.go`
  reuses `gotd/td`'s `telegram/downloader` package. The send side almost
  certainly has a mirroring `telegram/uploader` package plus
  `tg.MessagesSendMediaRequest` / `tg.InputMediaUploadedPhoto` /
  `tg.InputMediaUploadedDocument` types, consistent with the vendored
  `github.com/gotd/td v0.144.0` in `go.mod`, but this investigation
  environment has no network access to fetch and read the module source to
  confirm exact field names/signatures. The Tier 2 implementer must verify
  the precise API against the vendored `gotd/td` source (or `go doc`) before
  writing code; treat all `gotd/td` symbol names in `design.md` as
  best-effort, verify-before-use.
- **Local Bridge parity timing.** Should `send_media` ship simultaneously
  with a `cmd/local/daemon.go` dispatch case, or can hosted-mode ship first
  with local-mode as an explicit fast-follow? The issue does not mention
  Local Bridge at all. Resolution adopted: ship both in the same change (see
  `tasks.md`) so the tool does not silently no-op ("local-bridge daemon...
  not connected" is a real answer; a missing `case "send_media"` would instead
  fall through to the daemon's unknown-tool error) for local-mode accounts,
  keeping parity with every other hosted/local dual-path tool.
- **Response field naming.** The issue says output should be "same shape as
  send_message... plus media_type." `send_message`'s `SendResult.Text` field
  has no obvious media analogue. Resolution adopted: keep `SendResult`-like
  fields (`sent`, `mode`, `peer`, `message_id`, `dry_reason`, `notice`) and add
  `media_type`, `mime_type` (echoed back), and `file_name` (when known/derived),
  omitting `text` unless `caption` was supplied (in which case echo it under
  a `caption` field, not `text`, to avoid conflating the two tools' schemas).
- **Caption length/formatting parity with `send_message`.** Not specified by
  the issue. Resolution adopted: apply the same truncation/validation `text`
  gets in `send_message` (see `truncate` helper in `internal/mcp/tools.go`) to
  `caption`, since Telegram's caption length limit is shorter than message
  text length limit in some media contexts — implementer must confirm exact
  MTProto caption limit and truncate defensively rather than trust Telegram's
  own error.
