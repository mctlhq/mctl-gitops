# Design: issue-402-feat-send-media-support-local-file-path

## Current state

`send_media` is wired in `internal/mcp/media_tools.go` (`toolSendMedia`,
lines ~278-417). Today it:

1. Declares `file_url` and `file_base64` as MCP tool string inputs
   (`mcplib.WithString(...)`), both optional at the schema level but
   enforced as mutually-exclusive-and-required in the handler:
   `if (fileURL == "") == (fileB64 == "") { ...error... }` (line 358).
2. Validates `media_type`, and requires `file_name` when
   `media_type=="document"` and the source is `file_base64` (line 361-363).
3. Evaluates the send gate (`evaluateSendGate`) — a denied call returns a
   dry-run preview via `telegram.SendMedia(ctx, nil, ..., false, dryReason,
   nil, 0)` (line 380) *without* resolving any byte source. This is the
   "draft-by-default" contract: only a gate-approved call may perform I/O.
4. Branches on account mode. If `s.Hub != nil` and
   `s.Store.GetAccountMode(ctx, id.UserID) == "local"` (line 385-386), the
   *hosted* server does not touch the file at all — it injects `args["mode"]
   = "send"` and forwards the original tool arguments verbatim over the
   bridge websocket to the Local Bridge daemon via `s.bridgeCall` (line
   389-392). The daemon does the actual byte resolution and Telegram RPC
   call, on the user's own machine.
5. Otherwise (hosted mode, no bridge), the hosted server itself resolves
   bytes via `s.resolveSendMediaBytes` (line 398, defined 423-441): decodes
   `file_base64` or calls `telegram.FetchGuardedURL` for `file_url`, both
   capped by `s.MediaUploadMaxBytes` (from `MEDIA_UPLOAD_MAX_BYTES`,
   `internal/config/config.go:135,285`, default 20 MiB). It then calls
   `telegram.SendMedia` with a real `*gotdtelegram.Client` borrowed from the
   pool.

On the daemon side, `cmd/local/daemon.go`'s dispatch `switch` has a
`case "send_media":` arm (lines 492-546) that unmarshals the same JSON args
map the hosted server forwarded, decodes `FileBase64` or calls
`tg.FetchGuardedURL` for `FileURL` (both capped at the hardcoded
`tg.DefaultMediaUploadMaxBytes` = 20 MiB, `internal/telegram/send_media.go:18`
— note this is *not* read from `MEDIA_UPLOAD_MAX_BYTES`, the daemon has no
env-based config for this), then calls the same shared
`tg.SendMedia(ctx, c, args.Peer, args.MediaType, data, args.FileName,
mimeType, args.Caption, realSend, dryReason, nil, 0)` (internal/telegram,
package-shared with the hosted server) using its own pooled client.

`tg.SendMedia` (`internal/telegram/send_media.go:56-128`) is the single
shared function both hosted and daemon call into: it uploads `data` via
`uploader.NewUploader`, builds the right `tg.InputMediaClass` via
`buildInputMedia`, and sends `MessagesSendMediaRequest`. It is agnostic to
where `data` came from.

The SSRF guard (`telegram.FetchGuardedURL`,
`internal/telegram/fetchmedia.go`) is HTTPS-only and refuses loopback/
link-local/private-range addresses at both DNS-resolution and dial time —
this is explicitly why `file://` and `http://localhost` are rejected today,
and this proposal does not touch that guard at all.

`README.md` line 33 documents the current `send_media` input contract in
the platform's operations-reference table.

## Proposed solution

Add `file_path` as a third mutually-exclusive media-source input, resolved
**only** by whichever process has legitimate access to the named file:

1. **`internal/mcp/media_tools.go` — `toolSendMedia`**
   - Add `mcplib.WithString("file_path", ...)` to the tool schema, documented
     as "Local filesystem path (absolute or relative to the Local Bridge
     daemon's working directory). Local Bridge accounts only — rejected for
     hosted accounts. Exactly one of file_url/file_base64/file_path is
     required."
   - Extend the exclusivity check from a 2-way XOR to a "exactly one of
     three" check (count non-empty among `fileURL`, `fileB64`, `filePath`;
     require count == 1).
   - Change the document+file_name rule: `file_name` is required when
     `media_type=="document"` and the source is `file_base64` *or* the
     source is `file_url` with no derivable name — this part is unchanged.
     For `file_path`, `file_name` is never required because it is always
     derivable via `filepath.Base(filePath)`; when the caller left
     `file_name` empty and the source is `file_path`, default it to
     `filepath.Base(filePath)` right after arg parsing, before the document
     check runs, so the existing document-name check simply passes.
   - Before the draft/gate branch (still no I/O yet, preserving
     draft-by-default): if `filePath != ""`, resolve account mode with the
     same `s.Store.GetAccountMode` lookup the code already does further
     down, but *early* — if the account is not in Local Bridge mode (no
     `s.Hub`, or mode != "local"), return a validation error immediately:
     `"file_path is only supported for Local Bridge accounts — use
     file_base64 or file_url, or connect Local Bridge"`. This mirrors the
     existing gate/scope checks that fail fast before any I/O, and prevents
     the hosted server from ever being asked to open a path on its own
     filesystem.
   - The existing bridge branch (`if s.Hub != nil && accountMode ==
     "local"`) already forwards `args` (the raw map, now including
     `file_path`) verbatim to `s.bridgeCall(ctx, id, "send_media", args)` —
     no change needed there beyond what the exclusivity/derivation logic
     above already did to `args`' effective `file_name`. Concretely: write
     the derived `file_name` back into `args["file_name"]` before the
     bridge call so the daemon does not have to re-derive it (keeps
     basename-derivation logic in one place).
   - The non-bridge hosted branch (`s.resolveSendMediaBytes`) is never
     reached with `filePath != ""` because of the early rejection above —
     no changes needed inside `resolveSendMediaBytes` itself. This keeps the
     hosted server's byte-resolution code exactly as security-reviewed
     today (base64 decode / guarded HTTPS fetch only).

