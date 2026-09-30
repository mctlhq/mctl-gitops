# Design: issue-703-follow-ups-from-700-mcp-tool-call-failur

## Current state

Everything below was read in the clone at `d5d907c`.

### The recording path (`internal/mcp/record.go`)

`Server.recordToolCall` is registered in `newMCPServer` via
`mcpserver.WithToolHandlerMiddleware` (`internal/mcp/server.go:293-310`). It
installs a `*callRecorder` in `ctx` (`withRecorder`), calls the handler,
absorbs a returned Go error (`ReasonHandlerError`) or a recovered panic
(`ReasonPanic`) into an `IsError` result, and defers
`Server.flushRecordedCall`.

`Server.audit` (`internal/mcp/tools.go:2362-2389`) either stages a `callRecord`
into that recorder or, with no recorder in `ctx`, writes through via
`Server.writeAuditRow` (`tools.go:2398`), which calls
`Store.LogToolCall`, samples `ToolInvocationDuration` /
`ToolInvocationsTotal` when `rec.hasElapsed && !rec.exemptFromSLO`, and mirrors
the outcome to slog.

`flushRecordedCall` (`record.go:181-253`) applies five rules:

- Rule 1 — records staged + error: mutate the **last** staged record in place
  (`last.status = "error"`, `last.reason = …`).
- Rule 2 — no records + error: synthesize one error record with
  `exemptFromSLO: true`.
- Rule 3 — no records + success: synthesize one `"ok"` record unless the tool
  is in `auditExemptOnSuccess`; `exemptFromSLO` is **not** set.
- Rule 4 — write every record on a `context.WithoutCancel` +
  `auditWriteTimeout` context.
- Rule 5 — one `ToolCallErrorsTotal{tool, reason}` increment per erroring call,
  keyed by `req.Params.Name` and `records[len-1].reason`.

### Classification (`internal/mcp/reasons.go`)

`classifyReason(callPath, final)` returns `ReasonBridgeError` whenever
`callPath == "local"`, otherwise delegates to `classifyToolResultReason`, which
matches the user-visible error text against literal prefixes/substrings copied
from the handlers. Its buckets, in order: fixed literals → the
`mtprotoErrCatalog` prefix loop (`reasons.go:128-132`) → argument validation →
confirmation flow → Telegram-side literals → rate limit → policy refusals →
`"not found"` → `ReasonUnknown`.

The findings are visible directly in this code:

- `ReasonStoreError` (`reasons.go:52-54`) is declared and documented, and
  `grep -rn store_error` finds only the constant and one runbook mention. No
  path emits it: the ~30 store-failure sites in `tools.go` return
  `toolErr("<tool>: %v", err)`, whose text classifies as `unknown` (or
  accidentally as `not_found` when the driver's message contains "not found").
- `"confirmation_id required"` sits in the confirmation-flow switch's
  `ReasonNotFound` arm (`reasons.go:154-156`), next to `"confirmation_id not
  found, expired, or already used"`. It is emitted by
  `media_tools.go:194` as a **missing required argument**.
- `mtprotoErrResult` (`errorcatalog.go:167-174`) returns `nil` for any
  `tgerr.Error` in neither catalog, so `borrowErrResult`
  (`tools.go:2061-2072`) falls through to `toolErr("%s: %v", tool, err)` and
  the failure classifies as `unknown`.
- `jsonrpcHooks` uses a bare `err.(jsonrpcCoder)` assertion
  (`record.go:301`), so any wrapping logs `jsonrpc_code=0`.

### Recording-semantics findings

- `callPath == "local"` is set by the handler's `s.audit(..., "local")` call.
  It is over-broad in one direction —
  `get_unread_messages` with `fetch_media=true` audits `"local"` for a refusal
  the bridge never saw (`tools.go:280-286`), as does `get_messages`
  (`tools.go:549-555`) — and under-broad in the other: a bridge call that fails
  before any `s.audit` (Rule 2) has `callPath == ""` and is classified from
  text.
- `send_message` audits `send_message:sent` with `err == nil` immediately after
  a real Telegram send (`tools.go:474`) and only then calls `jsonResult`. A
  marshal failure makes the final result `IsError`, and Rule 1 rewrites that
  row to `status="error"` — the audit log then denies a send that happened.
- Rule 3's synthesized success record is not `exemptFromSLO`, so it adds an
  `ok` sample to `ToolInvocationsTotal`, which is exactly the SLO denominator
  in `deploy/alerts/mctl-telegram.rules.yaml:513-556`.
- The exemption is reason-blind: a `panic` or `handler_error` that reaches Rule
  2 is excluded from the SLO pair, and no alert rule watches
  `mctl_tool_call_errors_total` at all.
- `labelTool` (`record.go:335-338`) collapses the tool label to
  `"unregistered"` only for `ReasonToolNotFound` / `ReasonUnparsableMessage` —
  a denylist. `capability_disabled` and `jsonrpc_error` still pass the
  client-supplied `req.Params.Name` into a Prometheus label.

### API / docs / tests

- `Store.LogToolCall(ctx, userID int64, tool, peerRedacted, status, errMsg,
  callPath, reason string)` (`internal/db/store.go:1752`) — six consecutive
  bare strings. **Corrected in review:** 33 lines across 12 non-test files
  (`internal/oauth` alone has 24), not ~25 sites; see #716. Original text:
  ~25 call sites in repo (`internal/mcp/tools.go:2403`,
  `internal/agentapi/json.go:75`, `internal/agentapi/profilehandler.go:182,201`,
  plus `internal/db` tests).
- `docs/runbook.md:1468-1512` documents the reason breakdown and the
  `increase()` caveat, but never states that the two metric families
  deliberately disagree, nor Rule 2's row volume.
- `internal/mcp/record_test.go:155-166` says the Rule 2 record "never had an
  elapsed duration to begin with" — false: `record.go:213-215` sets `elapsed`
  and `hasElapsed = true`. The gate is `exemptFromSLO`.
  `histogramSampleCount`'s doc says it sums "across every other label value
  (e.g. outcome)", but `ToolInvocationDuration` has exactly one label, `tool`
  (`internal/metrics/metrics.go:434-438`).

## Proposed solution

One new mechanism plus a set of local corrections. Nothing changes the
`Reason*` value set, the audit hash chain, or the middleware topology.

### 1. An explicit reason hint, staged where the failure is known

`classifyToolResultReason` guesses a reason from prose the handler wrote for a
human. That is the root cause of four findings (`store_error` unreachable,
`confirmation_id required`, unenumerated MTProto texts, and the `callPath ==
"local"` shortcut). Rather than adding more string literals, give the failing
code path a way to say what it is.

Add to `internal/mcp/record.go`:

```go
// hint is the reason the failing code path named for itself. It always wins
// over classifyToolResultReason, which stays as the fallback for every path
// that names nothing.
func hintReason(ctx context.Context, reason string)   // stages onto *callRecorder
```

`callRecorder` gains a `hint string` field (last writer wins, guarded by the
existing mutex); with no recorder in `ctx` it is a no-op, exactly like
`Server.audit`'s write-through branch, so direct-handler tests are unchanged.

New precedence in `flushRecordedCall`:

1. `explicitReason` (`panic`, `handler_error`) — unchanged, the wrapper knows
   with certainty.
2. `rec.hint` — the failing path named itself.
3. `classifyReason(callPath, final)` — today's behaviour, unchanged.

Hints are emitted at four kinds of site, all small edits:

- `borrowErrResult` (`tools.go:2061`) and the friendly session-error /
  `ErrPoolFull` branches → `ReasonTelegramError`. This makes every MTProto
  failure — enumerated or not — classify correctly and reduces the
  `mtprotoErrCatalog` prefix loop to a fallback for direct
  `mtprotoErrResult` callers. **Note:** `borrowErrResult` is a free function;
  it gains a leading `ctx context.Context` parameter (all call sites are in
  this package and already hold a `ctx`).
- `bridgeCall`'s failure returns and each `bridgeResultErr` audit site →
  `ReasonBridgeError`, emitted **only** where the call actually reached the
  bridge. `classifyReason`'s `callPath == "local"` shortcut is then deleted,
  and `classifyReason` collapses to `classifyToolResultReason`. The
  local-mode refusals in `tools.go:280-286` / `tools.go:549-555` /
  `media_tools.go` hint `ReasonModeUnsupported` instead, and their
  `s.audit(..., "local")` calls keep `call_path="local"` for the audit row (it
  remains a true statement about routing) without steering classification.
- The ~30 `toolErr("<tool>: %v", err)` store-failure sites in `tools.go`,
  `media_tools.go` and `broadcast_tools.go` → `ReasonStoreError`, via a new
  helper `func (s *Server) storeErr(ctx context.Context, tool string, err
  error) *mcplib.CallToolResult` that hints and formats in one call. This is
  what makes `ReasonStoreError` reachable rather than deleted; the issue offers
  both, and emitting it is the option that preserves the diagnostic the
  constant was written for.
- `"confirmation_id required"`: moved out of the `ReasonNotFound` arm into the
  argument-validation switch in `classifyToolResultReason`, and additionally
  hinted `ReasonInvalidArgument` at the two handler sites. Both, because the
  text classifier remains the fallback for any path that forgets to hint.

### 2. Rule 1 never rewrites a staged success

Split Rule 1 by the last staged record's status:

- `last.status == "error"` → reconcile in place, exactly as today.
- `last.status == "ok"` → leave it untouched and **append** a new record
  (`tool: req.Params.Name`, `status: "error"`, reason from the precedence chain
  above, `errMsg: firstResultText(final)`, `id: auth.From(ctx)`, elapsed from
  `startedAt`, `synthesized: true`).

This is a total rule with no per-tool allowlist to maintain: a completed
destructive action (`send_message:sent`, `send_media:sent`,
`*:via-bridge`) keeps its `ok` row, and the later encode failure becomes its
own visible row. The encode-after-ok case that Rule 1 was written for
(`TestFlushRecordedCall_ReconcilesEncodeFailureAfterOKAudit`) still surfaces
the failure — as a second row instead of a rewrite, which is the assertion that
has to change. Rule 5 is unaffected: it still keys off `records[len-1].reason`,
which is now the appended record.

### 3. `exemptFromSLO` → `synthesized`

> **AMENDED (human review, 2026-10-01):** the server-fault predicate below is NOT implemented.
> `feedsSLO` is `return !r.synthesized`, so no synthesized record feeds the SLO
> pair, and `serverFaultReason` is not added (it would be dead code). The
> availability SLO input set stays pre-#696. Server faults are caught by the
> `MctlToolHandlerFaults` alert (section 4) instead. The original text is kept
> below for the record.

Rename the `callRecord` field to `synthesized` and set it on **every** record
`flushRecordedCall` creates (Rule 1's appended record, Rule 2, Rule 3). The
invariant becomes total and self-describing: staged by `Server.audit` ⇒ not
synthesized.

`writeAuditRow` gates the SLO pair on a new method:

```go
// feedsSLO reports whether this record may sample the two series the
// tool-availability SLO reads. Records staged by Server.audit always do
// (pre-#696 behaviour, unchanged). A synthesized record does only when it
// records a server fault: a panic, a handler-returned error, a store failure
// or a response-encoding failure are ours, and hiding them from the SLO is
// how a real outage stays quiet. Client-fault rejections stay out, so a
// looping bad client cannot page on-call.
func (r callRecord) feedsSLO() bool {
    return !r.synthesized || serverFaultReason(r.reason)
}
```

`serverFaultReason` is a small `map[string]bool` over `ReasonPanic`,
`ReasonHandlerError`, `ReasonStoreError`, `ReasonEncodeFailed`, kept next to
the `Reason*` block so a new reason is classified when it is added.

A Rule 3 success record is synthesized with an empty reason, so it never feeds
the pair — the second half of the invariant the issue calls out.

### 4. A dedicated handler-fault alert

> **AMENDED (human review, 2026-10-01):** this alert is now the only mechanism that surfaces server
> faults. Its scope stays `panic|handler_error`. `store_error` and
> `encode_failed` remain visible in `mctl_tool_call_errors_total{reason}` and on
> the dashboard, but they are not alerted in #703, and the runbook section must
> say so explicitly.

Add to `deploy/alerts/mctl-telegram.rules.yaml`, in the
`mctl-telegram-tool-availability` group:

```yaml
- alert: MctlToolHandlerFaults
  expr: sum by (tool, reason) (rate(mctl_tool_call_errors_total{reason=~"panic|handler_error"}[15m])) > 0
  for: 5m
  labels: {severity: warning, service: mctl-telegram}
  annotations:
    summary: "mctl-telegram MCP tool handler fault ({{ $labels.reason }} on {{ $labels.tool }})"
    runbook_url: "https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbook.md#mctltoolhandlerfaults"
```

with a matching `<a id="mctltoolhandlerfaults"></a>` runbook section (required
by `deploy/alerts/runbook_links_test.go`) and a silence/firing pair in
`deploy/alerts/mctl-telegram.rules_test.yaml`, matching that file's stated
convention that the pair is the point.

### 5. Allowlist the JSON-RPC hook's tool label

`newMCPServer` already has the authoritative set: `srv.ListTools()` is what
`descriptors.go:30` and `portal_allowlist_test.go:279` use. The hook is built
before the server exists, so pass it a late-bound holder:

```go
var registered atomic.Pointer[map[string]struct{}]
opts := []mcpserver.ServerOption{ …, mcpserver.WithHooks(s.jsonrpcHooks(&registered)) }
srv := mcpserver.NewMCPServer(…)
// … every addTool/addToolUI call …
names := make(map[string]struct{}, …) // from srv.ListTools()
registered.Store(&names)
```

`labelTool` becomes: emit `toolName` only when it is present in the loaded set;
otherwise `"unregistered"`. A nil pointer (hook fired before the set was
stored, which serving order makes impossible but construction order allows)
yields `"unregistered"` — fail closed on cardinality. This covers
`capability_disabled` and `jsonrpc_error` as well as the two reasons the
denylist already handled, and a tool excluded by `ToolFilter` correctly reads
as unregistered, matching `ErrToolNotFound`'s own semantics. The verbatim name
stays in the `mcp jsonrpc error` slog line.

### 6. `errors.As` for the JSON-RPC code

```go
var coder jsonrpcCoder
if errors.As(err, &coder) { code = coder.ToJSONRPCError().Error.Code }
```

`errors.As` accepts an interface target, so the local `jsonrpcCoder` interface
is unchanged.

### 7. `db.ToolCall` params struct

> **WITHDRAWN (human review, 2026-10-01):** moved to mctlhq/mctl-telegram#716 (33 lines across 12
> non-test files, mostly OAuth / connect flows). Nothing in this section is
> implemented under #703.

```go
// ToolCall is one audit row's payload. A struct rather than positional
// arguments: the previous signature ended in six consecutive bare strings,
// where transposing status and errMsg still compiled.
type ToolCall struct {
    UserID       int64
    Tool         string
    PeerRedacted string
    Status       string
    ErrMsg       string
    CallPath     string
    Reason       string
}

func (s *Store) LogToolCall(ctx context.Context, call ToolCall)
```

The body is unchanged; only the parameter shape moves. All call sites
(`internal/mcp/tools.go:2403`, `internal/agentapi/json.go:75`,
`internal/agentapi/profilehandler.go:182,201`, and the `internal/db` tests) are
migrated in the same commit. `Store` is an `internal/` type, so there is no
external compatibility surface and no deprecated wrapper is kept — one
signature, one spelling.

### 8. Docs and test-comment corrections

`docs/runbook.md`, in the `#### Tool-call error breakdown (mctl-telegram#696)`
section:

- A "**Why the two families disagree**" paragraph: `mctl_tool_call_errors_total`
  counts every `tools/call` failure including client faults and the JSON-RPC
  rejections that never resolve a handler;
  `mctl_tool_invocations_total{status="error"}` counts only what the
  availability SLO is allowed to burn budget on. The reason-error counter is
  therefore expected to run **higher** than the SLO numerator, permanently, and
  a difference is not a lost sample.
- A "**Row volume**" paragraph for Rule 2: every client-fault rejection is a
  hash-chained `audit_logs` write (`Store.LogToolCall`), bounded per identity
  by `RATE_LIMIT_PER_USER` (default 30/min → ≤1800 rows/hour/identity), each
  serializing on that user's chain lock (`SELECT … FOR UPDATE` on Postgres,
  `BEGIN IMMEDIATE` on SQLite); a client looping on a scope error therefore
  costs write throughput on that user's chain and audit-table growth until
  `AUDIT_RETENTION_DAYS` sweeps it.
