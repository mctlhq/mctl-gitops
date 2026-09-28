# Design: issue-705-media-responses-amplify-memory-10x-fetch

## Current state

### The response envelope every tool shares

`jsonResult` is the single helper almost every tool returns through
(`internal/mcp/tools.go:2308-2316`):

```go
func jsonResult(v any) (*mcplib.CallToolResult, error) {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return mcplib.NewToolResultError("encode: " + err.Error()), nil
	}
	res := mcplib.NewToolResultText(string(b))
	res.StructuredContent = v
	return res, nil
}
```

For a payload holding base64 media this is four live copies of the same bytes
before mcp-go has even started encoding the JSON-RPC response: `b`, the
`string(b)` inside the text content block, the retained `v` in
`StructuredContent`, and then the library's own marshal buffer, which serializes
the base64 twice (text block plus structured content) with `append` growth on
top. `MarshalIndent` also adds indentation to every line of a large payload.

Every media-bearing tool goes through it: `get_unread_messages`
(`internal/mcp/tools.go:334`), `get_messages` (`tools.go:595`), `get_media`
(`internal/mcp/media_tools.go:268`).

### Inline bulk fetch

`fetchMediaInline` (`internal/mcp/bulk_media.go:143-225`) walks the page,
initiating at most `BulkMediaFetchCap = 5` downloads (`bulk_media.go:18`) and
charging every attempt's real wire bytes against
`var BulkMediaByteCap int64 = telegram.DefaultMediaDownloadMaxBytes`
(`bulk_media.go:30`) — i.e. 20 MiB today. Per item it does:

```go
data, consumed, dlErr, attemptedFn := mediaDownloader(s, ctx, userID, *loc, perItemCap) // :195
totalBytes += consumed                                                                 // :219
encoded := base64.StdEncoding.EncodeToString(data)                                      // :220
msgs[i].MediaData = &encoded                                                            // :221
```

`data` stays reachable until the next loop iteration reassigns it, so raw plus
base64 (+33%) of the same file are both live, and the base64 of every earlier
item accumulates in `msgs`. `wrapMessages` (`internal/mcp/format.go:47-68`) then
copies the `[]telegram.Message` slice; `MediaData` is a `*string`
(`internal/telegram/messages.go:45`), so that copy shares bytes rather than
duplicating them — the amplification is entirely in `jsonResult` and in the
download buffer.

Neither cap is configurable: the greps show `BulkMediaByteCap` /
`BulkMediaFetchCap` referenced only inside `bulk_media.go`, its test file, and
the two hardcoded tool-description strings (`tools.go:259`, `tools.go:505`).
Tool descriptions are snapshotted into `docs/tool-descriptors.json` and held by
`TestToolDescriptorsSnapshotMatchesRegistry`
(`internal/mcp/descriptors_test.go:13-48`, regenerate with
`-update-descriptors`).

### The download buffer

`telegram.DownloadMedia` (`internal/telegram/media_download.go:382-392`) streams
gotd's downloader into a `cappedBuffer` (`:323-347`):

```go
w.buf = append(w.buf, p...)   // :344 — no preallocation
```

`buf` starts nil and grows by slice doubling in 512 KiB blocks
(`downloaderPartSize`, `:273`), so a 20 MiB file transits roughly twice through
reallocation copies and can end up with capacity well above its length. The
declared size is already known at both call sites (`telegram.MediaInfo.Size`,
`MediaDownloadRef.Size`) and is simply not passed down. The single-item path is
`toolGetMedia` (`internal/mcp/media_tools.go:243-274`), which downloads into
`buf`, keeps `buf` alive, and then base64-encodes it inline inside the
`jsonResult(getMediaResult{...})` argument — raw and encoded both reachable
during the marshal.

### Admission control

There is none for media. The only server-side admission limit is
`ClientPool.MaxSessions` (`internal/telegram/clientpool.go:85`, `ErrPoolFull` at
`:55`, enforced at `:319`), which caps *sessions*, not concurrent downloads or
bytes, and defaults to `0` (no cap) via `TELEGRAM_MAX_SESSIONS`. The Local Bridge
hub caps pending calls per daemon (`internal/bridge/hub.go:31` `maxPendingCalls =
100`) by count, never by size. No semaphore or byte budget exists anywhere in
`internal/mcp`, `internal/telegram`, or `internal/bridge`.

