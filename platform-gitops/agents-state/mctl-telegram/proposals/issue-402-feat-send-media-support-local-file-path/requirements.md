# feat(send_media): support local file path (file_path) for sending media

## Context
`send_media` (`internal/mcp/media_tools.go`) currently accepts exactly one of
`file_url` (an HTTPS URL the server fetches) or `file_base64` (inline
base64-encoded bytes). Neither works well for an AI coding agent (Claude
Code, Antigravity, etc.) that has just generated a file on the same machine
it is running on: `file_base64` blows up a 1-5 MB file into 1.3-6.7M
characters of output the model must literally emit (300k-1.5M tokens,
exceeding most per-turn output limits), and `file_url` categorically refuses
`file://` and loopback/private addresses via the SSRF guard in
`internal/telegram/fetchmedia.go` (`isDisallowedIP`), which is by design and
must not be weakened.

The fix is a third input, `file_path`, that is meaningful only when the tool
call is actually executed on the user's own machine — i.e. Local Bridge mode
(`cmd/local/daemon.go`, dispatched via `internal/bridge`), where a daemon
process already has direct filesystem access to whatever the agent just
wrote to disk. In hosted mode the MCP tool call is handled by a remote
server process (`internal/mcp/media_tools.go`'s `toolSendMedia inside
cmd/server`) that has no relationship to the caller's filesystem — resolving
`file_path` there would read the *server's own* disk, not the user's, which
is not the requested capability and is a path-disclosure risk. `file_path`
must therefore be rejected outright for hosted-mode accounts, with an error
that tells the caller to use `file_base64`/`file_url` or switch to Local
Bridge mode.

## User stories
- AS an AI coding agent running locally (e.g. via Claude Code, Antigravity)
  with the Local Bridge daemon connected, I WANT to pass a local filesystem
  path to `send_media` SO THAT I can send a generated audio file, document,
  report, or screenshot to Telegram without emitting its bytes as base64
  output tokens or standing up a temporary HTTPS host for it.
- AS a platform operator, I WANT `file_path` to be refused for hosted-mode
  accounts SO THAT the hosted server is never induced to read arbitrary
  paths off its own disk on behalf of a remote caller.
- AS a security reviewer, I WANT the existing `MEDIA_UPLOAD_MAX_BYTES` cap
  and `file_name`-required-for-document rule to apply identically to
  `file_path` SO THAT this input doesn't open a size or validation loophole
  the other two sources don't have.

## Acceptance criteria (EARS)
- WHEN `send_media` is called with `file_path` set and no `file_url`/
  `file_base64`, THE SYSTEM SHALL treat `file_path` as the third valid
  media-source input, mutually exclusive with the other two.
- IF more than one of `file_path`, `file_url`, `file_base64` is provided,
  THEN THE SYSTEM SHALL return a validation error before any I/O, mirroring
  the existing `(fileURL == "") == (fileB64 == "")` check in
  `toolSendMedia`.
- IF none of `file_path`, `file_url`, `file_base64` is provided, THEN THE
  SYSTEM SHALL return a validation error before any I/O.
- WHEN `file_name` is not supplied AND `file_path` is the source, THE SYSTEM
  SHALL derive `file_name` from `filepath.Base(file_path)`.
- WHEN `media_type="document"` AND `file_path` is the source AND `file_name`
  is not explicitly supplied, THE SYSTEM SHALL use the derived basename to
  satisfy the existing "file_name required for document" rule (i.e. this
  case is no longer an error, unlike `file_base64` without `file_name`).
- WHEN the account resolved from the caller's identity is in Local Bridge
  mode (`s.Store.GetAccountMode(...) == "local"`), THE SYSTEM SHALL let the
  Local Bridge daemon (`cmd/local/daemon.go`) resolve `file_path` by reading
  the file directly from the daemon's local filesystem.
- WHEN the account is in hosted mode (no bridge, or `GetAccountMode() !=
  "local"`) AND `file_path` is set, THE SYSTEM SHALL return a validation
  error (before any filesystem access) telling the caller `file_path` is
  only supported for Local Bridge accounts.
- WHEN the send gate denies the call (draft-by-default), THE SYSTEM SHALL
  NOT open, stat, or read `file_path` — mirroring the existing rule that a
  denied call performs no `file_url` fetch or `file_base64` decode.
- WHEN `file_path` is read in Local Bridge mode AND the resulting byte count
  exceeds the configured upload cap (`tg.DefaultMediaUploadMaxBytes` today;
  see design.md for the local-daemon cap question), THE SYSTEM SHALL reject
  the call with the same "exceeds the N-byte upload cap" error shape used
  by `file_base64`/`file_url` today, without partially uploading.
- IF `file_path` does not exist, is not a regular file, or is not readable
  by the daemon process, THEN THE SYSTEM SHALL return a clear error
  identifying `file_path` as the source of the failure, without leaking
  the daemon host's directory listing beyond the path the caller already
  supplied.
- WHILE resolving `file_path`, THE SYSTEM SHALL NOT log the file's contents,
  matching the existing rule that message bodies and file bytes are never
  logged (`internal/audit/redact.go`).
- WHEN `file_path` is used successfully, THE SYSTEM SHALL detect MIME type
  from the file's contents the same way `file_base64` does
  (`http.DetectContentType` on the first 512 bytes), since local files carry
  no `Content-Type` header the way `file_url` responses do.

## Out of scope
- Resolving `file_path` from the hosted server's own filesystem (rejected by
  design — see acceptance criteria and design.md).
- Directory or glob inputs (`file_path` must name exactly one regular file).
- Streaming very large files below/above the existing upload cap in chunks;
  this proposal reuses the existing whole-buffer read-then-upload pattern
  `SendMedia` already uses for `file_base64`/`file_url`.
- Changing `MEDIA_UPLOAD_MAX_BYTES` semantics or default value.
- Adding a `file_path` variant to `get_media`/`prepare_get_media` (download
  side) — this proposal is send-only, per the issue.

## Open questions
- The Local Bridge daemon currently hardcodes `tg.DefaultMediaUploadMaxBytes`
  (20 MiB) for both `file_base64` and `file_url` in `cmd/local/daemon.go`,
  rather than reading a `MEDIA_UPLOAD_MAX_BYTES` env var the way the hosted
  server's `internal/config.Load()` does. This proposal reuses that same
  hardcoded constant for `file_path` for consistency with the daemon's
  existing behavior, rather than introducing new local-daemon configuration
  in this change. If the operator wants the local daemon's cap to be
  configurable, that is a separate, pre-existing gap not introduced here.
- The issue does not say whether `file_path` should be validated against an
  allowlist of directories (e.g. only the OS temp dir or the user's home
  directory) versus permitting any path readable by the daemon process.
  Given the daemon already runs as the user's own OS user with the user's
  own filesystem permissions (no privilege boundary crosses here, unlike the
  file_url SSRF case where the *server* would otherwise reach into the
  *user's* private network), this proposal does not add a path allowlist:
  the daemon reading any file its own OS user can already read is not a
  privilege escalation. Symlinks are resolved and followed like any normal
  file read (`os.Open`); no special symlink handling is added.
- The issue says "absolute or relative local filesystem path." Relative to
  what, when resolved inside the daemon process, is left to the OS process
  working directory of `cmd/local` at the time it was started (typically the
  user's shell cwd) — the same behavior every other CLI tool gives a
  relative path. This is called out in design.md rather than treated as
  blocking.