- The new `MctlToolHandlerFaults` section with its explicit anchor.

`internal/mcp/record_test.go`: the comment at ~line 159 names `synthesized`
(**AMENDED:** not `serverFaultReason`, which is not added; the test must assert
that a **panic** record does NOT feed the pair, and that is the mutation-checked
assertion);
`histogramSampleCount`'s doc line drops the non-existent "outcome" label.

## Alternatives

1. **Delete `ReasonStoreError` instead of emitting it.** The issue explicitly
   allows this and it is a two-line change. Dropped: the ~30 store-failure
   sites are real and currently land in `unknown`, which is the bucket the
   taxonomy exists to shrink. Deleting the constant would make the metric
   permanently unable to distinguish "the database is failing" from "we do not
   know", which is exactly the distinction an on-call engineer needs first.

2. **Keep classifying from text and just add more literals** (more
   `mtprotoErrCatalog` entries, a `"confirmation_id required"` arm, a broader
   `store` substring match). Dropped: it scales linearly with handler prose,
   and #700's own review found three misclassifications in one pass. The hint
   channel makes the common paths authoritative while leaving the classifier
   as the honest fallback for handlers that name nothing — which is also why
   the classifier is *kept*, not replaced.

3. **A per-tool `completedAction` allowlist to protect Rule 1's staged `ok`
   row** (e.g. `send_message:sent`, `send_media:sent`, `*:via-bridge`).
   Dropped: it is a denylist-by-omission of exactly the kind the issue objects
   to in `labelTool` — a destructive tool added later would silently regain the
   rewrite bug. Never rewriting a staged `ok` is total and needs no
   maintenance.