Config is parsed in `internal/config/config.go` (`MediaDownloadMaxBytes` at
`:209`, parsed at `:432`) and assigned onto the MCP server by direct field
write in `cmd/server/main.go:510-516`. `internal/metrics/metrics.go` has ~40
collectors (`mctl_tool_invocations_total` `:415`, `mctl_tool_call_errors_total`
`:426`, `mctl_telegram_pool_capacity` `:441`) and no bytes/media/in-flight
metric. Failure reasons are a closed set in `internal/mcp/reasons.go` with a
text-literal classifier (`classifyToolResultReason`, `:96`) covered by
`reasons_test.go`.

### Test surface

`internal/mcp/bulk_media_test.go` has 16 tests that stub the downloader by
swapping the `mediaDownloader` package var (`stubDownloader`, `:60-67`) and shrink
the cap with `withBulkMediaByteCap` (`:72-78`), so no real megabytes are ever
allocated. `internal/telegram/media_download_test.go:171-303` unit-tests
`cappedBuffer` with 50-100 byte caps. The repository contains **no** benchmark
functions and no allocation assertions anywhere.

## Proposed solution

Five changes, all inside `internal/mcp`, `internal/telegram`, `internal/config`,
`internal/metrics` and `cmd/server/main.go`. `jsonResult` and its ~90 non-media
call sites are left untouched.

### A. A media-aware result builder (bytes appear once)

New file `internal/mcp/media_result.go`:

```go
// mediaTextInlineCapDefault is the total base64 length below which a media
// result keeps the legacy dual-encoded shape.
const mediaTextInlineCapDefault int64 = 1 << 20

// mediaJSONResult returns v as structuredContent. When mediaBytes exceeds the
// server's inline cap it builds the text block from textView (a copy of v with
// every base64 field replaced by a placeholder) instead of marshalling v, so
// the media bytes are encoded exactly once for the whole response.
func (s *Server) mediaJSONResult(v any, mediaBytes int64, textView any) (*mcplib.CallToolResult, error)
```

Behaviour:

- `mediaBytes <= cap` (or `cap == 0`): `return jsonResult(v)` — byte-identical to
  today, including `MarshalIndent` formatting. Small photos, voice notes, and every
  `fetch_media` call that fetched nothing are unaffected.
- otherwise: `b, err := json.Marshal(textView)` (compact, and `textView` carries
  no media bytes, so this allocation is kilobytes), then
  `res := mcplib.NewToolResultText(string(b)); res.StructuredContent = v`.
  The payload with the base64 is marshalled exactly once, by mcp-go, out of
  `StructuredContent`.

Text views are explicit, reusing the same Go types so the JSON *shape* is
unchanged and the declared output schema still describes it:

- `messagesTextView(result messagesResult) messagesResult` — copies the slice
  (as `wrapMessages` already does) and replaces each non-nil `MediaData` with
  `"<omitted: N base64 bytes; read structuredContent.messages[i].media_data or call prepare_get_media/get_media>"`.
- `getMediaTextView(result getMediaResult) getMediaResult` — same for `Data`.

Two additive fields make the mode machine-detectable without parsing the
placeholder (safe because `outputSchema[T]` deliberately strips
`additionalProperties: false`, `internal/mcp/output_schema.go:33-78`):

- `FetchMediaSummary.MediaDataOmittedFromText bool json:"media_data_omitted_from_text,omitempty"`
  (`bulk_media.go:35`)
- `getMediaResult.DataOmittedFromText bool json:"data_omitted_from_text,omitempty"`
  (`media_tools.go:32`)

Call-site changes: `tools.go:334` and `tools.go:595` compute
`mediaBytes = sum(len(*m.MediaData))` (cheap, no copy) and call
`s.mediaJSONResult(result, mediaBytes, messagesTextView(result))`;
`media_tools.go:268` does the same with `int64(len(dataB64))` and
`getMediaTextView`.

