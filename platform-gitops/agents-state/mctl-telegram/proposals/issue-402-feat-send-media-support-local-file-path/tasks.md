# Tasks: issue-402-feat-send-media-support-local-file-path

- [ ] 1. Add `file_path` to the `send_media` MCP tool schema in
      `internal/mcp/media_tools.go` (`toolSendMedia`), with description text
      covering Local Bridge-only support and mutual exclusivity with
      `file_url`/`file_base64` — DoD: `mcplib.WithString("file_path", ...)`
      present; tool description text updated; `go build ./...` passes.

- [ ] 2. Replace the 2-way XOR validation
      (`(fileURL == "") == (fileB64 == "")`) with an "exactly one of
      file_path/file_url/file_base64" check in `toolSendMedia` (depends on 1)
      — DoD: zero sources set -> error; two or three sources set -> error;
      exactly one set (including `file_path` alone) -> passes validation;
      covered by new table-driven cases in
      `internal/mcp/send_media_test.go` alongside the existing
      `TestToolSendMedia_BothSourcesSet`.

- [ ] 3. Derive `file_name` from `filepath.Base(file_path)` when `file_path`
      is the source and `file_name` was not supplied, writing the derived
      name back into `args["file_name"]` before any gate/bridge branching
      (depends on 1) — DoD: `media_type="document"` + `file_path` + no
      `file_name` no longer errors (unlike the equivalent `file_base64`
      case); unit test asserts the derived name appears in the dry-run
      preview's `file_name` field.

- [ ] 4. Add the hosted-mode rejection for `file_path`: when `file_path` is
      set and the account is not resolved to Local Bridge mode
      (`s.Hub == nil` or `s.Store.GetAccountMode(...) != "local"`), return a
      validation error before the gate/draft branch runs and before any
      filesystem access (depends on 1, 2) — DoD: unit test on a
      `Server{Hub: nil}` (or bridge-mode-lookup returning non-"local") with
      `file_path` set to a real file on the test machine returns
      `res.IsError == true` and the test file's mtime/access-time is
      provably untouched (or simply: the test never needs the file to
      exist, proving no read is attempted) — matches the "no filesystem
      interaction" risk called out in design.md.

- [ ] 5. Confirm/adjust the existing bridge-forwarding branch in
      `toolSendMedia` so `args` (now including `file_path` and the
      possibly-derived `file_name`) is forwarded to
      `s.bridgeCall(ctx, id, "send_media", args)` unchanged in shape
      (depends on 3, 4) — DoD: existing bridge-mode tests still pass;
      no new marshaling needed since `args` is already a raw
      `map[string]any`.

- [ ] 6. Add `FilePath`/`FileName`-fallback handling to the `case
      "send_media":` arm in `cmd/local/daemon.go`: read the file via
      `os.ReadFile`, enforce `tg.DefaultMediaUploadMaxBytes`, detect MIME
      via `http.DetectContentType`, and fall back to `filepath.Base` for
      `FileName` if still empty (depends on 1) — DoD: daemon-side unit test
      (or table-driven extension of existing daemon dispatch tests, if
      present) exercising a real temp file: success path returns a
      `tg.SendMediaResult`-shaped JSON payload with correct `mime_type`/
      `file_name`; oversized file returns the same error shape as the
      existing `file_base64` oversize case; nonexistent path returns a
      clear `send_media: file_path: ...` error.

- [ ] 7. Update `README.md`'s `send_media` row (and any other docs that
      enumerate `send_media` inputs, e.g. `docs/` if it duplicates the
      table) to mention `file_path` as a third source, Local Bridge-only,
      with basename derivation (depends on 1-6) — DoD: docs describe all
      three sources and the hosted-mode restriction; `grep -rn
      "file_base64/file_url\|file_url/file_base64"` in docs finds no
      stale two-source phrasing left unaddressed.

- [ ] 8. Run full verification: `go fmt ./...`, `go vet ./...`,
      `go test ./...`, and `golangci-lint run` if available (depends on
      1-7) — DoD: all green, no new lint findings.

## Tests
- [ ] T1. `internal/mcp/send_media_test.go`: exactly-one-of-three
      validation — 0, 2, and 3 sources set all error; each single source
      alone passes validation (reuse `sendMediaTestServer`/
      `sendMediaScopedIdentity` helpers already in the file).
- [ ] T2. `internal/mcp/send_media_test.go`: `file_path` + `media_type
      != "document"` + no `file_name` -> dry-run preview's `file_name`
      equals `filepath.Base(file_path)`.
- [ ] T3. `internal/mcp/send_media_test.go`: `file_path` set on a
      hosted-mode (non-bridge) server -> `IsError`, and the call performs
      no gate evaluation side effects beyond the validation error (assert
      via a `file_path` pointing at a path guaranteed not to exist, e.g.
      `/nonexistent/for-test-only`, so any accidental read would surface
      as a different, filesystem-shaped error rather than the expected
      validation error).
- [ ] T4. `internal/mcp/send_media_test.go`: draft-by-default still holds
      for `file_path` — with `AllowSend=false`, a `file_path`-sourced call
      returns `sent=false` and never attempts to read the file (same
      technique as T3: point at a nonexistent path and assert the
      validation/dry-run response, not a filesystem error).
- [ ] T5. `cmd/local` (daemon dispatch test, new or extended): `file_path`
      success path — write bytes to a `t.TempDir()` file, dispatch
      `send_media` with `mode="send"` and that path, assert the resulting
      `tg.SendMediaResult` has the right `file_name` (basename) and that
      `mime_type` matches `http.DetectContentType` on the same bytes.
- [ ] T6. `cmd/local` (daemon dispatch test): `file_path` oversize —
      file larger than `tg.DefaultMediaUploadMaxBytes` -> daemon returns
      the "exceeds the N-byte upload cap" error, no partial send attempted
      (assert no `MessagesSendMediaRequest`-shaped side effect if the test
      harness can observe that, otherwise assert the error return alone).
- [ ] T7. `cmd/local` (daemon dispatch test): `file_path` missing/
      unreadable -> daemon returns a `send_media: file_path: ...` error,
      distinguishable from the oversize error.
- [ ] T8. Regression: existing `file_url`/`file_base64` test suites in
      both `internal/mcp/send_media_test.go` and `cmd/local` continue to
      pass unmodified (guards against the 2-way -> 3-way exclusivity
      refactor breaking the original two sources).

## Rollback
This is a purely additive MCP tool-input change with no data migrations, no
new persistent state, and no config flag gating it — rollback is a plain
revert of the PR (or a follow-up PR removing the `file_path` schema field
and the two new code branches in `toolSendMedia` and `cmd/local/daemon.go`).
Because the hosted-mode rejection path means the hosted server never
performs new filesystem I/O, and the daemon-side change only adds a new
`case` arm reusing the existing `tg.SendMedia`/upload-cap machinery, a
revert carries no risk to already-in-flight `file_url`/`file_base64` calls.
No feature flag is introduced; if a staged rollout is desired, it can be
gated by keeping the daemon-side `case args.FilePath != "":` branch behind a
review-only merge (not deployed) while the MCP-schema and validation changes
land first, though this is not required given the change's additive nature.
