# Tasks: issue-617-feat-audit-measure-what-reaches-tg-mctl

The five correlation fields, the DB columns, the hash block, both audit tools
and the runbook section already exist (see design.md, "Current state"). These
tasks close the three #617 acceptance items that remain: durable evidence, the
trace leg, and the worked example.

- [ ] 1. Add the shape-only header survey to `internal/edgectx`. New
      `HeaderShape` type and `func Survey(r *http.Request) []HeaderShape`:
      sorted header names as received; `Authorization`, `Cookie`,
      `Proxy-Authorization`, `Set-Cookie` recorded as name + `Secret: true`
      only; everything else recorded as byte length, character class
      (`hex`/`ascii`/`opaque`/`empty`) and the first 8 hex chars of
      SHA-256(value + per-process random salt).
      DoD: `go test ./internal/edgectx/` passes; no code path can return a raw
      header value; `FromRequest` is unchanged.

- [ ] 2. Gate the survey behind config and emit it (depends on 1). Add
      `EDGE_HEADER_SURVEY` (bool, default false) to `internal/config/config.go`
      and `.env.example`; in `internal/mcp.httpContext`, when enabled, emit one
      `slog.Info("edge header survey", ...)` per request through a
      `golang.org/x/time/rate` token bucket (a few records per minute), using
      `internal/audit/ratelimit.go` as the in-repo precedent. Add the
      "deliberately not redacted, and why" comment to
      `internal/audit/redact.go` next to the existing `device_pubkey` /
      `cost_usd` rationale.
      DoD: with the flag unset, `httpContext` behaves exactly as today and
      emits nothing; with it set, one bounded record per request appears.

- [ ] 3. Write `docs/reports/edge-headers-617.md` (depends on 2). Full observed
      inbound header table for BOTH routes (Portal `mcp.mctl.ai` →
      `tg.mctl.ai`, and direct `tg.mctl.ai/mcp`), exact names as received,
      dated; at least three repeated Portal calls so a per-request identifier
      is distinguishable from a constant; a per-candidate verdict table
      (`arrives` / `does not arrive` / `arrives but is not stable` /
      `not measured (reason)`) covering `Cf-Ray`, `CF-Connecting-IP`,
      `Cf-Worker`, `traceparent`, `tracestate`, `Mcp-Method`, `Mcp-Name`,
      `MCP-Protocol-Version` and everything else observed; an explicit scope
      statement (this route, this date, no extrapolation to Gateway logs or
      other zones); and the open `not measured` row for whether Cloudflare
      strips a client-supplied `Cf-Worker`. Follow the evidence discipline of
      `docs/cloudflare-portal-compat.md` — an unrun cell says
      `PENDING-OPERATOR`, never `PASS`.
      DoD: the document answers, for a reader who was not present, every
      candidate #617 names; the `traceparent` verdict is recorded, because
      task 5 depends on knowing it.

- [ ] 4. Add `internal/tracing`. Single entry point
      `Init(ctx, Config) (shutdown func(context.Context) error, error)`.
      Promote `go.opentelemetry.io/otel` and `otel/trace` from indirect to
      direct in `go.mod`; add `otel/sdk` and
      `exporters/otlp/otlptrace/otlptracehttp`. Empty OTLP endpoint installs
      nothing (global no-op tracer, no goroutine, no exporter). Non-empty
      endpoint builds a `TracerProvider` with a batch processor, a parent-based
      sampler over a configurable ratio (default 1.0), a resource with
      `service.name=mctl-telegram` and the build version, and sets the global
      propagator to `propagation.TraceContext{}`. Add `OTEL_EXPORTER_OTLP_
      ENDPOINT` and `OTEL_TRACES_SAMPLER_RATIO` to `internal/config/config.go`
      and `.env.example`.
      DoD: `go build ./...` and `go vet ./...` clean; with no endpoint set the
      binary starts, serves and shuts down exactly as before.

- [ ] 5. Start the span and carry its id (depends on 4). Add
      `tracing.Middleware()` in `cmd/server/main.go` between
      `limiter.Middleware()` and `mcpSrv.HTTPHandler()` (inside auth, so the
      401 path is untraced); extract the inbound W3C context with the global
      propagator so a forwarded `traceparent` is continued; name the span
      `MCP <Mcp-Method>` when present. Add `TraceID` / `SpanID` string fields
      to `edgectx.Context`, filled in `internal/mcp.httpContext` from
      `trace.SpanContextFromContext(r.Context())` only when the span context is
      valid AND sampled. Call `tracing.Init` in `main` next to the metrics
      registry and defer `shutdown`.
      DoD: a request with an inbound `traceparent` produces a span whose trace
      id matches it; a request without one produces a fresh trace; with tracing
      disabled `edgectx.Context.TraceID` stays empty.