Why this shape rather than dropping the bytes from `structuredContent` and
keeping them in `text`: both bulk tools and `get_media` declare an output schema
(`outputSchema[messagesResult]`, `outputSchema[getMediaResult]`), and a tool
declaring one must return structured content that satisfies it —
`getMediaResult.data` is a required property. Structured content is therefore the
only place the bytes can live unconditionally; the text block is the one that can
carry a summary.

### B. Release the raw bytes early, preallocate the buffer

- `internal/telegram/media_download.go`: add

  ```go
  func DownloadMediaSized(ctx context.Context, c *telegram.Client, loc MediaFileLocation, maxBytes, sizeHint int64) ([]byte, int64, error)
  ```

  which seeds `cappedBuffer{cap: maxBytes, buf: make([]byte, 0, alloc)}` where
  `alloc = min(sizeHint, maxBytes)` when both are positive and `0` otherwise
  (in particular `0` when the declared size is unknown: preallocating the cap
  there would reserve up to 20 MiB per small photo and defeat the change). `DownloadMedia` keeps
  its exact signature and becomes `DownloadMediaSized(..., 0)`, so
  `cmd/local/daemon.go:865` and `media_download_test.go` compile unchanged.
- `bulk_media.go`: pass `msgs[i].MediaInfo.Size` as the hint through
  `mediaDownloader`/`downloadMediaViaPool` (extra `sizeHint` parameter on the
  package var — `stubDownloader` in the test file is updated with it), and set
  `data = nil` immediately after `base64.StdEncoding.EncodeToString(data)` so the
  raw slice is collectable while the next item downloads.
- `media_tools.go`: encode into a local `dataB64`, then `buf = nil` before
  constructing `getMediaResult`, and pass `ref.Size` as the hint.

### C. Media admission gate

New file `internal/mcp/media_gate.go`:

```go
// mediaGate bounds how many media operations may hold downloaded bytes at
// once. A nil *mediaGate imposes no limit, which is what every existing test
// and any Server built without WithMediaConcurrency gets.
type mediaGate struct{ slots chan struct{}; inFlight *prometheus.GaugeVec }

const mediaGateWait = 2 * time.Second

func (g *mediaGate) acquire(ctx context.Context) error // nil when acquired
func (g *mediaGate) release()
```

`acquire` is a `select` over the slot channel, a `time.After(mediaGateWait)`
timer, and `ctx.Done()`. On timeout it returns `errMediaBusy`.

Wiring: `Server.mediaGate *mediaGate` plus `func (s *Server) WithMediaConcurrency(n int) *Server`
in `internal/mcp/server.go` (the established `With*` pattern, e.g.
`WithLimiter`), called from `cmd/server/main.go` next to the existing
`mcpSrv.MediaDownloadMaxBytes = cfg.MediaDownloadMaxBytes` assignments.

Acquisition points — one slot per *operation*, not per item, because a slot's
purpose is to bound how many callers can be accumulating media bytes:

- The `get_messages` / `get_unread_messages` handlers acquire once, only when
  `fetch_media=true`, before calling `fetchMediaInline`, with `defer release()`
  in the handler, so the slot is held through `mediaJSONResult` as well. A
  failure to acquire is rendered as a retryable error result before any
  download starts.
- `toolGetMedia` acquires after the confirmation is claimed and before
  `borrowWithRetry`, with `defer release()` in the handler (not released as
  soon as `dataB64` exists).

Scope of the bound, stated honestly: mcp-go serializes the JSON-RPC response
*after* the handler returns, so the final marshal of the payload — the largest
single allocation — happens outside the slot. The gate therefore bounds
concurrent downloads and result construction, not total media memory. Holding
the slot until the handler returns is the latest point available without
changing the transport. Documentation and the metric help text must describe
`MEDIA_MAX_CONCURRENT` as a limit on concurrent media operations, and the memory
figure below as an estimate, not a guaranteed ceiling. On
  refusal the confirmation is released with `s.Confirms.Unclaim(confID)` and
  `released = true`, exactly like the existing deadline branch
  (`media_tools.go:252-262`), so the client can retry with the same
  `confirmation_id`.

