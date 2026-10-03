# Media gate and config polish follow-ups from #706

## Context

Issue #705 bounded media response memory in `mctl-telegram` after a
`get_messages` call with `fetch_media=true` OOM-killed the pod at its 256Mi
limit. PR #706 shipped that work: three new env vars
(`BULK_MEDIA_BYTE_CAP`, `MEDIA_TEXT_INLINE_CAP_BYTES`,
`MEDIA_MAX_CONCURRENT`), a counting-semaphore admission gate
(`internal/mcp/media_gate.go`), two Prometheus series
(`mctl_media_inflight`, `mctl_media_gate_rejections_total{tool}`), and a
runbook section. The PR was approved with zero P1/P2 findings; issue #707
collects the seven P3 findings from the final review round so the review
threads can be closed without another round.

The findings are small but not cosmetic. One is a latent safety inversion:
`MEDIA_TEXT_INLINE_CAP_BYTES=-1` is clamped to `0`, which means "always
inline base64 in both the text block and `structuredContent`" — the exact
pre-#705 memory behaviour the issue existed to remove — while the sibling
`BULK_MEDIA_BYTE_CAP` clamps a bad value to its safe default. A typo or a
templating accident in a gitops values file therefore re-arms the OOM
instead of being corrected. The rest are coverage and hygiene gaps that make
the gate harder to keep correct: an untested builder option whose gauge
wiring is silently order-dependent on `WithMetrics`, an unpinned metric
family, an exported symbol with no external consumer, misplaced imports, and
a mutable package-level timeout read by goroutines from `acquire`.

## User stories

- AS an operator I WANT a malformed `MEDIA_TEXT_INLINE_CAP_BYTES` to fall
  back to the safe 1 MiB default SO THAT a config typo cannot silently
  restore the pre-#705 dual-encoded memory cost.
- AS an operator I WANT `Config.MediaMaxConcurrent` to hold the value the
  server actually enforces SO THAT startup logs and any future consumer of
  the field agree with the running gate.
- AS an operator I WANT the runbook table to state what a negative value of
  each media knob does SO THAT I can reason about a misconfiguration without
  reading `internal/config/config.go`.
- AS a maintainer I WANT `mctl_media_inflight` pinned by a registration test
  SO THAT the series the runbook sizes the pod limit from cannot be dropped
  unnoticed.
- AS a maintainer I WANT `WithMediaConcurrency` covered by tests and its
  in-flight gauge wired regardless of builder call order SO THAT reordering
  the chain in `cmd/server/main.go` cannot silently disable the gauge.
- AS a maintainer I WANT the gate's wait timeout carried on the gate struct
  SO THAT a test shrinking it cannot race goroutines still running from
  another test.

## Acceptance criteria (EARS)

Config

- IF `MEDIA_TEXT_INLINE_CAP_BYTES` parses to a negative value THEN THE
  SYSTEM SHALL log a warning and set `Config.MediaTextInlineCapBytes` to the
  `1048576` default, not to `0`.
- WHEN `MEDIA_TEXT_INLINE_CAP_BYTES` is explicitly `0` THE SYSTEM SHALL keep
  `0` (the documented "always inline" escape hatch for a text-only client).
- IF `MEDIA_MAX_CONCURRENT` parses to a negative value THEN THE SYSTEM SHALL
  log a warning and normalise `Config.MediaMaxConcurrent` to `0`
  (the existing "unlimited, no gate" meaning), so the field matches what
  `WithMediaConcurrency` enforces.
- WHEN `MEDIA_MAX_CONCURRENT` or `MEDIA_TEXT_INLINE_CAP_BYTES` is unset,
  valid, garbage, or zero THE SYSTEM SHALL resolve exactly as it does today
  (`2` / `1048576` defaults, garbage falls back to default, `0` preserved).
- WHILE `BULK_MEDIA_BYTE_CAP` handling is unchanged THE SYSTEM SHALL keep
  clamping `<= 0` to the `8388608` default.
- WHEN the runbook's media-knob table is read THE SYSTEM SHALL document, per
  knob, what a negative value resolves to, and SHALL state that only an
  explicit `0` selects the unsafe/unbounded meaning for
  `MEDIA_TEXT_INLINE_CAP_BYTES` and `MEDIA_MAX_CONCURRENT`.

