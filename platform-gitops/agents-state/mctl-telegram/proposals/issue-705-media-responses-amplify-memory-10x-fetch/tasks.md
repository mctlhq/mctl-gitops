# Tasks: issue-705-media-responses-amplify-memory-10x-fetch

- [ ] 1. Add `internal/mcp/media_result.go` with `mediaTextInlineCapDefault = 1 << 20`,
      `Server.MediaTextInlineCapBytes`, and
      `(*Server).mediaJSONResult(v any, mediaBytes int64, textView any)`.
      Below the cap (or cap 0) it delegates to `jsonResult` unchanged; above it,
      it builds the text block with `json.Marshal(textView)` and sets
      `res.StructuredContent = v` — no `MarshalIndent`, no `string(b)` copy of the
      media payload.
      DoD: helper compiles, `go vet` clean, unit-tested in isolation (both branches),
      `jsonResult` and its ~90 other call sites untouched.

- [ ] 2. Add the text views (depends on 1): `messagesTextView(messagesResult) messagesResult`
      and `getMediaTextView(getMediaResult) getMediaResult`, each copying the value and
      replacing base64 fields with
      `"<omitted: N base64 bytes; read structuredContent... or call prepare_get_media/get_media>"`.
      Add additive fields `FetchMediaSummary.MediaDataOmittedFromText`
      (`internal/mcp/bulk_media.go:35`) and `getMediaResult.DataOmittedFromText`
      (`internal/mcp/media_tools.go:32`), both `omitempty`.
      DoD: views allocate nothing proportional to the media bytes; the structured
      payload still validates against the declared output schemas;
      `TestOutputSchemasStayOpenToAdditiveFields` and `TestToolOutputSchemas` pass.

- [ ] 3. Switch the three media call sites to `mediaJSONResult` (depends on 1, 2):
      `internal/mcp/tools.go:334` (get_unread_messages), `tools.go:595` (get_messages),
      `internal/mcp/media_tools.go:268` (get_media). Compute `mediaBytes` by summing
      `len(*m.MediaData)` / `len(dataB64)` without copying.
      DoD: a `fetch_media` result with no fetched bytes takes the legacy path
      byte-for-byte; existing `tools_test.go` / `send_media_test.go` / handler tests pass
      unmodified.

- [ ] 4. Release raw bytes early (depends on 3): in `fetchMediaInline`
      (`bulk_media.go:220`) set `data = nil` right after base64 encoding; in
      `toolGetMedia` encode into a local and set `buf = nil` before building
      `getMediaResult`.
      DoD: no code path holds the raw `[]byte` and its base64 encoding of the same
      file reachable while the response value is handed to mcp-go.

- [ ] 5. Preallocate the download buffer: add
      `telegram.DownloadMediaSized(ctx, c, loc, maxBytes, sizeHint)` in
      `internal/telegram/media_download.go` seeding
      `cappedBuffer{buf: make([]byte, 0, min(sizeHint, maxBytes))}`; keep
      `DownloadMedia` as a `sizeHint = 0` wrapper with its exact current signature.
      Thread a `sizeHint` parameter through `mediaDownloader` /
      `downloadMediaViaPool` (`bulk_media.go:53`, `:78`) passing
      `msgs[i].MediaInfo.Size`, and pass `ref.Size` in `toolGetMedia`.
      DoD: `cmd/local/daemon.go:865` and `internal/telegram/media_download_test.go`
      compile unchanged; cap-rejection semantics (`rejected`, `consumed`,
      read-ahead margin) are provably unchanged.

- [ ] 6. Lower and decouple the aggregate cap: `bulk_media.go:30` becomes
      `var BulkMediaByteCap int64 = 8 << 20` with an updated doc comment citing this
      issue and explaining the decoupling from `telegram.DefaultMediaDownloadMaxBytes`.
      DoD: `withBulkMediaByteCap` still works; no other production reference to the
      old aliasing remains.

