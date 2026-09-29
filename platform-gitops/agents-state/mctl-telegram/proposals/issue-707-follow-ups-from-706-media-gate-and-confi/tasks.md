# Tasks: issue-707-follow-ups-from-706-media-gate-and-confi

Each numbered task closes one checkbox in issue #707. Tasks 1-8 are
independent of each other except where noted, so they can land as one PR with
one commit per finding (`fix:` for 1-2, `refactor:` for 3, 5, 6,
`test:` for 4, `style:`/`test:` for 7, `docs:` for 8) — conventional commits
per `CLAUDE.md`, all with `refs #707`.

- [ ] 1. In `internal/config/config.go` `Load()`, clamp a negative
  `MEDIA_TEXT_INLINE_CAP_BYTES` to the `1048576` default instead of `0`, and
  reword the `slog.Warn` to say the default was applied and that an explicit
  `0` is required for always-inline. Hoist the three #705 defaults to package
  consts (`defaultBulkMediaByteCap = 8388608`,
  `defaultMediaTextInlineCapBytes = 1048576`, `defaultMediaMaxConcurrent = 2`)
  and use them in both the `envInt*` call and the clamp. — DoD:
  `MEDIA_TEXT_INLINE_CAP_BYTES=-1` yields `MediaTextInlineCapBytes == 1048576`;
  `=0` still yields `0`; unset yields `1048576`; garbage yields `1048576`;
  `BulkMediaByteCap` handling unchanged.

- [ ] 2. In the same `Load()` block, set `c.MediaMaxConcurrent = 0` inside the
  existing `< 0` branch and update the warning to say "normalised to 0 (no
  gate)". Update the field doc at `internal/config/config.go:228-232` to state
  that a negative value is normalised. — DoD:
  `MEDIA_MAX_CONCURRENT=-1` yields `MediaMaxConcurrent == 0`; the server's
  enforced policy (via `WithMediaConcurrency`, `n <= 0` means no gate) is
  unchanged.

- [ ] 3. In `internal/metrics/metrics.go`, rename exported `MediaGateTools`
  (line 721) to `mediaGateTools` and move its declaration into the label-list
  `var` block at lines 314-331, extending that block's comment to name it
  alongside `claudeResultClasses`, `jobCostResults` and the `workContext*`
  lists. Update the pre-init loop (line 678) and the two references in
  `internal/metrics/metrics_test.go` (lines 554-557). — DoD: `grep -rn
  "MediaGateTools" .` returns nothing; `go build ./... && go vet ./...` clean;
  no metric, label or series name changed.

- [ ] 4. Add `"mctl_media_inflight"` and
  `"mctl_media_gate_rejections_total"` to `expectedMetricNames` in
  `internal/metrics/metrics_test.go` (lines 14-45). Do **not** add touch calls
  for them in `TestNew_RegistersAllMetrics` — `MediaInflight` is a plain
  `Gauge` and the rejection counter's children are pre-created by `New()`;
  adding touches would defeat the comment at lines 75-82. — DoD:
  `TestNew_RegistersAllMetrics` passes; deleting `r.MediaInflight` from the
  `MustRegister` call at line 658 makes it fail.

