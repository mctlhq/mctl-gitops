# Bound media response memory: emit inline media bytes once and cap media concurrency

## Context

On 2026-09-28 the production `mctl-telegram` pod (0.69.0) was OOM-killed at its
256Mi limit within one 30s scrape interval, immediately after a `get_messages`
call with `fetch_media=true` that downloaded 5 media items. Baseline working set
was ~60MB and the 7-day peak was 91MB, so this is a single-request spike, not a
leak. The amplification is structural: `fetchMediaInline`
(`internal/mcp/bulk_media.go`) may pull up to `BulkMediaByteCap` (today 20 MiB,
aliased to `telegram.DefaultMediaDownloadMaxBytes`) of raw bytes per call, those
bytes are base64-encoded into `telegram.Message.MediaData` (+33%), and then
`jsonResult` (`internal/mcp/tools.go:2308`) holds the same payload four more
times over: `json.MarshalIndent` output, a `string(b)` copy of it into the text
content block, the identical value retained in `res.StructuredContent`, and
finally mcp-go's own marshal of the JSON-RPC response, which encodes the base64
twice (once inside the text block, once as structured content) with buffer
growth on top. `get_media` (`internal/mcp/media_tools.go:268`) does the same for
a single file of up to `MEDIA_DOWNLOAD_MAX_BYTES` (20 MiB). The stopgap
`mctlhq/mctl-gitops#1450` raised the limit to 768Mi with `GOMEMLIMIT=600MiB`;
two concurrent media calls still exceed that.

This proposal removes the duplication (the base64 must appear exactly once in a
large response), removes the intermediate copies on the media path, preallocates
the download buffer instead of relying on `append` doubling, lowers
`BulkMediaByteCap` to 8 MiB and makes it configurable, and adds a server-wide
admission gate on concurrent media operations so a burst returns a retryable
error instead of killing the pod. It matters because an OOM kill takes down
every other tool call and every Local Bridge websocket on that replica, and
because `fetch_media` is exposed to any MCP client with
`telegram:messages:read`.

## User stories

- AS an operator of `tg.mctl.ai` I WANT a `fetch_media=true` page or a
  `get_media` download to cost memory proportional to the byte cap, not ~10x it,
  SO THAT one media call cannot OOM-kill the pod and drop every other session.
- AS an SRE I WANT concurrent media downloads bounded with a clear retryable
  error SO THAT a burst of media calls degrades gracefully instead of
  terminating the process.
- AS an MCP client author I WANT the media bytes in exactly one documented place
  in the response, with a machine-readable marker where they were omitted, SO
  THAT I can find them deterministically and know when to fall back to
  `prepare_get_media`/`get_media`.
- AS a platform engineer I WANT the memory ceiling of the media path expressed
  as a formula over configuration SO THAT the 768Mi stopgap in
  `mctlhq/mctl-gitops#1450` can be revisited with evidence.
- AS a maintainer I WANT an allocation test around the media handler path SO
  THAT a future refactor cannot silently reintroduce the duplication.

## Acceptance criteria (EARS)

Response shaping

- WHEN `get_messages` or `get_unread_messages` is called with
  `fetch_media=true` and the total base64 length of all `media_data` values in
  the result exceeds `MEDIA_TEXT_INLINE_CAP_BYTES` (default 1 MiB), THE SYSTEM
  SHALL place the base64 only in `structuredContent` and emit a text content
  block of the same JSON shape in which each `media_data` value is replaced by a
  short placeholder string naming the omitted byte count and where to read the
  bytes.
- WHEN the same call's total base64 length is at or below
  `MEDIA_TEXT_INLINE_CAP_BYTES`, THE SYSTEM SHALL return the result exactly as
  it does today (base64 in both the text block and `structuredContent`,
  `json.MarshalIndent` formatting), so small photos and voice notes are
  byte-for-byte unchanged for existing clients.
- WHEN `get_media` returns a payload whose base64 `data` exceeds
  `MEDIA_TEXT_INLINE_CAP_BYTES`, THE SYSTEM SHALL apply the same rule to
  `getMediaResult.Data`.
- WHEN media bytes are omitted from the text block, THE SYSTEM SHALL set an
  additive boolean flag in the structured payload
  (`fetch_media_summary.media_data_omitted_from_text` for the bulk tools,
  `data_omitted_from_text` for `get_media`) so a client can detect the mode
  without string-matching the placeholder.
- WHILE an output schema is declared for a tool (`outputSchema[T]`,
  `internal/mcp/output_schema.go`), THE SYSTEM SHALL keep returning
  `structuredContent` that validates against it, and SHALL only add fields
  (never remove or rename), preserving the open-schema contract that
  `TestOutputSchemasStayOpenToAdditiveFields` enforces.
- IF `MEDIA_TEXT_INLINE_CAP_BYTES` is set to `0` THEN THE SYSTEM SHALL always
  inline the bytes in the text block, restoring pre-change behaviour for an
  operator who must support a text-only client and accepts the memory cost.

Copy elimination

- WHILE building a media-bearing result above the inline cap, THE SYSTEM SHALL
  NOT call `json.MarshalIndent` on the payload and SHALL NOT make a
  `string([]byte)` copy of a marshalled payload; the text block SHALL be built
  from a placeholder view whose size is independent of the media bytes.
