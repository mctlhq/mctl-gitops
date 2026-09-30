# Close the P3 follow-ups from #700: MCP tool-call failure recording

## Context

mctl-telegram#696 (merged as #700) introduced a single recording path for every
MCP `tools/call` outcome: `Server.recordToolCall` (a
`mcpserver.ToolHandlerMiddleware`), `Server.flushRecordedCall`'s five flush
rules, the closed `Reason*` taxonomy in `internal/mcp/reasons.go`, the
text-based `classifyToolResultReason` classifier, and the JSON-RPC-level
`Server.jsonrpcHooks`. Review of #700 raised fourteen non-blocking P3 findings
across three areas — classification accuracy, recording semantics, and
API/docs/test hygiene — none of which blocked the merge. Issue #703 collects
them so the review threads can be resolved.

Left alone, each finding is small; together they make the failure record less
trustworthy than it claims to be. Two reasons are provably wrong or dead
(`ReasonStoreError` is never emitted, `"confirmation_id required"` is reported
as `not_found`), a wrapped JSON-RPC error logs `jsonrpc_code=0`, a successful
destructive `send_message:sent` audit row can be rewritten to `error` by a later
encode failure, server-fault failures (`panic`, `handler_error`) are invisible
to both the availability SLO and every alert rule, and the JSON-RPC hook's
metric label still accepts a client-supplied tool name for two of its four
reasons. This proposal closes all fourteen boxes with one coherent change set
rather than fourteen drive-by edits.

## User stories

- AS an on-call engineer I WANT `mctl_tool_call_errors_total{tool,reason}` to
  carry a reason that is derived from the failing code path, not guessed from
  the user-visible error text, SO THAT I can trust a reason breakdown during an
  incident.
- AS an on-call engineer I WANT a handler panic or a returned handler error to
  either burn the availability error budget or fire its own alert SO THAT a
  server-fault failure mode cannot run silently in production.
- AS an operator auditing a user I WANT the audit row of a completed
  destructive action (`send_message:sent`) to survive a later response-encoding
  failure SO THAT the audit log never denies that a message was actually sent.
- AS a platform operator I WANT `mctl_tool_call_errors_total`'s label
  cardinality to be bounded by an allowlist of registered tool names SO THAT a
  hostile or broken client cannot grow the Prometheus series set.
- AS a maintainer I WANT `Store.LogToolCall` to take a params struct instead of
  six consecutive bare strings SO THAT a call site cannot silently transpose
  `status` and `errMsg`.
- AS an on-call engineer reading `docs/runbook.md` I WANT the deliberate
  disagreement between `mctl_tool_call_errors_total` and the SLO metric pair
  stated explicitly, together with the audit row volume Rule 2 creates, SO THAT
  I do not read the difference as a bug or get surprised by chain-lock
  contention.

## Acceptance criteria (EARS)

### Classification

- WHEN a tool handler fails on a `*db.Store` call unrelated to the audit log
  itself, THE SYSTEM SHALL record `reason = store_error`, making
  `ReasonStoreError` reachable from a real code path.
- WHEN a tool handler returns the `"confirmation_id required — call
  prepare_get_media first"` (or `prepare_pin_message`/`prepare_send_message`)
  refusal, THE SYSTEM SHALL record `reason = invalid_argument`, not
  `not_found`.
- WHEN a `tgerr.Error` reaches `borrowErrResult` whose MTProto code appears in
  neither `mtprotoErrCatalog` nor `mtprotoTransientCatalog`, THE SYSTEM SHALL
  record `reason = telegram_error` rather than `unknown`.
- WHILE `classifyToolResultReason`'s `mtprotoErrCatalog` prefix loop remains in
  the classifier, THE SYSTEM SHALL treat it strictly as a fallback behind an
  explicit reason hint, and THE SYSTEM SHALL fail its own unit test if any
  catalog `message` is a prefix of another catalog `message` (which would make
  classification depend on Go map iteration order).
- WHEN `Server.jsonrpcHooks` reads a JSON-RPC error code, THE SYSTEM SHALL use
  `errors.As` against the `jsonrpcCoder` interface, so a wrapped
  `requestError` no longer logs `jsonrpc_code = 0`.

### Recording semantics

- WHEN a call is relayed to the Local Bridge and the bridge reports a failure,
  THE SYSTEM SHALL record `reason = bridge_error`.
- IF a handler refuses a request locally on a `mode == "local"` account without
  ever calling the bridge (for example `get_unread_messages` with
  `fetch_media=true`), THEN THE SYSTEM SHALL NOT record `bridge_error`; it
  shall record the reason of the actual refusal (`mode_unsupported`).
- WHEN the last staged record of a failing call has `status == "ok"`, THE
  SYSTEM SHALL keep that record unchanged and append a separate `status =
  "error"` record for the same call, so a completed destructive action
  (`send_message:sent`) is never rewritten to `error` by a later failure.
- WHEN the last staged record of a failing call already has `status ==
  "error"`, THE SYSTEM SHALL reconcile it in place as today (fill `reason`, and
  `errMsg` when empty) and SHALL NOT append a second row.
- WHILE any record was synthesized by `flushRecordedCall` rather than staged by
  `Server.audit`, THE SYSTEM SHALL mark it as synthesized — Rule 2 and Rule 3
  alike — so the field's invariant holds for every synthesized record.