- [ ] 6. Set the span attributes (depends on 5). In
      `internal/mcp.Server.audit` (`internal/mcp/tools.go:2190`), after the
      existing slog block, set on `trace.SpanFromContext(ctx)` when it is
      recording: `mctl.tool.name`, `mctl.tool.status`, `mctl.user.id`,
      `mctl.edge.request_id`, `mctl.edge.route`, `mcp.method`, `mcp.name`,
      `mcp.protocol_version`, skipping empty values on the same rule the slog
      block already applies. Source every value from the existing
      `edgectx.From(ctx)` call — no second capture.
      DoD: no raw tool arguments, peers, handles or message bodies reach a
      span; `auditDetached` still records attributes (the span survives
      `context.WithoutCancel`).

- [ ] 7. Persist `trace_id` on the audit row (depends on 5). Extend the
      existing column loop in `internal/db/db.go:145` with `trace_id`
      (nullable `TEXT`, no DEFAULT) and add the partial index
      `idx_audit_logs_trace_id ... WHERE trace_id IS NOT NULL`. In
      `internal/db/audit_chain.go`, add `TraceID` to `auditEdge` and write it
      under a NEW `auditTraceMarker = 0x02` block appended after the existing
      `0x01` block, only when non-empty. In `internal/db/store.go`, read
      `ec.TraceID` in `LogToolCall`, insert via `nullable`, add
      `TraceID string \`json:"trace_id,omitempty"\`` to `AuditEntry`, and
      select/scan it in `ListAuditFor` and `VerifyAuditChain`.
      DoD: hashes of every pre-existing row are byte-identical; a fresh
      correlated row round-trips its trace id.

- [ ] 8. Document the new field on both audit tools (depends on 7). Update the
      `WithDescription` text of `toolGetMyAuditLog` (`internal/mcp/tools.go:998`)
      and `toolGetUserAuditLog` (`internal/mcp/tools.go:1499`) to mention
      `trace_id`, keeping the admin tool's "EVIDENCE, NOT AS IDENTITY"
      warning. Confirm the reflected output schema stays open to additive
      fields (`internal/mcp/output_schema.go`), and update
      `docs/portal-allowlist.json` if the allowlist test demands it.
      DoD: `TestAuditToolDescriptions_DocumentEveryReturnedField`,
      `TestToolOutputSchemas`, `TestOutputSchemasStayOpenToAdditiveFields` and
      `TestPortalAllowlist...` all pass.

- [ ] 9. Add the route counter (depends on nothing else). New
      `mcp_tool_calls_by_route_total{route}` in `internal/metrics/metrics.go`
      with `route` in `{portal, direct, none}`, registered in `New()` and
      incremented in `Server.audit`. Do not add `edge_route` as a label to
      `ToolInvocationsTotal`.
      DoD: the metric appears on `/metrics` with at most three series; existing
      metric names and labels are untouched.

- [ ] 10. Write `docs/reports/correlation-example-617.md` (depends on 3, 6, 7,
      9). One read-only tool call by one user through `mcp.mctl.ai`, shown as
      (1) Portal/Access evidence, (2) the `get_my_audit_log` JSON entry,
      (3) the span with its attributes; join keys named explicitly (`trace_id`
      deterministic audit→trace, `edge_request_id` audit→Portal evidence);
      the caveats restated (a ray is per request, one Portal tool call is more
      than one upstream request, `Cf-Ray` arrives on both routes); and the
      direct-route call shown alongside as the bypass signature for
      `mctl-telegram#616`. No message content anywhere. Link it from
      `docs/runbook.md`'s "Following one call across the layers" section.
      DoD: `go test ./docs/` (runbook anchors) and
      `deploy/alerts/runbook_links_test.go` pass; the example uses synthetic
      identifiers only, per AGENTS.md.

- [ ] 11. Post the Slice 1 table and the worked example as comments on
      `mctlhq/mctl-telegram#617` and link the example from
      `mctlhq/.github#35` as the "cross-layer trace/audit correlation example"
      deliverable (depends on 3, 10). No code dependency.
      DoD: both comments exist and quote the committed documents; #617's
      Slice 1 and Slice 2 acceptance lists are each satisfiable by pointing at
      an artifact.

## Tests

Follow the in-repo conventions: stdlib `testing`, no assert library,
`newTestStore(t)` / `newToolsTestStore(t)` in-memory SQLite helpers, personas
`alice`/`bob`/`carol`/`dana` with synthetic identifiers, test names that state
the behaviour, and a comment above each test explaining why the property
matters.

- [ ] T1. `internal/edgectx`: `TestSurvey_NeverRevealsACredentialValue` — feed
      a request with `Authorization: Bearer <synthetic>` and `Cookie:` and
      assert no substring of either value appears in the marshalled output and
      that both are marked `Secret`.
- [ ] T2. `internal/edgectx`: `TestSurvey_DigestIsStableForARepeatedValueAndDiffersOtherwise`
      — the property that makes "is this identifier per-request or constant?"
      answerable without printing it.