Error text: `"media downloads are at capacity — retry shortly"`. Classified via a
new `ReasonMediaCapacity = "media_capacity"` in `internal/mcp/reasons.go` with a
literal case in `classifyToolResultReason` and a row in `reasons_test.go` (that
test enumerates every literal the handlers can produce). Metrics: a new counter
`mctl_media_gate_rejections_total{tool}` and gauge `mctl_media_inflight` in
`internal/metrics/metrics.go`, both nil-guarded like every other `s.Metrics`
use.

### D. Caps: lower, decouple, configure, document

- `bulk_media.go:30` becomes `var BulkMediaByteCap int64 = 8 << 20` with the
  doc comment updated to explain the decoupling from
  `telegram.DefaultMediaDownloadMaxBytes` and to reference this issue. It stays a
  package var so `withBulkMediaByteCap` keeps working.
- `internal/config/config.go`: three new fields parsed next to the media block
  at `:432` — `BulkMediaByteCap int64` (`BULK_MEDIA_BYTE_CAP`, default
  `8388608`), `MediaTextInlineCapBytes int64` (`MEDIA_TEXT_INLINE_CAP_BYTES`,
  default `1048576`, `0` = always inline), `MediaMaxConcurrent int`
  (`MEDIA_MAX_CONCURRENT`, default `2`, `0` = unlimited). Use `envInt64`
  (`config.go:550`) for the byte values rather than the `int`-returning `envInt`
  the existing media lines use.
- `cmd/server/main.go`: `mcp.BulkMediaByteCap = cfg.BulkMediaByteCap`,
  `mcpSrv.MediaTextInlineCapBytes = cfg.MediaTextInlineCapBytes`,
  `mcpSrv.WithMediaConcurrency(cfg.MediaMaxConcurrent)`.
- Tool descriptions (`tools.go:259`, `tools.go:505`) gain one sentence: the
  aggregate byte cap (8 MiB default, `BULK_MEDIA_BYTE_CAP`) and the fact that
  above 1 MiB of encoded media the bytes are returned in structured content only,
  with a placeholder in the text block. `docs/tool-descriptors.json` is
  regenerated. `media_tools.go:153` (which already documents
  `MEDIA_DOWNLOAD_MAX_BYTES`) gains the same structured-content note.

### E. Resulting memory formula

Per in-flight media operation, with the raw buffer released before marshalling:

```
peak ≈ base64(cap) + marshal_buffer(base64(cap) up to ~2x during growth)
     ≈ 1.33*cap + ~2.7*cap  ≈ 4*cap
```

- bulk `fetch_media` at the new 8 MiB aggregate cap: ~32 MiB per call (was
  ~200 MiB+).
- single `get_media` at the unchanged 20 MiB per-file cap: ~70-80 MiB per call.
- with `MEDIA_MAX_CONCURRENT=2`: typical worst case ~160 MiB above a ~60MB baseline
  (an estimate: responses already handed to mcp-go can still be marshalling
  while new operations start, see section C), i.e.
  ~220 MiB — inside 256Mi, and comfortably inside a 384Mi limit with
  `GOMEMLIMIT` at ~300MiB, which is what the follow-up gitops PR should aim for
  rather than jumping straight back to 256Mi.

## Alternatives

1. **Drop `StructuredContent` for media results and keep the base64 in `text`.**
   Rejected: both bulk tools and `get_media` declare an output schema via
   `outputSchema[T]` (`tools.go:483`, `media_tools.go:56`), and a tool that
   declares one must return structured content; `getMediaResult.data` is a
   required property. Omitting it would break schema-validating clients — the
   exact failure mode #631/#637 already produced on this server.

2. **Return media as an MCP embedded resource / resource link
   (`resources/read` with a `blob`).** Architecturally the best end state: the
   tool response would carry only a URI and the bytes would stream from a
   resource handler, removing base64 from the tool result entirely. Dropped for
   now — the repo has no resource surface for media (the only resource is the
   MCP Apps triage UI behind `AppsEnabled`, `internal/mcpui`), it needs a new
   token-scoped URI namespace with its own TTL/authorization story, and client
   support is uneven. Recorded as the follow-up this proposal's placeholder text
   is designed to make possible without another breaking change.