- WHEN a media download finishes, THE SYSTEM SHALL drop its reference to the raw
  `[]byte` before the response value is handed to mcp-go, so raw and base64
  copies of the same file are not both reachable during response marshalling.
- WHEN a media download starts and a declared size is known
  (`telegram.MediaInfo.Size` or `MediaDownloadRef.Size`), THE SYSTEM SHALL
  preallocate the accumulation buffer to `min(declared size, effective cap)` so
  `cappedBuffer.Write` (`internal/telegram/media_download.go:331`) does not
  double a 20 MiB slice through `append` growth.
- WHILE no declared size is available (photos report `Size == 0`), THE SYSTEM
  SHALL preallocate no more than the effective per-item cap.

Caps and admission control

- WHEN no override is configured, THE SYSTEM SHALL use a `BulkMediaByteCap` of
  8 MiB, decoupled from `telegram.DefaultMediaDownloadMaxBytes`.
- WHEN `BULK_MEDIA_BYTE_CAP` is set, THE SYSTEM SHALL use that value as the
  per-call aggregate raw-byte budget for inline bulk fetch.
- WHEN the `get_messages` / `get_unread_messages` tool descriptions are rendered,
  THE SYSTEM SHALL state the aggregate byte cap and its default, and state that
  above the inline cap the bytes are returned in structured content only.
- WHILE the number of in-flight media operations (one per `fetchMediaInline`
  call, one per `get_media` download) is at `MEDIA_MAX_CONCURRENT` (default 2),
  THE SYSTEM SHALL make a new media operation wait at most
  `mediaGateWait` (2s) for a slot.
- IF no slot becomes free within that wait THEN THE SYSTEM SHALL return a
  non-fatal, retryable error result telling the caller to retry shortly, SHALL
  NOT start the download, and SHALL record the call in `audit_logs` with a
  dedicated reason (`media_capacity`) and increment a Prometheus counter.
- IF `MEDIA_MAX_CONCURRENT` is `0` THEN THE SYSTEM SHALL impose no gate
  (documented as unsafe), and a `*Server` built without the gate configured
  (every existing unit test, `mcp.New`) SHALL behave exactly as before.
- WHILE the gate is configured, THE SYSTEM SHALL expose the number of in-flight
  media operations as a Prometheus gauge.

Regression protection

- WHEN the media allocation test runs with `BulkMediaByteCap` shrunk to a small
  value and a stubbed downloader (`stubDownloader`,
  `internal/mcp/bulk_media_test.go:60`), THE SYSTEM SHALL keep total bytes
  allocated while building and marshalling the response below a fixed multiple
  (4x) of the aggregate byte cap.
- WHEN `docs/tool-descriptors.json` is compared against the live registry, THE
  SYSTEM SHALL match (regenerated with
  `go test ./internal/mcp -run TestToolDescriptorsSnapshotMatchesRegistry -update-descriptors`).

## Out of scope

- Changing the 768Mi limit / `GOMEMLIMIT` in `mctlhq/mctl-gitops#1450`. That is
  a separate repo and a separate PR, to be revisited after this release; this
  proposal only publishes the resulting memory formula.
- Serving media as MCP resource links / `resources/read` (`blob`) instead of
  inline content. Recorded as a follow-up: it would remove the base64 from the
  tool response entirely, but requires a client-support survey and a new
  resource surface.
- Lowering the `MEDIA_DOWNLOAD_MAX_BYTES` default (20 MiB) for single-file
  `get_media`. Only the bulk aggregate cap is lowered here.
- Local Bridge daemon memory (`cmd/local/daemon.go:840-889` encodes base64 with
  a hardcoded 20 MiB cap). The daemon runs on the operator's own machine, not the
  pod; `fetch_media=true` is already refused in bridge mode
  (`internal/mcp/tools.go:278`, `:532`).
- Streaming/chunked or resumable media transfer, range requests, and any change
  to `internal/bridge` framing (`MaxMediaFrameBytes`, 32 MiB).
- Touching `jsonResult`'s behaviour for the ~90 non-media tool call sites.

## Open questions

- Exact value of `MEDIA_TEXT_INLINE_CAP_BYTES`: 1 MiB is chosen so typical
  photos and voice notes keep today's dual-encoded behaviour while videos and
  documents switch to structured-only. Proceeding with 1 MiB, configurable.
- Whether any client currently reading `tg.mctl.ai` consumes only the text block
  for media (the Cloudflare MCP portal catalogue, ChatGPT, Claude connectors all
  read structured content where a schema is declared). Proceeding with the
  placeholder + `MEDIA_TEXT_INLINE_CAP_BYTES=0` escape hatch as the compatibility
  answer rather than blocking on a survey.
- Whether the media gate should be a weighted byte budget rather than slots. The
  issue suggests slots ("e.g. 2 concurrent media downloads"); proceeding with
  slots plus a documented worst-case formula, since a byte budget needs a
  reservation for photos whose declared size is 0.
- Whether `fetch_media_summary` should also report the aggregate byte cap and
  bytes consumed. Proposed as an additive field (`byte_cap`, `bytes`) because the
  schema is open, but not required by the issue.