- WHEN a synthesized record carries a server-fault reason (`panic`,
  `handler_error`, `store_error`, `encode_failed`), THE SYSTEM SHALL feed
  `ToolInvocationsTotal` / `ToolInvocationDuration` for it; WHEN it carries a
  client-fault reason (`auth_required`, `scope_denied`, `invalid_argument`,
  `mode_unsupported`, `refused`, `rate_limited`, `not_found`,
  `confirmation_rejected`, `media_capacity`, `unknown`), THE SYSTEM SHALL keep
  it out of that pair.
- WHILE a synthesized record has `status == "ok"` (Rule 3), THE SYSTEM SHALL
  keep it out of the SLO metric pair, so an unaudited success cannot dilute the
  availability denominator.
- WHEN `mctl_tool_call_errors_total{reason=~"panic|handler_error"}` is
  non-zero over a 15-minute window, THE SYSTEM SHALL fire a dedicated alert
  whose `runbook_url` resolves to an existing anchor in `docs/runbook.md`.
- WHEN `Server.jsonrpcHooks` sets the `tool` label on
  `ToolCallErrorsTotal`, THE SYSTEM SHALL emit the verbatim name only if it is
  in the set of tool names the server actually registered, and SHALL emit the
  fixed `"unregistered"` sentinel otherwise — for every reason, including
  `capability_disabled` and `jsonrpc_error`.
- IF the registered-tool set is not yet available when the hook fires, THEN THE
  SYSTEM SHALL emit `"unregistered"` (fail closed on cardinality).

### API, docs and tests

- WHEN a caller writes an audit row, THE SYSTEM SHALL accept a single
  `db.ToolCall` params struct instead of six consecutive bare `string`
  parameters, and every in-repo call site (`internal/mcp`, `internal/agentapi`,
  and the `internal/db` tests) shall be migrated.
- WHILE `docs/runbook.md` documents the tool-call error breakdown, THE SYSTEM
  SHALL state that `mctl_tool_call_errors_total` and the
  `mctl_tool_invocations_total` SLO pair deliberately disagree, and why.
- WHILE `docs/runbook.md` documents Rule 2, THE SYSTEM SHALL state that every
  client-fault rejection becomes a hash-chained `audit_logs` write, bounded per
  identity by `RATE_LIMIT_PER_USER` (default 30/min, i.e. at most 1800
  rows/hour/identity), and that each such write serializes on that user's chain
  lock (`SELECT … FOR UPDATE` on Postgres, `BEGIN IMMEDIATE` on SQLite).
- WHEN `internal/mcp/record_test.go` explains why a Rule 2 record does not feed
  the SLO pair, THE SYSTEM SHALL name the actual mechanism (the synthesized /
  server-fault predicate) rather than a missing elapsed duration, and the
  `histogramSampleCount` helper's doc line shall describe
  `mctl_tool_invocation_duration_seconds`'s real single `tool` label.

## Out of scope

- Any change to the `Reason*` values already emitted and documented, beyond the
  two reclassifications named above. The taxonomy stays a closed set of
  compile-time constants.
- Extending failure recording to MCP methods other than `tools/call`
  (`tools/list`, `initialize`, `resources/read`, `ping`) — still out of scope,
  as in #700.
- Changing the 99.5% tool-availability SLO target or the 14.4x / 6x burn-rate
  thresholds in `deploy/alerts/mctl-telegram.rules.yaml`.
- Folding `reason` into `hashAuditEntry` — `reason` stays outside the audit
  hash chain (`internal/db/audit_chain.go`).
- Pre-creating `mctl_tool_call_errors_total` series at zero; the runbook caveat
  about `increase()` stays as written.
- Any migration of existing `audit_logs` rows. Rows written before this change
  keep the reason they were written with.

## Open questions

- The issue names `ReasonCapabilityMissing`; the constant in
  `internal/mcp/reasons.go` is `ReasonCapabilityDisabled` (`"capability_disabled"`).
  Read as the same item; the allowlist fix covers it and every other
  JSON-RPC reason. No rename is proposed.
- The issue asks to "review the remaining unenumerated MTProto texts after
  0de0eb1"; the clone is shallow, so that commit's content was not readable
  here. Interpreted as: MTProto errors absent from both catalogs currently fall
  out of `mtprotoErrResult` as `nil`, reach `toolErr("%s: %v", tool, err)`, and
  classify as `unknown`. Resolved by hinting `telegram_error` at the
  `borrowErrResult` source rather than by enumerating more texts.
- Whether server-fault reasons should re-enter the availability SLO (chosen
  here) or whether the SLO input set should stay byte-identical to pre-#696 and
  the gap be closed by the new alert alone. Both halves of the issue's
  complaint are addressed by the chosen option; the alert-only variant is
  recorded in `design.md` under Alternatives and is a one-line revert of the
  predicate if burn-rate noise appears.
- Whether `telegram_error` / `bridge_error` count as server faults for SLO
  purposes. Treated as **not** server faults here (they are upstream/remote
  faults, and pre-#696 they already reached the SLO through `Server.audit`
  staging, so their SLO treatment is unchanged either way).