- [ ] 7. Add `internal/mcp/media_gate.go`: `mediaGate` (slot channel + optional
      gauge), `mediaGateWait = 2 * time.Second`, `acquire(ctx)` selecting over slot /
      timer / `ctx.Done()`, `release()`, nil receiver = unlimited. Add
      `Server.mediaGate` and `(*Server).WithMediaConcurrency(n int) *Server` in
      `internal/mcp/server.go` following the existing `With*` pattern.
      DoD: a `*Server` from `mcp.New` without the setter behaves exactly as before;
      `go test ./internal/mcp` passes with no test changes for this task alone.

- [ ] 8. Wire the gate into the two media paths (depends on 7): acquire once at the
      top of `fetchMediaInline` with `defer release()`; acquire in `toolGetMedia`
      after the confirmation claim and before `borrowWithRetry`, releasing once the
      base64 exists. On refusal return
      `"media downloads are at capacity — retry shortly"`, and in `toolGetMedia`
      release the claim via `s.Confirms.Unclaim(confID); released = true` so the
      `confirmation_id` survives for a retry (mirror `media_tools.go:252-262`).
      DoD: refusal starts no download, is audited, and leaves the confirmation
      reusable.

- [ ] 9. Add `ReasonMediaCapacity = "media_capacity"` to `internal/mcp/reasons.go`
      with a matching literal case in `classifyToolResultReason` and a row in
      `reasons_test.go` (depends on 8). Add `mctl_media_gate_rejections_total{tool}`
      (counter) and `mctl_media_inflight` (gauge) to `internal/metrics/metrics.go`,
      used nil-guarded from the gate.
      DoD: `reasons_test.go` enumerates the new literal; `/metrics` exposes both
      collectors; no unbounded label cardinality.

- [ ] 10. Config + wiring (depends on 6, 7): add `BulkMediaByteCap`
      (`BULK_MEDIA_BYTE_CAP`, default 8388608), `MediaTextInlineCapBytes`
      (`MEDIA_TEXT_INLINE_CAP_BYTES`, default 1048576, 0 = always inline) and
      `MediaMaxConcurrent` (`MEDIA_MAX_CONCURRENT`, default 2, 0 = unlimited) to
      `internal/config/config.go` beside the media block at `:432`, parsed with
      `envInt64` for the byte values. Wire them in `cmd/server/main.go:510-516`:
      `mcp.BulkMediaByteCap = cfg.BulkMediaByteCap`,
      `mcpSrv.MediaTextInlineCapBytes = cfg.MediaTextInlineCapBytes`,
      `mcpSrv.WithMediaConcurrency(cfg.MediaMaxConcurrent)`.
      DoD: `internal/config/config_test.go` covers default + override for all three;
      defaults reproduce the documented behaviour with no env set.

- [ ] 11. Documentation (depends on 3, 6, 10): update the `fetch_media` paragraphs in
      the `get_messages` / `get_unread_messages` descriptions (`tools.go:259`,
      `tools.go:505`) and the `get_media` description (`media_tools.go:153`) to state
      the 8 MiB aggregate cap, its env override, and the structured-content-only
      behaviour above 1 MiB of encoded media. Regenerate the snapshot:
      `go test ./internal/mcp -run TestToolDescriptorsSnapshotMatchesRegistry -update-descriptors`.
      Document the three new env vars wherever `MEDIA_DOWNLOAD_MAX_BYTES` is
      documented (`README.md` / `docs/`), including the memory formula
      `MEDIA_MAX_CONCURRENT * ~4 * cap`.
      DoD: `docs/tool-descriptors.json` matches the registry; no emoji; English only.

- [ ] 12. Final sweep: `go fmt ./...`, `go vet ./...`, `golangci-lint run`, full
      `go test ./...`. Conventional-commit history on a feature branch, merged with
      `gh pr merge <N> --merge --delete-branch`.
      DoD: CI green; PR body links issue #705 and names the follow-up gitops PR.

## Tests

- [ ] T1. `internal/mcp/media_result_test.go` — `TestMediaJSONResult_BelowCapKeepsLegacyShape`:
      with `mediaBytes` under the inline cap the result is identical to
      `jsonResult(v)` (same text bytes, same `StructuredContent`).
- [ ] T2. `TestMediaJSONResult_AboveCapEmitsBytesOnce`: above the cap, the text block
      contains the placeholder and none of the base64; `StructuredContent` still
      carries the full payload; the full result marshals to JSON containing the
      base64 exactly once.