4. **Close the SLO blind spot with the new alert alone, leaving the SLO input
   set byte-identical to pre-#696.** **ADOPTED in review (2026-10-01)** as the
   design of record; the text below is the original rationale for dropping it. The lowest-risk option, and the fallback
   if burn-rate noise appears. Dropped as the primary because the issue objects
   to `panic`/`handler_error` *leaving the SLO*, and a fault the availability
   SLO ignores is a fault the error budget says never happened. Reverting is
   one line in `feedsSLO`.

## Platform impact

- **Migrations:** none. No schema change, no `audit_logs` backfill, `reason`
  stays out of `hashAuditEntry` (`internal/db/audit_chain.go`), so
  `VerifyAuditChain` is unaffected.
- **Backward compatibility:** (AMENDED: `Store.LogToolCall`'s signature does NOT change under #703; see #716.) Original: `Store.LogToolCall`'s signature changes, but
  `internal/db` is an internal package with all call sites in this repo. No MCP
  tool descriptor, output schema, or error text a client sees changes —
  `docs/tool-descriptors.json` and `portal_allowlist_test.go` snapshots must
  therefore be byte-identical after the change, which is itself a test.
- **AMENDED (human review, 2026-10-01):** with `feedsSLO = !synthesized`, the SLO pair loses only
  Rule 3's synthesized `ok` samples added by #696 and returns to its pre-#696
  input set. It gains nothing. The paragraph below describes the original
  proposal and no longer applies.
- **Metric / alert impact (the main risk).** `feedsSLO` adds a small number of
  server-fault errors to the `mctl_tool_invocations_total` numerator, and
  removes Rule 3's `ok` samples from the denominator. Both push the measured
  error rate *up* slightly. Mitigation: the affected reasons (`panic`,
  `handler_error`, `store_error`, `encode_failed`) are rare by construction —
  if they are not, the alert firing is the correct outcome. Rule 3's `ok`
  removal is bounded by the tools that never audit their own success; validate
  the before/after denominator on the Grafana board
  (`deploy/grafana/mctl-telegram-beta.json`) for one 24h window post-deploy,
  and revert `feedsSLO` to `!r.synthesized` if fast-burn noise appears.
- **Cardinality:** strictly reduced. The allowlist removes the last path by
  which a client-supplied string reaches a Prometheus label. Existing series
  created by that hole (if any) age out of the TSDB normally.
- **Row volume:** Rule 1's append adds at most one extra `audit_logs` row per
  *failing call that had already staged a success* — today a rare encode-failure
  path. No change to steady-state volume.
- **Risks + mitigations:**
  - *A hint is emitted on a path whose failure later takes a different
    branch.* Mitigated by last-writer-wins plus the precedence order:
    `explicitReason` (panic/handler_error) still outranks any hint, so the
    wrapper's certain knowledge cannot be overridden.
  - *`srv.ListTools()` called from inside a hook.* Called once behind the
    `atomic.Pointer`, populated at construction before serving; the hook only
    reads the loaded map.
  - *`borrowErrResult` gaining a `ctx` parameter touches many call sites.*
    Mechanical and compiler-enforced; `go build ./...` is the check.
  - *Behaviour drift in the 632-line `record_test.go`.* Two assertions change
    deliberately (encode-after-ok row count; **AMENDED:** the panic-feeds-SLO
    assertion is dropped, a panic still feeds nothing); every
    other test must pass unchanged, which is the review signal that the rest of
    #700's contract is intact.
