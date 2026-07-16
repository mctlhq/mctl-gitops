# Design: issue-287-add-send-media-mcp-tool-for-photo-video

## Current state

Read paths I grounded this design in:

- **Tool registration.** `internal/mcp/server.go`'s `Server.HTTPHandler()`
  builds an `mcpserver.MCPServer` and registers each tool via
  `{t, h := s.toolXxx(); s.addTool(srv, t, h)}` (lines 133-150+). `addTool`
  applies the `ToolFilter` (`"all"` vs `"read-only"`) before calling
  `srv.AddTool`. New tools are added the same mechanical way.
- **`send_message`** (`internal/mcp/tools.go:281-367`, `toolSendMessage`):
  - Requires `peer`, `text`.
  - Computes the send gate via `evaluateSendGate(ctx, s.Store, id,
    s.AllowSend, s.DemoReviewerTGID)` — checks (in order) the demo/reviewer
    identity override, `ALLOW_SEND`, the `telegram:messages:send` scope, and
    per-account `send_enabled` (`db.Store.IsSendEnabled`).
  - If the gate denies, returns a dry-run preview via
    `telegram.SendMessage(ctx, nil, peer, text, false, dryReason, nil, 0)` —
    note `c` (the client) is `nil` in this branch; `SendMessage` short-circuits
    before touching `c` whenever `realSend` is `false`.
  - If the gate allows and the account is Local Bridge ("local") mode
    (`s.Store.GetAccountMode`), forwards to `s.bridgeCall(ctx, id,
    "send_message", args)` with `args["mode"] = "send"` injected.
  - Otherwise borrows a live client via `s.borrowWithRetry` (flood-wait aware
    retry wrapper) and calls `telegram.SendMessage(ctx, c, peer, text, true,
    "", s.PeerCache, id.UserID)`.
  - Audits every branch via `s.audit(ctx, id, "send_message:<phase>",
    telegram.RedactPeer(peer), err, startedAt)`.
  - Applies the per-peer rate limiter via `evaluateDirectSendLimiter` only on
    the real-send path, before borrowing a client.
  - `internal/telegram/send.go`'s `SendMessage` does the actual
    `MessagesSendMessage` RPC call, with one automatic peer-cache-evict-and-
    retry on `PEER_ID_INVALID`, and extracts the resulting message ID from the
    returned `tg.UpdatesClass` via `extractMessageID`.
- **`get_media` / `prepare_get_media`** (`internal/mcp/media_tools.go`): the
  existing binary-I/O precedent. `prepare_get_media` resolves a message's
  media location (`telegram.PrepareMediaRef`) and mints a single-shot
  `confirmation_id` via `s.Confirms.Issue` + `s.MediaStore.Set`; `get_media`
  claims that confirmation (`s.Confirms.Claim`), downloads through
  `telegram.DownloadMedia` (which wraps `gotd/td`'s
  `telegram/downloader.Downloader`, enforcing `s.MediaDownloadMaxBytes`), and
  returns base64 bytes. Both check size against `s.MediaDownloadMaxBytes`
  (`internal/config/config.go`, env `MEDIA_DOWNLOAD_MAX_BYTES`, default
  20 MiB / `telegram.DefaultMediaDownloadMaxBytes`) before/while downloading.
- **Media type classification.** `internal/telegram/messages.go:DecodeMediaInfo`
  classifies documents into `photo` / `video` / `animation` / `document` /
  `sticker` / `audio` / `voice` based on `tg.Document.Attributes`
  (`DocumentAttributeVideo`, `DocumentAttributeAnimated`, etc.) — `animation`
  is already a first-class, distinct type from `video` on the read path, so
  the send path's requirement to keep them distinct has a direct mirror to
  follow.
- **Error translation.** `internal/mcp/errorcatalog.go`'s `mtprotoErrResult`
  maps known `tgerr.Error` codes (`PEER_ID_INVALID`, `CHAT_WRITE_FORBIDDEN`,
  flood-wait, etc.) to friendly messages; `borrowErrResult`
  (`internal/mcp/tools.go`) chains `sessionErrText` →
  `telegram.ErrPoolFull` → `mtprotoErrResult` → generic `toolErr` fallback.
  Every write tool funnels errors through this same chain.