- [ ] T3. `TestGetMediaResult_AboveCapSetsOmittedFlag` and the bulk equivalent:
      `data_omitted_from_text` / `media_data_omitted_from_text` are true only in the
      omitted mode and absent otherwise (`omitempty`).
- [ ] T4. `internal/mcp/bulk_media_alloc_test.go` —
      `TestFetchMediaInlinePeakAllocations`: `withBulkMediaByteCap(t, 1<<20)`, a
      `stubDownloader` returning synthetic (non-real, non-Telegram) bytes, then measure
      `runtime.MemStats.TotalAlloc` (or `testing.Benchmark(...).AllocedBytesPerOp`)
      across `fetchMediaInline` + result construction + `json.Marshal` of the
      `*CallToolResult`, asserting the delta stays under 4x `BulkMediaByteCap`.
      Include `BenchmarkFetchMediaInlineResult` with `-benchmem` for trend data.
      Verify the test fails against the pre-change code path.
- [ ] T5. `internal/telegram/media_download_test.go` —
      `TestDownloadMediaSized_PreallocatesFromHint`: the buffer's capacity after a
      sized download is `min(sizeHint, maxBytes)`-ish rather than a doubling artefact,
      and `TestDownloadMediaSized_HintDoesNotWidenCap`: a hint above `maxBytes` never
      lets more than `maxBytes` through (existing `cappedBuffer` cap tests still pass).
- [ ] T6. `internal/mcp/media_gate_test.go` — `TestMediaGate_RefusesWhenFull`
      (slots exhausted -> `errMediaBusy` after the wait, no download attempted),
      `TestMediaGate_ReleasesOnAllPaths` (success, per-item error, systemic error,
      ctx cancel all release the slot), `TestMediaGate_NilIsUnlimited`.
- [ ] T7. `TestGetMedia_GateRefusalPreservesConfirmation`: a gate refusal calls
      `Confirms.Unclaim`, leaves the `MediaStore` ref intact, and a retry with the same
      `confirmation_id` succeeds.
- [ ] T8. `internal/mcp/reasons_test.go` — the capacity message classifies as
      `ReasonMediaCapacity`, and no existing literal reclassifies.
- [ ] T9. `internal/config/config_test.go` — defaults and env overrides for
      `BULK_MEDIA_BYTE_CAP`, `MEDIA_TEXT_INLINE_CAP_BYTES` (including `0`) and
      `MEDIA_MAX_CONCURRENT` (including `0`), independent of
      `MEDIA_DOWNLOAD_MAX_BYTES` (mirroring `config_test.go:208-252`).
- [ ] T10. Existing suites pass unmodified except for the `stubDownloader` signature
      update: `bulk_media_test.go` (16 tests), `descriptors_test.go`,
      `output_schema_test.go`, `record_test.go`.
- [ ] T11. Fixtures use synthetic identifiers only (personas `Alice`/`Bob`/`Carol`/`Dana`,
      no real ids, names or handles), per `.claude/CLAUDE.md`.

## Rollback

- The change is a single merged PR with no migration and no persisted state, so
  `mctl_rollback_service` to the previous image tag (or reverting the merge commit
  and re-tagging) fully restores prior behaviour.
- Config-only mitigation without a redeploy, in increasing order of reversal:
  `MEDIA_TEXT_INLINE_CAP_BYTES=0` restores the base64 in the text block for
  text-only clients; `MEDIA_MAX_CONCURRENT=0` disables the admission gate;
  `BULK_MEDIA_BYTE_CAP=20971520` restores the old 20 MiB aggregate cap. Setting all
  three reproduces pre-change behaviour except for the (memory-only) early release
  and buffer preallocation.
- Keep the `mctlhq/mctl-gitops#1450` stopgap (768Mi, `GOMEMLIMIT=600MiB`) in place
  until this release has run a full week with `mctl_media_inflight` and
  `mctl_media_gate_rejections_total` observed; only then open the follow-up gitops
  PR lowering to ~384Mi / `GOMEMLIMIT≈300MiB`. If memory regresses after that PR,
  revert the gitops PR first — it is independent of this repo's rollback.