2. **`cmd/local/daemon.go` — `case "send_media":`**
   - Add `FilePath string \`json:"file_path"\`` to the args struct.
   - In the `realSend` branch, add a third case:
     `case args.FilePath != "":` — read the file with `os.ReadFile` (or
     `os.Open` + `io.LimitReader(f, tg.DefaultMediaUploadMaxBytes+1)` to
     avoid holding an oversized file fully in memory before the cap check;
     the existing `file_base64`/`file_url` paths already fully buffer, so
     `os.ReadFile` followed by a length check is consistent with today's
     pattern and simplest to review) then enforce the same
     `tg.DefaultMediaUploadMaxBytes` cap with the same error-message shape
     used for `file_base64` today (`"send_media: file_path decodes to %d
     bytes, exceeding the %d-byte upload cap"` — adjusted wording since
     there is no decode step, e.g. "file_path is %d bytes, exceeding...").
   - On a read failure (`os.IsNotExist`, permission error, or "is a
     directory"), return `bridge.EncodeError(env.ID, fmt.Sprintf("send_media:
     file_path: %v", err))` — same shape as the other two sources' error
     handling.
   - Detect MIME type the same way `file_base64` does today:
     `http.DetectContentType(data[:min(512, len(data))])`.
   - `args.FileName` arrives already populated (hosted server derived it
     before forwarding); the daemon does not need its own basename-fallback
     logic, but as defense in depth (a caller could talk to the daemon's
     websocket endpoint directly bypassing the hosted server in theory) add
     the same `filepath.Base` fallback in the daemon if `FileName == ""` and
     `FilePath != ""`.

3. **Shared code (`internal/telegram/send_media.go`)** — no changes.
   `tg.SendMedia` already takes `data []byte` and `fileName string`
   independent of source; `file_path` reuses this entirely.

4. **`README.md`** — update the `send_media` row to document `file_path` as
   a third source, Local Bridge-only, with the basename-derivation and
   hosted-rejection behavior noted.

## Alternatives

1. **Resolve `file_path` on the hosted server too, by convention (e.g. the
   path must live under a configured "agent workspace" directory mounted
   into the hosted server's container).** Rejected: this proposal's whole
   premise is that the hosted server is a different machine from the one
   the AI agent is running on; there is no directory that is simultaneously
   "the agent's local disk" and "the hosted container's disk" without an
   explicit file-upload step first (which is exactly the `file_base64`/
   `file_url` cost this issue is trying to avoid). It also reintroduces a
   server-side arbitrary-path-read surface that the SSRF guard was written
   specifically to keep the server from having for network addresses; doing
   the filesystem equivalent would be an unforced regression.
2. **Add a dedicated `upload_file` MCP tool (two-step: stage bytes via a
   local-only tool, then reference a handle from `send_media`) instead of a
   third `send_media` input.** Rejected as over-engineered for the issue's
   scope: it adds a new confirmation/handle lifecycle (mirroring
   `prepare_get_media`/`get_media`'s confirmation store) for what is a
   same-process, same-call daemon-side file read with no cross-request
   state needed. A single additional mutually-exclusive input matches how
   `file_url`/`file_base64` already work and needs no new storage.
3. **Let `file_path` work for hosted-mode accounts too, but only via
   `os.Open` restricted to an explicit allowlist directory configured by
   `MEDIA_UPLOAD_MAX_BYTES`-style env var (e.g. `MEDIA_LOCAL_PATH_ROOT`).**
   Rejected: adds meaningful new configuration surface and a new class of
   path-traversal review burden for a scenario (giving the *hosted*
   multi-tenant server filesystem access shared with agent processes) the
   issue never asked for — the issue is specifically about the Local Bridge/
   daemon case ("For local bridge / daemon mode, read the file directly from
   disk").

## Platform impact
- **Migrations**: none — no schema or storage changes.
- **Backward compatibility**: fully additive. Existing calls using
  `file_url`/`file_base64` are unaffected; the exclusivity check only
  changes from "exactly one of two" to "exactly one of three," which is a
  superset. `README.md`'s tool inventory table is updated but the MCP tool
  name/output shape (`telegram.SendMediaResult`) does not change.
- **Resource impact**: negligible. The daemon already buffers file bytes up
  to 20 MiB for `file_base64`/`file_url` today; a local `os.ReadFile` is
  equivalent or cheaper (no base64 decode, no network round trip). No new
  goroutines, background workers, or persistent state.
- **Risks + mitigations**:
  - *Risk*: hosted server accidentally reads its own filesystem if the
    early-rejection check is missed on some code path (e.g. a future
    refactor that reorders the mode check after `resolveSendMediaBytes`).
    *Mitigation*: keep the hosted-mode rejection as the very first thing
    checked for `filePath != ""`, before the gate/draft branch even runs,
    and add a unit test (`internal/mcp/send_media_test.go`) asserting
    `file_path` on a non-bridge server returns an error with zero
    filesystem interaction (e.g. point `file_path` at a real file the test
    process can read, assert it is never sent/read).
  - *Risk*: daemon-side path read escaping intended scope (e.g. reading
    `~/.ssh/id_rsa` because an LLM was tricked into passing that path).
    *Mitigation*: this is the same trust boundary the daemon already
    operates inside — the daemon runs as the user's own OS user, driven by
    tool calls the user's own agent session issues, exactly like a shell
    tool the agent already has. No proposal changes an agent's ability to
    read arbitrary files it already has OS permission to read; this is
    called out in requirements.md's Open Questions rather than mitigated
    with a new allowlist, since adding one would silently break the
    issue's own primary use case (arbitrary generated-file paths under a
    user's Downloads/tmp/workspace directories).
  - *Risk*: inconsistent upload cap between hosted (`MEDIA_UPLOAD_MAX_BYTES`
    env var) and local daemon (hardcoded `tg.DefaultMediaUploadMaxBytes`).
    *Mitigation*: pre-existing gap, not introduced by this change (documented
    in requirements.md Open Questions); `file_path` simply reuses whatever
    cap `file_base64`/`file_url` already use in the daemon today, so it does
    not add a *new* inconsistency.
