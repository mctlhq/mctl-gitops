# Design: issue-707-follow-ups-from-706-media-gate-and-confi

## Current state

### Config (`internal/config/config.go`)

The three #705 knobs are resolved in `Load()` at lines 451-468:

```go
c.BulkMediaByteCap = envInt64("BULK_MEDIA_BYTE_CAP", 8388608)
if c.BulkMediaByteCap <= 0 {
    slog.Warn("BULK_MEDIA_BYTE_CAP must be positive; falling back to the 8388608-byte default ...")
    c.BulkMediaByteCap = 8388608
}
c.MediaTextInlineCapBytes = envInt64("MEDIA_TEXT_INLINE_CAP_BYTES", 1048576)
if c.MediaTextInlineCapBytes < 0 {
    slog.Warn("MEDIA_TEXT_INLINE_CAP_BYTES is negative; treating as 0 (media base64 always inlined in the text block)", ...)
    c.MediaTextInlineCapBytes = 0
}
c.MediaMaxConcurrent = envInt("MEDIA_MAX_CONCURRENT", 2)
if c.MediaMaxConcurrent < 0 {
    slog.Warn("MEDIA_MAX_CONCURRENT is negative; treating as unlimited (no gate)", ...)
}
```

Three different shapes for three adjacent knobs. `BulkMediaByteCap` clamps to
its safe default. `MediaTextInlineCapBytes` clamps *away* from its default,
to the `0` that `internal/mcp`'s `mediaJSONResult` reads as "always inline"
— the pre-#705 dual-encoding the OOM investigation removed. `MediaMaxConcurrent`
warns and leaves the negative value in the struct; the behaviour happens to be
right only because `WithMediaConcurrency` treats any `n <= 0` as "no gate", so
the struct field and the enforced policy disagree in wording while agreeing in
effect.

Field docs are at `internal/config/config.go:216-232`. Tests live in
`internal/config/config_test.go`: `TestLoadBulkMediaByteCap` (265),
`TestLoadMediaTextInlineCapBytes` (296, with a `"negative is treated as
zero"` row), `TestLoadMediaMaxConcurrent` (326, with no negative row), and
`TestLoadNonPositiveBulkMediaByteCapFallsBack` (525).

### The gate (`internal/mcp/media_gate.go`, `internal/mcp/server.go`)

`mediaGate` is a buffered channel used as a counting semaphore, with an
optional `prometheus.Gauge`:

```go
var mediaGateWait = 2 * time.Second   // "A package var, not a const, so tests can shrink it"

type mediaGate struct {
    slots    chan struct{}
    inFlight prometheus.Gauge
}

func (g *mediaGate) acquire(ctx context.Context) error {
    if g == nil { return nil }
    timer := time.NewTimer(mediaGateWait)
    ...
}
```

`acquire` reads the package var on every call, and it is called from
`internal/mcp/tools.go:320` (`get_messages`), `tools.go:589`
(`get_unread_messages`) and `internal/mcp/media_tools.go:258` (`get_media`).
`internal/mcp/media_gate_test.go:129` mutates it via a `withMediaGateWait`
helper (also used by `get_media_gate_test.go:56`), and
`TestMediaGate_ConcurrentAcquireReleaseStaysWithinCapacity` spawns eight
goroutines that each call `acquire`. Nothing prevents a future test from
shrinking the var while another test's gate goroutines are still in
`acquire` — with `-race`, that is a reportable race on a shared variable, not
merely a flake.

`Server.mediaGate` is installed by the builder option at
`internal/mcp/server.go:210`:

```go
func (s *Server) WithMediaConcurrency(n int) *Server {
    if n <= 0 { s.mediaGate = nil; return s }
    var inFlight prometheus.Gauge
    if s.Metrics != nil { inFlight = s.Metrics.MediaInflight }
    s.mediaGate = newMediaGate(n, inFlight)
    return s
}
```

