# Single recording path for every MCP tool-call outcome

## Context

Today a `tools/call` against `mctl-telegram` is only observable if the tool
handler happens to reach `Server.audit` (`internal/mcp/tools.go:2318`). Every
early return that fires before that line — `requireScope` failures, argument
validation, Local-Bridge mode refusals — returns
`mcplib.NewToolResultError(...)` and leaves no audit row, no `mcp tool call`
slog line and no metric. `toolSearchMessages` (`internal/mcp/tools.go`) has
three such returns before its single `s.audit` call. Three tools
(`get_my_send_status`, `get_my_identity`, `get_my_audit_log`) never call
`s.audit` at all. JSON-RPC-level failures are worse: an unknown tool name or an
unparsable `tools/call` body is rejected by `mcp-go` inside `handleToolCall`
before any handler runs, so nothing in this repository ever sees it. Because
the HTTP status is `200` in all of these cases, Cloudflare analytics cannot
flag them either.

Issue #696 records the operational consequence: on 2026-09-27 a user's client
reported a `search_messages` failure, Cloudflare logged five `200` responses
from Anthropic IPs at 19:28 UTC, and the pod had neither a log line nor an
`audit_logs` row for the call. `mctl_telegram_flood_wait_events_total` and
`mctl_telegram_client_errors_total` were both flat, proving the failure never
reached Telegram — but nothing on our side could say whether the fault was
ours or the client's. The blind spot itself is the defect. A third, narrower
bug sits at the other end: `jsonResult` (`internal/mcp/tools.go:2308`) can
return `encode: …` as an `IsError` result *after* the handler already wrote an
`ok` audit row, so the recorded status contradicts what the client received.

## User stories

- AS an on-call operator I WANT every failing MCP tool call to leave one audit
  row, one WARN log line and one metric sample SO THAT I can tell from the pod
  and from VictoriaMetrics whether a reported tool error originated in
  mctl-telegram, in Telegram, or in the client.
- AS an on-call operator I WANT JSON-RPC-level `tools/call` rejections (unknown
  tool, unparsable request, disabled capability) logged with their error code
  SO THAT a client calling a tool we never registered is distinguishable from a
  tool that ran and failed.
- AS an SRE I WANT a `{tool,reason}`-labelled error counter SO THAT I can
  alert on a specific failure class (for example a spike in `scope_denied`
  after an OAuth scope change) without grepping logs.
- AS a connected Telegram user I WANT my own audit log to show failed calls,
  not only successful ones SO THAT `get_my_audit_log` is a truthful record of
  what was attempted against my account. (The failed rows appear with their
  existing `status` and `error` fields; the new `reason` stays operator-only.)
- AS a maintainer I WANT the recording to live in one wrapper rather than in
  each of the ~36 tool handlers SO THAT a tool added later cannot reintroduce
  the blind spot by forgetting to call `s.audit`.

## Acceptance criteria (EARS)

- WHEN a registered tool handler returns a `*mcplib.CallToolResult` with
  `IsError=true`, from any code path including returns that precede
  `Server.audit`, THE SYSTEM SHALL write exactly one `audit_logs` row for that
  `tools/call` with `status="error"` and a non-empty `reason` drawn from the
  closed reason set.
- WHEN a registered tool handler returns an `IsError=true` result THE SYSTEM
  SHALL emit exactly one `mcp tool call` slog record at WARN carrying `tool`,
  `user_id`, `status`, `reason` and, when present, `peer`, `call_path`,
  `edge_request_id`, `edge_route`, `mcp_method`, `mcp_name` and
  `protocol_version`.
- WHEN a registered tool handler returns an `IsError=true` result THE SYSTEM
  SHALL increment `mctl_tool_call_errors_total{tool,reason}` exactly once.
- WHEN a tool handler returns a non-nil Go `error` THE SYSTEM SHALL record it
  through the same path with `reason="handler_error"` and convert it into an
  `IsError=true` tool result, so the model receives the failure in its context
  window instead of a bare JSON-RPC `INTERNAL_ERROR`.
- IF a tool handler panics THEN THE SYSTEM SHALL recover inside the recording
  wrapper, record the outcome with `reason="panic"`, and return an
  `IsError=true` result rather than unwinding into the transport.
- WHEN `mcp-go` returns a JSON-RPC `error` object for a `tools/call` request —
  unknown tool name, a tool excluded by `ToolFilter`, an unparsable
  `tools/call` body, or tools capability disabled — THE SYSTEM SHALL emit one
  WARN slog record `mcp jsonrpc error` carrying `mcp_method="tools/call"`, the
  requested tool name, the JSON-RPC error code, `edge_request_id`, and
  `user_id` when the request was authenticated.
- WHEN a JSON-RPC `tools/call` error is logged THE SYSTEM SHALL increment
  `mctl_tool_call_errors_total` with the requested tool name and a reason of
  `tool_not_found`, `unparsable_message`, `capability_disabled` or
  `jsonrpc_error`.
- WHILE recording any outcome THE SYSTEM SHALL emit no raw tool arguments, no
  message bodies, no phone numbers and no unredacted peer values; peer values
  SHALL remain the `telegram.RedactPeer` output already passed to
  `Server.audit`, and free-text error strings SHALL remain passed through
  `audit.ScrubText`.
- IF a handler has already recorded an outcome for the current call and the
  final result is `IsError=true` THEN THE SYSTEM SHALL record that call's
  terminal status as `error`, never as `ok` — in particular the
  `jsonResult` / `json.MarshalIndent` failure path SHALL NOT be recorded as
  `ok`.