- [ ] T3. `internal/mcp`: `TestHTTPContext_EmitsNothingWhenTheSurveyIsDisabled`
      — capture slog via `slog.SetDefault(slog.New(slog.NewJSONHandler(&buf,
      nil)))` with `t.Cleanup` restore, as `internal/mcp/audit_edge_test.go`
      does, and assert the buffer is empty.
- [ ] T4. `internal/mcp`: `TestHTTPContext_CapturesTheTraceIDOnlyWhenSampled` —
      a recording span yields a 32-hex `TraceID`; a non-recording/unsampled one
      yields empty, because a trace id no backend holds is worse than none.
- [ ] T5. `internal/mcp`: `TestAudit_SetsCorrelationAttributesOnTheSpan` — use
      an in-memory `tracetest.SpanRecorder`, call `s.audit` with a populated
      `edgectx.Context`, and assert all eight attributes with their exact
      names; plus `TestAudit_OmitsEmptyAttributes`.
- [ ] T6. `internal/mcp`: `TestAudit_PutsNoSensitiveValueOnTheSpan` — call with
      an error message containing a synthetic `@handle` and a phone-like digit
      run, and assert the span carries neither (the span analogue of the
      existing `audit.ScrubText` guard on the log line).
- [ ] T7. `internal/db`: `TestLogToolCall_RecordsTheTraceID` — round-trip
      through `LogToolCall` + `ListAuditFor`, mirroring
      `internal/db/audit_edge_test.go`.
- [ ] T8. `internal/db`: `TestVerifyAuditChain_PreTraceIDRowsStillVerify` — the
      load-bearing backward-compatibility test. Hand-insert rows hashed with
      the old `auditEdge` (both the empty and the five-field-populated cases),
      then assert `VerifyAuditChain` reports `ok` and the expected `Verified`
      count. This is the test that proves the `0x02` marker did not
      retroactively invalidate anything.
- [ ] T9. `internal/db`: `TestVerifyAuditChain_DetectsATamperedTraceID` —
      `UPDATE audit_logs SET trace_id = ...` then assert the chain fails,
      matching the existing tamper test for `edge_request_id`.
- [ ] T10. `internal/mcp`: the existing
      `TestAuditToolDescriptions_DocumentEveryReturnedField` must pass
      unmodified — it reflects over `db.AuditEntry`'s JSON tags, so it fails
      until both tool descriptions mention `trace_id`. Do not weaken it.
- [ ] T11. `internal/mcp`: existing `TestOutputSchemasStayOpenToAdditiveFields`
      and `TestToolOutputSchemas` must pass with the new field — the guard
      against repeating the portal catalogue rejection of #631/#637.
- [ ] T12. `internal/tracing`: `TestInit_WithNoEndpointInstallsNoProvider` —
      the default path must be inert: no exporter, and `shutdown` returns nil
      promptly.
- [ ] T13. `internal/metrics`: assert `mcp_tool_calls_by_route_total` exposes
      at most the three expected label values and that `ToolInvocationsTotal`
      kept its original label set.
- [ ] T14. `docs`: `docs/runbook_test.go` and
      `deploy/alerts/runbook_links_test.go` must still resolve every anchor
      after the runbook link to the correlation example is added.

## Rollback

The change is additive in four separable layers, so it rolls back in pieces
without a data migration:

1. **Tracing.** Unset `OTEL_EXPORTER_OTLP_ENDPOINT`. `tracing.Init` installs
   nothing, spans stop, `edgectx.Context.TraceID` stays empty and new audit
   rows carry a NULL `trace_id`. No redeploy required; this is the default
   configuration, so the change ships inert and is switched on deliberately.
2. **Header survey.** Unset `EDGE_HEADER_SURVEY`. The survey emits nothing and
   `httpContext` is the function it is today.
3. **Code.** Revert the merge commit. The `trace_id` column and its index
   remain in the database and are simply never written; `LogToolCall` reverts
   to hashing without the `0x02` block, and rows written while the feature was
   live still verify, because the block is only present on rows that carry a
   trace id and the reverted `hashAuditEntry` would recompute those rows
   differently. If any correlated-with-trace rows were written, `VerifyAuditChain`
   would report them as tampered after a revert — so the safe rollback order is
   step 1 first (stop writing trace ids), then revert; or keep the `0x02` block
   in a revert-only patch that leaves hashing intact and removes only the
   middleware and the exporter.
4. **Documents.** `docs/reports/edge-headers-617.md` and
   `docs/reports/correlation-example-617.md` are evidence, not behaviour. They
   are never rolled back: a measurement that was true on its date stays true on
   its date. If a later measurement contradicts them, add a new dated section
   rather than editing the old one.

No column is dropped in any rollback path: dropping `trace_id` would change
the canonical hash input of the rows that carry it, which is the exact failure
mode `internal/db/db.go:125-137` exists to prevent.