The gauge is wired only when `WithMetrics` already ran. `cmd/server/main.go`
happens to satisfy that (`WithMetrics` at line 510, `WithMediaConcurrency` at
522, with a comment at 518-521 saying so), but the ordering is an unenforced
convention: reordering the chain loses `mctl_media_inflight` silently, with no
test failing. `WithMediaConcurrency` has no test at all today —
`internal/mcp/media_gate_test.go` and `get_media_gate_test.go` construct
`newMediaGate` / assign `s.mediaGate` directly.

`internal/mcp/media_gate_test.go:3-11` puts `prometheus` and
`prometheus/testutil` inside the stdlib import group, unlike every sibling
file (`get_media_gate_test.go:3-15`).

### Metrics (`internal/metrics/metrics.go`)

`MediaGateRejectionsTotal` is created at line 593, `MediaInflight` at 598,
both registered at 657-658. The zero-baseline pre-init loop at 678 reads
`MediaGateTools`, which is declared at the very bottom of the file, after
`New()` returns:

```go
// MediaGateTools is the fixed label set of mctl_media_gate_rejections_total ...
var MediaGateTools = []string{"get_messages", "get_unread_messages", "get_media"}
```

Every sibling label list — `policySurfaces`, `policyDenyReasons`,
`jobStatuses`, `claudeResultClasses`, `jobCostResults`, `workContextRoutes`,
`workContextOutcomes`, `workContextBindingResults` — is unexported and
declared together at lines 231-331, above `New()`, under a comment
(lines 314-318) that names the complete set. `MediaGateTools` is the one
outlier, and `grep -rn MediaGateTools` finds consumers only in
`internal/metrics/metrics.go` and `internal/metrics/metrics_test.go` (same
package): the export buys nothing and widens the package API.

`expectedMetricNames` (`internal/metrics/metrics_test.go:14-45`) is the
by-name registration guard. It ends at `mctl_work_context_bindings_total`:
neither `mctl_media_inflight` nor `mctl_media_gate_rejections_total` is
listed. `mctl_media_gate_rejections_total` is at least indirectly pinned by
`TestNew_MediaGateRejectionsZeroBaseline` (line 552);
`mctl_media_inflight` is pinned by nothing in `internal/metrics` — only by
`TestMediaGate_InFlightGaugeTracksHeldSlots`
(`internal/mcp/media_gate_test.go:139`), which constructs its own throwaway
gauge named `test_media_inflight` and so would keep passing if the real
family were renamed or dropped.

### Runbook (`docs/runbook.md`)

The "Media response memory bounds (issue #705)" section holds the three-row
knob table (lines 2485-2487). The `BULK_MEDIA_BYTE_CAP` row explains its
`<= 0` fallback; the other two rows document only the `0` meaning and say
nothing about a negative value. Lines 2519-2522 list the config-only
mitigations in increasing order of reversal.

## Proposed solution

Seven scoped changes, no behaviour change for any valid configuration.

### 1. `MEDIA_TEXT_INLINE_CAP_BYTES < 0` clamps to the default

In `Load()`, replace the `= 0` clamp with `= 1048576` and reword the warning
to say the default was applied and that `0` must be set explicitly to get
always-inline. This makes the negative case fail *toward* the bounded
behaviour, matching `BULK_MEDIA_BYTE_CAP` two lines above. The explicit `0`
path is untouched, so the documented text-only-client escape hatch survives.

To keep the literal from being written in three places, hoist the three
defaults to package consts next to the existing
`maxOAUTHAccessTokenTTL`-style declarations:
`defaultBulkMediaByteCap = 8388608`,
`defaultMediaTextInlineCapBytes = 1048576`, `defaultMediaMaxConcurrent = 2`,
and use them in both the `envInt*` call and the clamp.

### 2. `MEDIA_MAX_CONCURRENT < 0` normalises to 0

