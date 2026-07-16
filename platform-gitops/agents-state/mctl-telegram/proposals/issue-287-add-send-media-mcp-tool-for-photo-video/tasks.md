# Tasks: issue-287-add-send-media-mcp-tool-for-photo-video

- [ ] 1. Add `MEDIA_UPLOAD_MAX_BYTES` config plumbing: `Config.MediaUploadMaxBytes`
      in `internal/config/config.go` (default 20971520, same pattern as
      `MediaDownloadMaxBytes`), `Server.MediaUploadMaxBytes` field in
      `internal/mcp/server.go`, wired at construction in `cmd/server/main.go`.
      — DoD: `go build ./...` passes; a config test in
      `internal/config/config_test.go` asserts the default and an override via
      env var, following the existing test style for `MEDIA_DOWNLOAD_MAX_BYTES`.

- [ ] 2. Build the guarded URL fetcher (new file, e.g.
      `internal/telegram/fetchmedia.go` or `internal/httpfetch/httpfetch.go`):
      HTTPS-only, resolves and rejects loopback/link-local/private-range IPs
      before connecting and re-validates at dial time (DNS-rebinding guard),
      bounded request timeout, streams the body capped at a caller-supplied
      max-bytes argument, returns a clear typed error for each failure mode
      (bad scheme, disallowed IP, timeout, oversized). — DoD: unit tests cover
      each rejection path (http scheme, private IP direct, private IP via
      redirect, oversize response, slow/timeout response) using
      `httptest.Server` and a fake resolver/dialer; no real network calls in
      tests.

- [ ] 3. Implement `telegram.SendMedia` in `internal/telegram` (depends on 2).
      Mirrors `SendMessage`'s dry-run/real-send split in `send.go`; on the
      real-send path, uploads bytes via `gotd/td`'s upload mechanism (verify
      exact package/type names against the vendored `github.com/gotd/td
      v0.144.0` source — see `design.md`'s Open Questions caveat before
      writing this), builds the correct `tg.InputMediaClass` per
      `media_type` (photo/video/document/animation), sets
      `DocumentAttributeAnimated` for `animation` so it is never relabeled as
      `video`, and sends via `MessagesSendMediaRequest`. Extract the shared
      peer-resolve + `PEER_ID_INVALID` retry logic out of `SendMessage` into a
      small helper both functions call, rather than duplicating it.
      — DoD: `go vet` and `golangci-lint` clean; unit tests (with a
      fake/mock `gotd/td` transport or the repo's existing test doubles for
      `telegram.Client`, following the pattern in
      `internal/telegram/media_download_test.go`) cover: dry-run returns no
      RPC call, photo/video/document/animation each produce the expected
      `InputMediaClass`/attributes, `PEER_ID_INVALID` triggers exactly one
      cache-evict-and-retry like `SendMessage` does.

- [ ] 4. Implement `toolSendMedia` in `internal/mcp/media_tools.go` (depends
      on 1, 3). Input validation (media_type enum, exactly-one-of
      file_url/file_base64, file_name required for document+file_base64)
      before any gate evaluation or I/O; `requireScope`
      ("telegram:messages:send") checked eagerly; reuses `evaluateSendGate`
      and `evaluateDirectSendLimiter` unmodified; dry-run branch performs no
      fetch/decode; real-send branch resolves bytes (base64 decode or guarded
      URL fetch), checks against `MediaUploadMaxBytes` before the Telegram
      call, routes through `s.bridgeCall` for local-mode accounts (task 6) or
      `s.borrowWithRetry` + `telegram.SendMedia` for hosted-mode; errors
      funneled through `borrowErrResult`; every branch calls `s.audit(...)`
      with `telegram.RedactPeer(peer)`. New `sendMediaResult` struct with
      `sent, mode, peer, message_id, media_type, mime_type, file_name,
      caption, dry_reason, notice` (omitempty where applicable).
      — DoD: tool description documents the acceptance criteria from
      `requirements.md` (media_type values, source options, draft-by-default,
      size cap, animation-vs-video distinction); `WithOutputSchema` wired.

- [ ] 5. Register `send_media` in `internal/mcp/server.go`'s `HTTPHandler()`
      (depends on 4). — DoD: tool appears in the MCP tool list at runtime
      (verify via MCP inspector or the existing pattern in
      `internal/mcp/tools_test.go`/`annotations_test.go` that enumerates
      registered tools and checks annotations).

- [ ] 6. Add Local Bridge daemon parity: `case "send_media":` in
      `cmd/local/daemon.go`'s `dispatchCall`, mirroring the existing
      `case "send_message":` block (depends on 3). — DoD: a local-mode
      account can send media through the daemon path; daemon-side test
      coverage added alongside existing daemon dispatch tests if any exist
      (check `cmd/local/daemon_test.go`), otherwise add one.