- **Local Bridge daemon parity.** `cmd/local/daemon.go`'s `dispatchCall`
  switches on `env.Tool` with a fixed set of cases: `list_dialogs`,
  `get_unread_messages`, `get_messages`, `send_message`, `prepare_get_media`,
  `get_media`, `pin_message`. Any tool not in this switch simply isn't
  reachable for a local-mode account — the daemon has no generic fallback.
- **Config.** `internal/config/config.go` defines `MediaDownloadMaxBytes`
  (`MEDIA_DOWNLOAD_MAX_BYTES`, default 20971520) and wires it to
  `mcp.Server.MediaDownloadMaxBytes` (see `cmd/server/main.go` construction,
  not fully re-read here but the field is consumed directly by
  `toolGetMedia`).
- **No existing SSRF-guarded HTTP fetcher.** `internal/netctx` tracks the
  *inbound* TCP peer address for rate-limiting/CIDR checks, unrelated to
  outbound fetches. `internal/fileutil/pathguard.go` guards local filesystem
  paths (traversal/symlink escape), not URLs. There is currently no code path
  in this server that makes an outbound HTTP request to a caller-supplied URL
  — `send_media`'s `file_url` option would be the first.
- **Module version.** `go.mod` pins `github.com/gotd/td v0.144.0`. This
  environment has no network access, so I could not fetch the module source
  to confirm exact upload-side type/function names (see Open Questions in
  `requirements.md`); the design below names the conventionally-expected
  `gotd/td` symbols (mirroring the already-used `telegram/downloader`
  package with an inferred `telegram/uploader` counterpart, and
  `tg.MessagesSendMediaRequest` / `tg.InputMediaUploaded*`), flagged as
  verify-before-use for the Tier 2 implementer.

## Proposed solution

### 1. New tool: `toolSendMedia` in `internal/mcp/media_tools.go`

Co-locate with `toolGetMedia`/`toolPrepareGetMedia` since this file already
owns Telegram binary I/O concerns. Structure mirrors `toolSendMessage`
almost exactly, swapping the payload:

```
mcplib.NewTool("send_media",
  WithReadOnlyHintAnnotation(false), WithDestructiveHintAnnotation(true),
  WithOpenWorldHintAnnotation(true), WithOutputSchema[sendMediaResult](),
  WithDescription(...),  // documents media_type enum, file_url vs
                          // file_base64, draft-by-default, size cap
  WithString("peer", Required()),
  WithString("media_type", Required()),  // "photo"|"video"|"document"|"animation"
  WithString("file_url"),
  WithString("file_base64"),
  WithString("caption"),
  WithString("file_name"),
)
```

Handler flow (parallels `toolSendMessage`, `internal/mcp/tools.go:313-366`):