Metrics and wiring

- WHILE no code outside `internal/metrics` consumes the media gate's label
  list THE SYSTEM SHALL keep that list unexported and declared next to the
  other pre-init label-value lists (`claudeResultClasses`, `jobCostResults`,
  `workContextRoutes` and friends) in `internal/metrics/metrics.go`.
- WHEN `metrics.New()` is called THE SYSTEM SHALL register a
  `mctl_media_inflight` family that a registration test asserts on by name,
  alongside `mctl_media_gate_rejections_total`.
- WHEN `WithMediaConcurrency(n)` is called with `n > 0` THE SYSTEM SHALL
  install a gate with `n` slots; WHEN called with `n <= 0` it SHALL leave
  `Server.mediaGate` nil (unlimited).
- WHEN `WithMediaConcurrency` and `WithMetrics` are both called, in either
  order, THE SYSTEM SHALL connect the gate's in-flight gauge to the wired
  `*metrics.Registry`.
- WHILE no `*metrics.Registry` is wired at all THE SYSTEM SHALL still
  enforce the concurrency limit and report no gauge (nil-safe, as today).

Tests and hygiene

- WHEN `internal/mcp/media_gate_test.go` is formatted THE SYSTEM SHALL carry
  the `prometheus` and `prometheus/testutil` imports in a third-party import
  group separate from the stdlib group, matching
  `internal/mcp/get_media_gate_test.go`.
- WHILE the gate's admission wait is configurable for tests THE SYSTEM SHALL
  carry it on the `mediaGate` struct rather than as a mutable package var
  read by `acquire`, so two tests cannot race over it.
- WHEN `go test ./... -race` runs THE SYSTEM SHALL pass with no data race
  reported on the gate's wait duration.
- WHILE this proposal is implemented THE SYSTEM SHALL preserve the
  externally observable gate behaviour: default 2s wait, `errMediaBusy`
  ("media downloads are at capacity - retry shortly") on timeout, ctx error
  on cancellation, `ReasonMediaCapacity` classification, and the existing
  rejection-counter semantics in `mediaGateRefused`.

## Out of scope

- Changing the default values of `BULK_MEDIA_BYTE_CAP`,
  `MEDIA_TEXT_INLINE_CAP_BYTES` or `MEDIA_MAX_CONCURRENT`.
- Changing the 2s admission wait, or making it operator-configurable via a
  new env var.
- Extending the gate to `send_media` uploads or to the Local Bridge
  `get_media` relay path (both documented gaps in `docs/runbook.md`; they are
  separate design decisions, not #706 review follow-ups).
- Lowering the `mctlhq/mctl-gitops#1450` pod memory limit / `GOMEMLIMIT`
  stopgap — the runbook makes that a separate gitops PR after a week of
  observed `mctl_media_inflight` data.
- Rejecting a negative media knob outright (returning an error from `Load`)
  rather than clamping. See Open questions.
- Any change to `Server.MediaTextInlineCapBytes`'s zero-value meaning
  ("always inline") for a `*Server` built without the config plumbing — that
  is what every existing `internal/mcp` test relies on.

## Open questions

- Clamp vs. reject for a negative media knob. `internal/config/config.go`
  rejects some invalid values outright (`MCP_TOOL_FILTER`,
  `OAUTH_ACCESS_TOKEN_TTL`) and clamps others (`BULK_MEDIA_BYTE_CAP`). The
  issue says "clamp to the default instead", so this proposal clamps and
  warns, matching the sibling knob; a later hardening pass could make all
  three fail closed together.
- Whether `mctl_media_gate_rejections_total` should also be added to
  `expectedMetricNames` in `internal/metrics/metrics_test.go`. The issue only
  names `mctl_media_inflight`; this proposal adds both, since the family is
  pre-initialised by `New()` and so appears in `Gather()` without being
  touched, exactly like the agent families already listed there.
- Whether to keep a package-level default wait constant once the duration
  moves onto the struct. This proposal keeps `defaultMediaGateWait` as an
  untouched `const` so the production value stays declared in one place and
  the mutable var disappears.