- [ ] 7. Update docs (depends on 4, 5): add a `send_media` row to the
      `## MCP tools` table in `README.md` matching the existing style
      (annotations + inputs + gate behavior + size cap + animation note);
      update any tool-count reference in `README.md`'s status line if present;
      cross-check `claude-connector-submission.md` /
      `chatgpt-app-submission.json` for tool inventories that may also need
      the new tool listed (grep for `send_message` in both files to find the
      right insertion points). — DoD: docs describe inputs, draft-by-default
      behavior, the upload size cap and its env var, and the
      animation-vs-video distinction, consistent with `requirements.md`.

- [ ] 8. Metrics (depends on 2, 4): add a counter/histogram for `file_url`
      fetch outcomes (success/rejected-scheme/rejected-ip/timeout/oversized)
      to `internal/metrics/metrics.go`, following the existing
      `ToolInvocationsTotal`/`ToolInvocationDuration` pattern, so the new
      outbound-fetch surface is observable. — DoD: metric emitted on every
      `file_url` fetch attempt in `toolSendMedia`.

## Tests

- [ ] T1. Dry-run parity: `send_media` with the gate closed (no `ALLOW_SEND`,
      missing scope, `send_enabled=false`, or demo-reviewer identity) returns
      `sent=false` with a populated `dry_reason` and makes no Telegram call
      and no `file_url`/`file_base64` resolution — for every media_type.
      Mirrors the existing `send_message_test.go` dry-run cases.
- [ ] T2. Real send (hosted mode, gate open, mocked `gotd/td` transport):
      each of photo/video/document/animation produces a real `message_id`
      and the correct MTProto attributes; animation is never sent with only
      a `DocumentAttributeVideo` (must include `DocumentAttributeAnimated`).
- [ ] T3. Validation errors, no I/O performed: missing `peer`; invalid
      `media_type`; both `file_url` and `file_base64` set; neither set;
      `document` + `file_base64` without `file_name`.
- [ ] T4. Oversized `file_base64`: decoded length above
      `MediaUploadMaxBytes` returns a clear error before any Telegram call
      (assert no RPC was attempted, e.g. via the mock transport's call
      count).
- [ ] T5. Oversized/misbehaving `file_url`: response larger than
      `MediaUploadMaxBytes` (via `httptest.Server` streaming past the cap) is
      rejected with a clear error, not a raw timeout/500; response that never
      completes within the fetch timeout returns a clear timeout error.
- [ ] T6. SSRF guard: `file_url` pointing at `http://` (non-TLS),
      `https://127.0.0.1/...`, `https://169.254.169.254/...`, and a redirect
      chain that starts at an allowed host but 302s to a private IP, are all
      rejected before any bytes are fetched from the disallowed target.
- [ ] T7. Per-peer rate limiting: repeated real `send_media` calls to the
      same peer count against the same `audit.RateLimiter` budget
      `send_message` uses (assert the shared cap trips), confirming no
      separate unmetered channel was introduced.
- [ ] T8. Local Bridge routing: a local-mode account's `send_media` call is
      forwarded via `s.bridgeCall`/`cmd/local/daemon.go`'s new dispatch case
      rather than `s.borrowWithRetry`, and a hosted-mode account is not.
- [ ] T9. Audit logging: every branch (dry-run, hosted real-send, local
      real-send, validation error, gate-denied) produces exactly one
      `s.Store.LogToolCall` row with the peer redacted via
      `telegram.RedactPeer`, matching `send_message`'s audit coverage.
- [ ] T10. Tool list / schema: `send_media` appears in the MCP tool list with
      the documented annotations (`readOnly=false`, `destructive=true`,
      `openWorld=true`) and a valid output schema, following the pattern in
      `internal/mcp/output_schema_test.go`.

## Rollback

- The change is purely additive (new tool, new optional env var with a safe
  default, new `Server`/`Config` fields). Rollback is a standard revert of the
  merged PR / redeploy of the prior image tag — no data migration to reverse,
  no schema change to undo.
- If `send_media` ships but the `file_url` guarded fetcher is judged too risky
  post-review (see `design.md` Alternative 3), the fast partial rollback is to
  gate `file_url` support behind a new env flag (e.g.
  `ALLOW_SEND_MEDIA_FROM_URL`, default `false`) rather than reverting the
  whole tool — `file_base64` sends keep working, `file_url` calls return a
  clear "disabled by operator" error instead of attempting a fetch. This can
  be a same-day config change (no redeploy of code, just env var) if wired as
  a config check rather than a compile-time removal.
- If a production incident traces to the outbound fetcher specifically
  (e.g. an SSRF bypass discovered after rollout), disable `file_url` via the
  same flag immediately, then patch and re-enable, rather than rolling back
  the entire tool (which would also remove the lower-risk `file_base64` path
  that unblocks the issue's primary motivating use case).
- No dependent services or downstream consumers are known to key off the
  MCP tool list at startup in a way that would be broken by a rollback that
  removes the tool (it is a net-new capability, not a modification of an
  existing contract).