- [ ] 5. In `internal/mcp/server.go`, make `WithMetrics` back-fill an
  already-installed gate's gauge (`if s.mediaGate != nil && m != nil {
  s.mediaGate.inFlight = m.MediaInflight }`). Update the doc comments on both
  `WithMetrics` and `WithMediaConcurrency`: the gauge is wired in either
  order, and builder options are startup-only (never applied while serving).
  Simplify the now-stale ordering comment in `cmd/server/main.go:518-521` to
  note the order no longer matters. — DoD: gauge wired for both
  `WithMetrics().WithMediaConcurrency()` and
  `WithMediaConcurrency().WithMetrics()`; nil-metrics path still enforces the
  limit with no gauge.

- [ ] 6. In `internal/mcp/media_gate.go`, replace
  `var mediaGateWait = 2 * time.Second` with
  `const defaultMediaGateWait = 2 * time.Second` and add a `wait
  time.Duration` field to `mediaGate`, set by `newMediaGate` to
  `defaultMediaGateWait`; `acquire` reads `g.wait`. Add a test-facing
  `newMediaGateWithWait(n int, inFlight prometheus.Gauge, d time.Duration)`
  constructor. Delete the `withMediaGateWait` helper
  (`internal/mcp/media_gate_test.go:128-134`). Update the comment references
  to `mediaGateWait` in `internal/mcp/reasons.go:86` and
  `internal/metrics/metrics.go:204`. — DoD: no package-level mutable wait
  remains; production wait still 2s; `go test ./internal/mcp/... -race`
  passes.

- [ ] 7. (depends on 6) Fix `internal/mcp/media_gate_test.go`'s import block:
  stdlib group (`context`, `errors`, `sync`, `testing`, `time`) then a
  separate third-party group (`prometheus`, `prometheus/testutil`), matching
  `internal/mcp/get_media_gate_test.go:3-15`. Migrate the tests off the
  deleted helper: `TestMediaGate_RefusesWhenFull` and
  `TestMediaGate_AcquireRespectsContextCancellation` use
  `newMediaGateWithWait(1, nil, 50*time.Millisecond)` and compare elapsed time
  against their own `g.wait`; `TestMediaGate_ConcurrentAcquireReleaseStaysWithinCapacity`
  derives its per-goroutine context timeout from `g.wait`; and
  `internal/mcp/get_media_gate_test.go:56-59` uses the same constructor for
  the gate it assigns to `s.mediaGate`. — DoD: `gofmt -l internal/mcp` empty;
  `golangci-lint run` clean; all gate tests pass.

- [ ] 8. Update `docs/runbook.md`'s "Media response memory bounds (issue
  #705)" table (lines 2485-2487): state per row what a negative value
  resolves to; note that only an explicit `0` selects always-inline for
  `MEDIA_TEXT_INLINE_CAP_BYTES` or no-gate for `MEDIA_MAX_CONCURRENT`; and
  reword the `BULK_MEDIA_BYTE_CAP` row's "unlike the other two knobs below"
  clause so the remaining distinction is the meaning of `0`, not the handling
  of negatives. Leave the memory formula, the `send_media` / Local Bridge
  exception paragraphs and the mitigation ordering (lines 2519-2522)
  unchanged. — DoD: table describes actual `Load()` behaviour after tasks 1-2;
  `go test ./internal/mcp/ -run TestTroubleshootingDoc` (the
  `troubleshooting_doc_test.go` docs guard) still passes.

## Tests

- [ ] T1. Add a `{name: "negative falls back to the default", env:
  {"MEDIA_TEXT_INLINE_CAP_BYTES": "-1"}, want: 1048576}` row to
  `TestLoadMediaTextInlineCapBytes` (`internal/config/config_test.go:296`),
  replacing the existing `"negative is treated as zero"` row (line 305), and
  keep the `"zero means always inline"` row.
- [ ] T2. Add a `{name: "negative is normalised to zero", env:
  {"MEDIA_MAX_CONCURRENT": "-1"}, want: 0}` row to
  `TestLoadMediaMaxConcurrent` (`internal/config/config_test.go:326`) — the
  missing row the issue calls out.
- [ ] T3. `TestNew_RegistersAllMetrics` covers `mctl_media_inflight` by name
  (task 4). Add a `TestNew_MediaInflightStartsAtZero` asserting
  `testutil.ToFloat64(reg.MediaInflight) == 0` on a fresh registry, so the
  gauge the runbook sizes the pod from has a pinned starting value.
- [ ] T4. New `internal/mcp` test `TestWithMediaConcurrency`:
  table-driven over `n` — `n = 0` and `n = -1` leave `s.mediaGate == nil`
  (unlimited: `acquire` returns nil past any count); `n = 1` installs a gate
  that admits one holder and refuses the second with `errMediaBusy`;
  `n = 3` admits three. Plus `TestWithMediaConcurrency_GaugeWiredInEitherOrder`:
  build a `*Server` both ways (`WithMetrics` then `WithMediaConcurrency`, and
  the reverse) against a real `metrics.New()`, acquire one slot, and assert
  `testutil.ToFloat64(m.MediaInflight) == 1` in both cases, then `0` after
  release. A third case with no `*metrics.Registry` asserts the limit is still
  enforced and nothing panics.
- [ ] T5. Keep the existing gate tests green on the struct-carried wait:
  `TestMediaGate_NilIsUnlimited`, `TestMediaGate_RefusesWhenFull`,
  `TestMediaGate_ReleasesOnAllPaths`,
  `TestMediaGate_AcquireRespectsContextCancellation`,
  `TestMediaGate_ConcurrentAcquireReleaseStaysWithinCapacity`,
  `TestMediaGate_InFlightGaugeTracksHeldSlots`, and the `get_media` refusal
  tests in `internal/mcp/get_media_gate_test.go` (including the
  cancelled-caller case that must not increment
  `MediaGateRejectionsTotal`).
- [ ] T6. Add `TestMediaGate_DefaultWaitIsTwoSeconds`: `newMediaGate(1,
  nil).wait == defaultMediaGateWait` and `defaultMediaGateWait == 2 *
  time.Second`, so the production wait cannot drift while tests run with a
  shrunken one.
- [ ] T7. Run `go test ./... -race` and `go vet ./...`; confirm
  `gofmt -l .` is empty and `golangci-lint run` is clean. The race detector is
  the acceptance signal for task 6.

## Rollback

Every change is source-only: no migration, no stored data, no metric or
series rename, and no new env var. Rollback is `git revert` of the merge
commit (merge-commit strategy per `CLAUDE.md`) followed by a tag and the
normal release-please deploy.

Per-finding rollback, if only one change needs to go:

- Tasks 1-2 (config clamps): revert the `internal/config` commit. Operationally,
  a deployment that wants the old negative-means-zero behaviour sets
  `MEDIA_TEXT_INLINE_CAP_BYTES=0` explicitly — no code change needed, no
  redeploy of this repository.
- Task 5 (gauge back-fill): revert; `cmd/server/main.go` already calls
  `WithMetrics` before `WithMediaConcurrency`, so `mctl_media_inflight` keeps
  working in the deployed order either way.
- Tasks 3, 4, 6, 7 (unexport, test pins, struct-carried wait, imports): test
  and internal-symbol changes with no runtime surface; revert in isolation.
- Task 8 (runbook): revert the `docs/runbook.md` commit; docs-only.

There is no runtime kill switch to reach for, because no runtime behaviour is
added — the media gate itself remains disableable with
`MEDIA_MAX_CONCURRENT=0` exactly as #706 shipped it.