1. `requireScope(id, "telegram:messages:send")` — checked eagerly, same as
   every scoped tool, ahead of any gate/network work. (`send_message` itself
   does not call `requireScope` directly, relying on `evaluateSendGate`'s
   scope check instead — but that check only fires deep inside the gate
   evaluation. For `send_media`, validate the scope explicitly and early so a
   caller without the scope never triggers a `file_url` fetch. This is a
   small, deliberate deviation from the `send_message` pattern for defense in
   depth, since `send_media` has an extra externally-triggerable I/O step
   `send_message` doesn't.)
2. Validate `peer`, `media_type` (enum check), and exactly-one-of
   `file_url`/`file_base64` up front — no I/O yet. For `document` +
   `file_base64`, require `file_name`.
3. Evaluate the send gate exactly as `send_message` does:
   `evaluateSendGate(ctx, s.Store, id, s.AllowSend, s.DemoReviewerTGID)`,
   then `evaluateDirectSendLimiter` when the gate is open. No new gate logic
   — reuse the existing helpers verbatim so the two tools cannot drift.
4. **If the gate denies:** return a dry-run preview immediately, without
   resolving `file_url` or decoding `file_base64` — the whole point of
   draft-by-default is that a denied call performs no meaningful I/O. This is
   a deliberate strengthening over blindly mirroring `send_message` (which has
   no bytes to fetch in the first place): resolve the media source in the
   *same conditional branch* as the real send, not before.
5. **If the gate allows and the account is local-mode:** forward through
   `s.bridgeCall(ctx, id, "send_media", args)` with `args["mode"] = "send"`
   injected, matching `send_message`'s bridge branch. Requires a matching
   `case "send_media"` in `cmd/local/daemon.go` (see below) — otherwise the
   daemon returns an "unrecognized tool" error and the feature silently
   doesn't work for local-mode accounts.
6. **If the gate allows and the account is hosted-mode:** resolve the byte
   source:
   - `file_base64`: `base64.StdEncoding.DecodeString`, reject decode errors,
     reject decoded length above `s.MediaUploadMaxBytes` before any Telegram
     call.
   - `file_url`: fetch via a new guarded helper (see below), capped at
     `s.MediaUploadMaxBytes`, with a bounded timeout (mirrors the 60s cap
     `toolGetMedia` uses for downloads).
   Then borrow a client via `s.borrowWithRetry` and call a new
   `telegram.SendMedia(ctx, c, peer, mediaType, bytes, fileName, mimeType,
   caption, s.PeerCache, id.UserID)` (mirrors `telegram.SendMessage`'s
   signature style).
7. Audit via `s.audit(ctx, id, "send_media:<phase>",
   telegram.RedactPeer(peer), err, startedAt)`, same pattern as every other
   write tool. Errors funnel through `borrowErrResult`.
8. Return `jsonResult(sendMediaResult{...})` — new result struct alongside
   the other result types at the bottom of `internal/mcp/tools.go` (or
   colocated in `media_tools.go` next to `getMediaResult`), containing
   `sent`, `mode`, `peer`, `message_id`, `media_type`, `mime_type,omitempty`,
   `file_name,omitempty`, `caption,omitempty`, `dry_reason,omitempty`,
   `notice,omitempty` — a superset compatible with `send_message`'s shape
   plus the media-specific fields the issue asks for.

### 2. New `telegram.SendMedia` in `internal/telegram/send.go` (or a new
   `send_media.go` in the same package, to keep `send.go` focused on text)

Mirrors `SendMessage`'s dry-run/real-send split:

- `realSend == false`: return a `SendMediaResult`-shaped dry-run preview
  (no Telegram call), same as `SendMessage`'s early return.
- `realSend == true`:
  1. `ResolvePeerCached` — reuse verbatim, same peer resolution/eviction/
     retry-on-`PEER_ID_INVALID` logic `SendMessage` already has (worth
     factoring the peer-resolve-and-retry-on-PEER_ID_INVALID block into a
     small shared helper both `SendMessage` and `SendMedia` call, to avoid
     the exact duplicated retry dance living in two places).
  2. Upload the bytes via `gotd/td`'s upload mechanism (byte-slice source,
     since bytes are already fully in memory after the base64-decode/HTTP-
     fetch step) to obtain an `tg.InputFileClass` handle.
  3. Build the appropriate `tg.InputMediaClass`:
     - `photo` → `tg.InputMediaUploadedPhoto{File: uploaded}`
     - `document` → `tg.InputMediaUploadedDocument{File: uploaded, MimeType:
       ..., Attributes: [DocumentAttributeFilename{FileName: fileName}]}`
     - `video` → `InputMediaUploadedDocument` with `Attributes` including
       `DocumentAttributeVideo{Duration, W, H, SupportsStreaming: true}` (best
       effort — duration/dimensions may be zero/unknown for agent-generated
       files; Telegram accepts zero values, it just won't show a scrubber
       thumbnail as richly)
     - `animation` → `InputMediaUploadedDocument` with `Attributes` including
       `DocumentAttributeAnimated{}` (and typically also a
       `DocumentAttributeVideo` for gif-as-mp4 playback) — this is the
       concrete mechanism that keeps `animation` distinct from `video`,
       matching how `DecodeMediaInfo` already reads that attribute back on
       the receive side.
  4. Call `tg.MessagesSendMediaRequest{Peer, Media, Message: caption,
     RandomID}` (caption maps to Telegram's `message` field on the media
     send request — same field text messages use, just attached to media).
  5. Extract the message ID via the same `extractMessageID` helper
     `SendMessage` already has (already exported at package level in
     `send.go`, no change needed).

### 3. Guarded URL fetcher for `file_url`

New helper, e.g. `internal/telegram/fetchmedia.go` or a small
`internal/httpfetch` package (either is defensible; a dedicated package is
slightly cleaner since it has no other `telegram`-specific dependencies and
could plausibly be reused elsewhere):