Add `c.MediaMaxConcurrent = 0` inside the existing negative branch, so the
struct field states the policy the gate enforces. This is a no-op for
`cmd/server/main.go` (`WithMediaConcurrency` already maps `n <= 0` to nil),
and it removes the trap for any future reader of the field — a startup log
line, a `get_media_gate` diagnostic, an admin surface — that would otherwise
print `-1` while the server runs unlimited.

### 3. Unexport and relocate the gate's label list

Rename `MediaGateTools` to `mediaGateTools` and move the declaration into the
label-list block at `internal/metrics/metrics.go:314-331`, extending that
block's comment to name it. Update the two in-package references (`New()`'s
pre-init loop, `TestNew_MediaGateRejectionsZeroBaseline`). Pure rename: no
metric, label or series changes.

### 4. Pin `mctl_media_inflight` by name

Append `"mctl_media_inflight"` and `"mctl_media_gate_rejections_total"` to
`expectedMetricNames`. Neither needs a "force the family into existence"
touch call in `TestNew_RegistersAllMetrics`: `MediaInflight` is a plain
`Gauge` (registered eagerly, not lazily like a `Vec` child), and
`MediaGateRejectionsTotal`'s children are materialised by `New()`'s pre-init
loop. That respects the deliberate comment at
`internal/metrics/metrics_test.go:75-82`: the touch list means "families this
test must force into existence", and adding a pre-created family to it would
mask the deletion of the pre-init.

### 5. Resolve the in-flight gauge independently of builder order

Keep `WithMediaConcurrency` as-is (it reads `s.Metrics` when metrics came
first) and make `WithMetrics` back-fill an already-installed gate:

```go
func (s *Server) WithMetrics(m *metrics.Registry) *Server {
    s.Metrics = m
    if s.mediaGate != nil && m != nil {
        s.mediaGate.inFlight = m.MediaInflight
    }
    return s
}
```

Both orders now end with the gauge wired, and the nil-metrics case is
unchanged. This is preferred over resolving the gauge lazily inside
`acquire` (see Alternatives): the builder options are startup-only, so the
assignment happens before any goroutine can call `acquire`, and the hot path
keeps its single nil check with no `*Server` back-pointer in the gate. The
doc comments on both options state the invariant: options are applied during
construction only, never while serving.

### 6. Carry the admission wait on the gate struct

Replace the mutable package var with a const default plus a struct field:

```go
const defaultMediaGateWait = 2 * time.Second

type mediaGate struct {
    slots    chan struct{}
    inFlight prometheus.Gauge
    wait     time.Duration // 0 means defaultMediaGateWait
}
```

`newMediaGate(n, inFlight)` keeps its signature and sets
`wait: defaultMediaGateWait`; `acquire` uses `g.wait`. Tests get a
`newMediaGateWithWait(n, inFlight, d)` constructor (or set `g.wait` before
starting goroutines) in place of the `withMediaGateWait` helper, which is
deleted along with the var. Each test then owns its own gate and its own
timeout: no shared mutable state, so no cross-test race and nothing to
document as a hazard. `get_media_gate_test.go:56`'s single
`withMediaGateWait` call becomes a per-gate wait on the gate it already
assigns at line 59.

This is the "pass the wait through the gate struct" branch the issue offers,
chosen over the "document the hazard" branch because a comment does not
survive `-race` on a future test, and the struct field costs one word per
gate — of which a server has exactly one.

### 7. Import grouping

Split `internal/mcp/media_gate_test.go`'s import block into stdlib and
third-party groups, matching `get_media_gate_test.go` and what
`goimports`/`golangci-lint` expect per `CLAUDE.md`'s conventions.

### 8. Runbook table

Update `docs/runbook.md`:

- `MEDIA_TEXT_INLINE_CAP_BYTES` row: a negative value is rejected and falls
  back to the 1 MiB default; only an explicit `0` restores pre-#705 inlining.
- `MEDIA_MAX_CONCURRENT` row: a negative value is normalised to `0`
  (unlimited), and `0` remains the documented-unsafe opt-in.