3. **Only lower the caps (e.g. `BulkMediaByteCap` to 4 MiB, `MEDIA_DOWNLOAD_MAX_BYTES`
   to 8 MiB) and keep the duplication.** Cheapest possible change, and it would
   have prevented this specific kill. Dropped as the primary fix: it leaves a
   ~10x multiplier in place, so the ceiling stays a product of two knobs that are
   easy to raise back, it makes `get_media` unable to fetch files users can fetch
   today, and it still lets N concurrent calls multiply without bound. The cap
   reduction is kept as one part of the fix, not the whole of it.

4. **Global `GOMEMLIMIT` + `debug.SetMemoryLimit` tuning only.** A soft limit
   makes the GC work harder; it does not stop a single request from needing 200MB
   of live heap, and live-heap pressure is what killed the pod. Useful as a
   backstop (already in the stopgap), not a fix.

## Platform impact

**Migrations.** None. No schema change, no `internal/db` change.

**Backward compatibility.**

- Small media (≤1 MiB base64) and every non-media tool: byte-identical
  responses, including `MarshalIndent` whitespace.
- Large media: the `text` block no longer carries the base64. Clients reading
  `structuredContent` (the documented contract for every tool with an output
  schema) are unaffected. Text-only clients get a self-describing placeholder
  naming the byte count and the two ways to obtain the bytes; an operator who
  must serve such a client can set `MEDIA_TEXT_INLINE_CAP_BYTES=0` to restore the
  old behaviour and accept the memory cost.
- Output schemas gain two optional boolean fields only. This is exactly the
  additive change `outputSchema`'s open-schema policy exists to permit
  (`output_schema.go:14-32`), so a frozen client catalogue will not start
  rejecting responses the way it did in #637.
- `fetch_media` pages now stop at 8 MiB of raw bytes instead of 20 MiB, so a
  dense page can report a higher `fetch_media_summary.skipped`. That is already a
  documented, cap-driven outcome of the tool; the description is updated and the
  cap is configurable for anyone who needs the old value.
- `telegram.DownloadMedia` keeps its signature, so `cmd/local/daemon.go` and the
  existing `media_download_test.go` are untouched. `mediaDownloader`'s signature
  gains a `sizeHint` parameter — it is a private package var, and the only
  external users are this package's own tests.

**Resource impact.** Expected per-request peak drops from ~200MB+ to ~32 MiB
(bulk) / ~80 MiB (single file), with total media memory estimated at
`MEDIA_MAX_CONCURRENT * ~4 * cap` (an estimate, not a hard bound: the final
mcp-go marshal happens after the slot is released). Slightly more CPU is spent on nothing — one
fewer full marshal and one fewer large string copy per media response, so CPU
should improve. Latency for media calls can now include up to 2s of gate wait
under concurrency, and a refusal where previously the call proceeded (and might
have OOM-killed the pod).

**Risks and mitigations.**

- *A text-only client silently loses media.* Mitigated by the placeholder text
  naming exactly where the bytes are, the additive detection flags, the 1 MiB
  threshold that leaves typical images inline, and the
  `MEDIA_TEXT_INLINE_CAP_BYTES=0` escape hatch.
- *The gate rejects legitimate traffic.* Default of 2 slots plus a 2s wait, a
  retryable error message classified as `media_capacity`, a rejection counter to
  size it from data, and `MEDIA_MAX_CONCURRENT=0` to disable.
- *`get_media` gate interaction with the single-shot confirmation.* Handled by
  the same `Unclaim`/`released` path the existing timeout branch uses, so a gate
  refusal does not burn the `confirmation_id`.
- *Snapshot drift.* `docs/tool-descriptors.json` is held by a test with an
  explicit regeneration command; it is a mandatory task step.
- *Under-measurement.* The new allocation test asserts against a shrunk
  `BulkMediaByteCap` with a stubbed downloader, so it measures the envelope
  (encode + marshal), which is where the 10x lived — it cannot catch a
  regression in gotd's own buffering, which is why the `cappedBuffer`
  preallocation gets its own unit test in `internal/telegram`.
- *Follow-up not done.* Revisiting `mctlhq/mctl-gitops#1450` (768Mi,
  `GOMEMLIMIT=600MiB`) is a separate PR in another repo; this proposal supplies
  the formula and the target (384Mi / ~300MiB) so that PR is mechanical.