- Parse the URL, require `https://` (reject `http://`, `file://`, etc.).
- Resolve the host, reject if any resolved IP is loopback, link-local,
  private-use (RFC 1918 / ULA), or a handful of known cloud-metadata
  addresses (169.254.169.254 is already covered by link-local, but call it
  out explicitly in a comment given its history as an SSRF target).
- Use a custom `http.Client` with a bounded `Timeout` and a `Transport` whose
  `DialContext` re-validates the resolved IP at connection time (defends
  against DNS-rebinding between the initial check and the actual dial) —
  this is the same class of problem `internal/netctx` was built to avoid on
  the *inbound* side (spoofed proxy headers); here it's the outbound analogue.
- Enforce a byte cap while streaming the response body (`io.LimitReader` over
  `resp.Body`, sized to `MediaUploadMaxBytes + 1` so an over-cap response can
  still be detected and rejected with a clear message instead of silently
  truncated).
- On any violation, return an error the handler surfaces as a clear
  validation/error result — never a raw timeout or 500.

### 4. Config: `MEDIA_UPLOAD_MAX_BYTES`

Add to `internal/config/config.go` next to `MediaDownloadMaxBytes`:

```go
// MediaUploadMaxBytes caps send_media uploads (file_url fetch and
// file_base64 decode). 0 means no cap. Default 20 MiB. Set via
// MEDIA_UPLOAD_MAX_BYTES.
MediaUploadMaxBytes int64 // MEDIA_UPLOAD_MAX_BYTES
...
c.MediaUploadMaxBytes = int64(envInt("MEDIA_UPLOAD_MAX_BYTES", 20971520))
```

Wire it to a new `Server.MediaUploadMaxBytes` field
(`internal/mcp/server.go`), set at construction in `cmd/server/main.go`
alongside the existing `MediaDownloadMaxBytes` wiring.

### 5. Local Bridge daemon parity: `cmd/local/daemon.go`