- WHEN a tool handler completes successfully THE SYSTEM SHALL produce exactly
  the audit rows, INFO slog lines and `mctl_tool_invocations_total` /
  `mctl_tool_invocation_duration_seconds` samples it produces today, with no
  additional row or line contributed by the wrapper.
- WHILE a tool is on the audit-exempt-on-success list (`get_my_audit_log`,
  whose handler deliberately does not audit itself to avoid an audit-of-audit
  row on every page fetch, and `get_my_identity` / `get_my_send_status`, which
  do not audit their successes today) THE SYSTEM SHALL still record
  `IsError=true` outcomes but SHALL NOT add a row for a successful call.
- IF the request context is already cancelled or past its deadline when the
  outcome is recorded THEN THE SYSTEM SHALL write the audit row on a detached
  context bounded by `auditWriteTimeout`, as `auditDetached`
  (`internal/mcp/tools.go:2399`) does today.
- WHEN a `reason` is written to `audit_logs` THE SYSTEM SHALL store it in its
  own nullable column that is NOT part of the hash chain: `hashAuditEntry`
  (`internal/db/audit_chain.go:29`) and `Store.VerifyAuditChain` SHALL remain
  byte-for-byte unchanged, so every row written by the new binary also
  verifies under the previous binary and an image rollback cannot make the
  chain report tampering. The `reason` is a classification derived from the
  already-hashed `status` / `error` fields, so leaving it unhashed does not
  weaken the chain's tamper evidence over what actually happened.
- WHILE persisting `reason` THE SYSTEM SHALL NOT expose it through
  `get_my_audit_log`: `db.AuditEntry`'s JSON shape and that tool's
  `outputSchema` SHALL remain unchanged. The column is for operators (SQL,
  Loki, metrics), not part of the user-facing tool contract.
- WHILE labelling `mctl_tool_call_errors_total` THE SYSTEM SHALL use only
  compile-time reason constants, never a client-supplied string, so label
  cardinality stays bounded.

## Out of scope

- The connect / OAuth web pages and `internal/oauth` observability. Issue #696
  is the `internal/mcp`-only split of #695 problem 6; the connect flow keeps
  its current behaviour.
- Non-`tools/call` MCP methods (`tools/list`, `initialize`, `resources/read`,
  `ping`). The JSON-RPC error hook is scoped to `tools/call`.
- JSON-RPC failures that `mcp-go` rejects before method dispatch — a body that
  fails the outer `json.Unmarshal`, a wrong `jsonrpc` version, or an invalid
  protocol version. `handleRequest` (`server/request_handler.go:30-75` of
  `mark3labs/mcp-go@v1.0.0`) answers those with `createErrorResponse` without
  firing any hook, so they are unreachable from this repository. Covering them
  would need an HTTP-level wrapper and is deferred.
- Changing which errors each tool returns, their wording, or the
  `internal/mcp/errorcatalog.go` MTProto message catalog. This proposal
  classifies outcomes; it does not restate them.
- Alerting policy. A new counter is exported and documented; whether an alert
  rule fires on it is a follow-up with its own SLO discussion.
- Making `Store.LogToolCall` report its own write failures. It swallows
  `BeginTx`, `INSERT` and `Commit` errors today
  (`internal/db/store.go:1745-1802`); that is a real adjacent blind spot,
  recorded in Open questions, not fixed here.
- Retro-filling `reason` for existing `audit_logs` rows. The column is
  nullable and old rows stay NULL.

## Open questions

- **Metric name.** The issue proposes `mctl_telegram_tool_call_errors_total`,
  but the repository reserves the `mctl_telegram_*` prefix for the MTProto
  client subsystem; the MCP tool layer uses `mctl_tool_invocations_total` and
  `mctl_tool_invocation_duration_seconds`
  (`internal/metrics/metrics.go:406-415`). This proposal uses
  **`mctl_tool_call_errors_total`** for consistency. Flag at review if the
  issue's literal name is required.
- **Zero-baseline pre-creation.** `internal/metrics/metrics.go` pre-creates
  closed-set counters at zero so `increase()` has a baseline (see the
  `AgentPolicyDenialsTotal` loop). The full cross product here is roughly 36
  tools x ~18 reasons ≈ 650 series of mostly-zeros, and `internal/metrics`
  does not know the tool list. This proposal does **not** pre-create, and
  documents the `increase()` caveat in `docs/runbook.md`. Reviewer may prefer
  exporting the tool-name list from `internal/mcp` and pre-creating.
- **Exposing `reason` to users.** Resolved at review (operator, 2026-09-27):
  keep `reason` operator-only. `get_my_audit_log`'s output schema does not
  change in this issue; exposing it can be a separate, user-facing change.
- **Audit-exempt list.** Resolved at review (operator, 2026-09-27): do not
  start auditing successful `get_my_identity` / `get_my_send_status` calls in
  this issue. All three `get_my_*` tools are exempt on success and recorded on
  failure. Auditing their successes is a separate decision.
- **Hashing `reason`.** Resolved at review (operator, 2026-09-27): not hashed.
  A hashed `reason` behind a new marker byte would make a rolled-back binary
  report every new error row as tampered, as the first revision of this
  proposal noted in its Rollback section.
  For a derived diagnostic field that risk is not worth it.
- **Reason for Telegram RPC failures.** A single `telegram_error` reason keeps
  cardinality flat but loses the MTProto code (`PEER_ID_INVALID`,
  `CHAT_FORBIDDEN`, …) that `internal/mcp/errorcatalog.go` already classifies
  and `docs/troubleshooting.md` is organised around. This proposal uses the
  flat `telegram_error` and leaves the code in the existing `error` column;
  promoting the MTProto code into the label is a bounded follow-up.