- `BULK_MEDIA_BYTE_CAP` row: reword the "unlike the other two knobs below"
  clause, which becomes wrong once negatives no longer differ between the
  rows — the remaining difference is that `0` is meaningful for the other two
  and not for this one.

## Alternatives

1. **Reject a negative media knob in `Load()` (fail closed).** Matches the
   `MCP_TOOL_FILTER` / `OAUTH_ACCESS_TOKEN_TTL` precedent and surfaces the
   operator's mistake instead of hiding it. Dropped because the issue
   explicitly asks to clamp to the default, and because refusing to boot on a
   knob whose safe value is already known would turn a typo in a gitops
   values file into an outage. Recorded as an open question for a later
   hardening pass that would convert all three together.

2. **Resolve the in-flight gauge lazily inside `acquire`** (gate holds a
   `*Server` or a `func() prometheus.Gauge`). Order-independent by
   construction, and the issue offers it as one of two options. Dropped: it
   adds an indirection to the hot path, gives the gate a back-pointer to the
   server purely for metrics, and would be read from the goroutines that call
   `acquire` — reintroducing exactly the shared-mutable-state shape that
   finding 7 is about. Back-filling in `WithMetrics` achieves the same result
   at construction time.

3. **Keep `mediaGateWait` a package var and document the hazard** (the
   issue's first branch for finding 7). Zero code churn. Dropped because the
   documented constraint is unenforceable: `go test` runs a package's tests
   in one process, `withMediaGateWait` mutates a var that live goroutines
   read, and the only thing keeping today's suite quiet is that no two such
   tests overlap yet.

4. **Add a `MEDIA_GATE_WAIT` env var while touching the wait.** Tempting once
   the duration is a struct field. Dropped as scope creep: #707 is a
   review-thread cleanup, and a new operator-visible knob needs its own
   runbook row, default rationale and config test.

## Platform impact

- **Migrations:** none. No schema, no stored data, no audit-chain change.
- **Backward compatibility:** no change for any valid configuration. The only
  behavioural differences are for previously-invalid input:
  `MEDIA_TEXT_INLINE_CAP_BYTES=<negative>` now resolves to `1048576` instead
  of `0`, and `Config.MediaMaxConcurrent` now reads `0` instead of the
  negative literal (with identical runtime behaviour). No metric, label or
  series name changes — `mctl_media_inflight` and
  `mctl_media_gate_rejections_total{tool}` keep their names, so the
  `mctlhq/mctl-gitops#1450` dashboards and the runbook's observation window
  are unaffected. `metrics.MediaGateTools` becomes unexported; `grep` shows
  no consumer outside `internal/metrics`, and the package is internal, so no
  external module can depend on it.
- **Resource impact:** nil. One extra `time.Duration` per `mediaGate` (one
  per server process) and one extra pointer assignment in `WithMetrics`.
- **Risks and mitigations:**
  - *A deployment currently relying on a negative
    `MEDIA_TEXT_INLINE_CAP_BYTES` to get always-inline base64.* Unlikely
    (the documented escape hatch is `0`), and the fix direction is the safe
    one. Mitigation: the reworded warning names `0` as the explicit opt-in,
    and the runbook row says so; a client that genuinely needs inlining sets
    `0`.
  - *Test-only refactor of the wait breaking an unrelated timing
    assertion.* `TestMediaGate_RefusesWhenFull` and
    `TestMediaGate_AcquireRespectsContextCancellation` compare elapsed time
    against the wait; both must compare against their own gate's `wait`
    rather than the deleted package var. Covered by T5.
  - *`WithMetrics` back-fill masking a real ordering bug elsewhere.* The
    back-fill is confined to `s.mediaGate.inFlight`; every other field
    `WithMetrics` affects is untouched. The new order-independence test
    asserts both orders explicitly rather than only the one
    `cmd/server/main.go` uses.
  - *Reviewer confusion about which #706 threads this closes.* Each task
    below maps one-to-one to a checkbox in issue #707, and commits should
    reference `refs #707`.