Add a `case "send_media":` to `dispatchCall`, structurally identical to the
existing `case "send_message":` block — decode a small args struct
(`Peer, MediaType, FileURL, FileBase64, Caption, FileName, Mode, DryReason`),
call the same `tg.SendMedia` used by the hosted path (package alias `tg` here
is actually the `internal/telegram` import per existing daemon.go convention,
not `gotd/td`'s `tg`), marshal the result. The daemon runs the caller's own
Telegram client locally, so this also means the `file_url` fetch — if
performed by the daemon rather than the hosted server for local accounts —
happens from the *user's own machine*, which sidesteps most of the SSRF
concern for that mode (the guarded fetcher should still be applied for
defense in depth, but the blast radius differs materially between hosted and
local).

### 6. Tool registration and docs

- Register in `internal/mcp/server.go`'s `HTTPHandler()`:
  `{t, h := s.toolSendMedia(); s.addTool(srv, t, h)}`, placed near
  `toolSendMessage`/`toolGetMedia` for readability.
- Add a row to the `## MCP tools` table in `README.md`, matching the existing
  style (annotations + one-line description), and update the tool count
  mentioned in the README status line if the doc numbers tools explicitly.
- Update `internal/mcp/tools_test.go` / add `media_tools_test.go` coverage
  (see `tasks.md`).

## Alternatives

1. **Reuse `MEDIA_DOWNLOAD_MAX_BYTES` directly as the upload cap** (as the
   issue's first-listed option suggests), instead of introducing
   `MEDIA_UPLOAD_MAX_BYTES`. Dropped because download and upload are
   different trust boundaries with different natural limits (an operator may
   want a generous read cap for archival channels but a tight write cap to
   limit outbound bandwidth/cost, or vice versa); collapsing them removes
   that knob for a marginal config-surface savings. A single new env var with
   the same default value keeps today's behavior unchanged by default while
   leaving the door open.

2. **Have Telegram fetch `file_url` "server-side" as the issue's prose
   literally suggests**, treating this as equivalent to Bot API's `sendPhoto`
   with a URL. Dropped because this server speaks MTProto via `gotd/td`'s
   user-account client, which has no such RPC — only the Bot API (a
   different, non-MTProct HTTP API this server does not use) supports
   passing a bare URL for Telegram's own infrastructure to fetch. Building
   this correctly requires the guarded fetch-then-upload path described
   above; there is no shortcut.

3. **Skip `file_url` entirely for v1, ship `file_base64` only.** Considered
   given the SSRF surface is the riskiest part of this proposal, and the
   issue's own context section emphasizes the base64/agent-generated-file use
   case as the primary motivator ("a gif built in a Claude Code / Cowork
   sandbox that has no public URL"). Not adopted as the final design because
   the issue's acceptance criteria explicitly lists `file_url` as a required
   input option, not a stretch goal — but this is flagged prominently in
   `requirements.md`'s Open Questions and `tasks.md`'s task breakdown as the
   piece most worth an explicit go/no-go decision (or a follow-up flag-gated
   rollout, e.g. `ALLOW_SEND_MEDIA_FROM_URL`) before merging, versus shipping
   `file_base64` alone first and following up with `file_url` once the
   guarded fetcher has had independent security review.

4. **Add a `prepare_send_media`/confirm two-step**, mirroring
   `prepare_pin_message`/`pin_message`. Dropped for consistency:
   `send_message` — the closest sibling tool — has no prepare/confirm step;
   its safety comes entirely from the `evaluateSendGate` draft-by-default
   design. Introducing a confirmation step only for media would be an
   inconsistent UX (why does sending a gif need two calls but sending text
   doesn't?) without a clear extra safety benefit, since the gate already
   blocks real sends by default.

## Platform impact

- **Migrations:** none. No new DB tables; `MediaStore`/`ConfirmStore` are
  in-memory and unused by this tool (see Alternative 4 above for why no
  confirmation step is introduced).
- **Backward compatibility:** purely additive — new tool, new optional env
  var (`MEDIA_UPLOAD_MAX_BYTES`, defaults preserve today's absence of any
  upload path), new `Server` field with a safe zero value. No existing tool's
  schema or behavior changes. `send_message` is untouched.
- **Resource impact:**
  - Memory: each `send_media` call holds the full decoded/fetched payload in
    memory at once (bounded by `MediaUploadMaxBytes`, default 20 MiB) — same
    order of magnitude as `get_media`'s existing download path, so no new
    class of memory risk, just a new direction.
  - Outbound network: `file_url` introduces the server's first outbound
    fetch to caller-supplied hosts. Needs the guarded fetcher (Design §3) and
    should be observed via `s.Metrics` (a `send_media_url_fetch` counter/
    histogram alongside existing `ToolInvocationsTotal`/`ToolInvocationDuration`
    would give operators visibility into a genuinely new attack surface).
  - Upload bandwidth/Telegram API load: bounded by the same cap; flood-wait
    handling is already covered by reusing `s.borrowWithRetry`.
- **Risks + mitigations:**
  - *SSRF via `file_url`* — highest risk in this proposal. Mitigated by the
    guarded fetcher (deny private/loopback/link-local ranges, re-check on
    redirect and at dial time, HTTPS-only, bounded timeout). Recommend a
    dedicated security-focused review pass on this component specifically
    before merge (the repo's own `/security-review` workflow, or an
    equivalent manual pass) given it is new outbound-request surface in a
    server that otherwise makes no caller-directed outbound HTTP calls.
  - *Gate drift between `send_message` and `send_media`* — mitigated by
    calling the exact same `evaluateSendGate`/`evaluateDirectSendLimiter`
    helpers rather than reimplementing gate logic (the issue explicitly asks
    for this factoring; it already exists as shared code, so `send_media`
    just needs to call it, not extract it).
  - *Local Bridge silently missing `send_media`* — mitigated by adding the
    daemon dispatch case in the same change (see Alternatives/Tasks), not as
    a follow-up, since a silently-unreachable tool for local-mode accounts is
    a worse failure mode than a slightly larger PR.
  - *Oversized upload causing a raw timeout/500* (explicit acceptance
    criterion) — mitigated by validating size before any Telegram call
    whenever it's knowable up front (base64 length, HTTP `Content-Length`),
    and by the streaming cap catching the case where the declared size lied
    or was absent.
  - *Reused MTProto attribute logic drifting from the read-side classification
    in `DecodeMediaInfo`* — mitigated by using the same attribute types
    (`DocumentAttributeAnimated`, `DocumentAttributeVideo`) the read path
    already decodes, so a media message this tool sends is guaranteed to be
    classified consistently if later fetched back via `get_media`.
