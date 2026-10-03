# Route remaining client-fault refusals through auditRefusal and retire classifyReason

## Context
mctl-telegram#717 added `Server.auditRefusal` (`internal/mcp/tools.go`), which stages a
refusal as a *synthesized* error record with an explicit reason, so a client tripping a
policy limit is audited (`audit_logs`, `mctl_tool_call_errors_total{reason}`) but does not
sample `mctl_tool_invocations_total` / `mctl_tool_invocation_duration_seconds`, the inputs of
the paging availability SLO (`MctlToolAvailabilityFastBurn`). Issue #718 collects the P3
findings deferred from the #717 review: several client-fault or policy refusals still go
through `Server.audit` with a non-nil error and therefore still burn the SLO; the
`classifyReason` alias in `internal/mcp/record.go` has a dead `callPath` parameter;
`provision_local_account`'s `db.ErrAccountAlreadyActive` branch classifies as `unknown`; and
`encode_failed` is neither alerted nor SLO-burning.

None of these is a regression versus pre-#696 behaviour. The work makes the documented
contract ("a client tripping a policy limit does not burn the availability SLO",
`docs/runbook.md` around line 1524) true for every known refusal site and removes the
alias so there is one classifier entry point.

## User stories
- AS an on-call operator I WANT client mistakes and policy denials excluded from the tool
  availability SLO SO THAT a looping misbehaving agent cannot page me for a healthy server.
- AS an operator reading `audit_logs` or `mctl_tool_call_errors_total` I WANT every refusal
  to carry an explicit, accurate reason SO THAT I do not have to triage `unknown` rows.
- AS a maintainer I WANT a single tool-result classifier function SO THAT there is no dead
  parameter suggesting routing facts steer classification.

## Acceptance criteria (EARS)
- WHEN `pin_message` is refused by `evaluateWriteGate` THE SYSTEM SHALL record the
  `pin_message:blocked` row through `Server.auditRefusal` with reason `refused`, status
  `error`, and SHALL NOT increment `mctl_tool_invocations_total{tool="pin_message:blocked"}`.
- WHEN the demo/reviewer identity calls `disconnect_telegram_account` or
  `delete_telegram_account` THE SYSTEM SHALL record the refusal through `Server.auditRefusal`
  with reason `refused` and SHALL NOT sample the availability SLO series for that tool.
- WHEN `revoke_local_bridge_device` is called with a `device_id` that does not exist or is
  not owned by the caller THE SYSTEM SHALL record the refusal through `Server.auditRefusal`
  with reason `not_found`, and the client-visible text SHALL remain
  `no such device on your account`.
- WHEN `get_media`'s `Confirms.Claim` fails THE SYSTEM SHALL record the refusal through
  `Server.auditRefusal` with reason `confirmation_rejected` for `ErrConfirmationMismatch` /
  `ErrConfirmationWrongUser`, `refused` for `ErrConfirmationInFlight`, and `not_found` for
  every other claim failure.
- WHEN `get_media` finds no `MediaStore` reference for a claimed confirmation THE SYSTEM
  SHALL record the refusal through `Server.auditRefusal` with reason `not_found`.
- WHEN `provision_local_account` hits `db.ErrAccountAlreadyActive` THE SYSTEM SHALL record
  the refusal with explicit reason `refused` (not `unknown`) through `Server.auditRefusal`.
- WHEN `provision_local_account` rejects a non-positive `telegram_id` THE SYSTEM SHALL record
  the refusal through `Server.auditRefusal` with reason `invalid_argument`.
- WHILE any refusal above is recorded THE SYSTEM SHALL still write exactly one `audit_logs`
  row with status `error`, the same tool name and redacted peer as today, and SHALL still
  increment `mctl_tool_call_errors_total{tool,reason}`.
- WHILE handling any refusal above THE SYSTEM SHALL return the same client-visible error text
  as today (no user-facing behaviour change).
- THE SYSTEM SHALL classify final tool results through `classifyToolResultReason` only;
  `classifyReason` SHALL no longer exist.
- IF a staged record carries `callPath == "local"` and the call fails with no hint THEN THE
  SYSTEM SHALL classify it from the result text alone (e.g. `invalid_argument`), never as
  `bridge_error`.
- WHEN a handler records a genuine server-side failure (MTProto, store, bridge) through
  `Server.audit` THE SYSTEM SHALL continue to feed the availability SLO exactly as today.

## Out of scope
- Item 4 of the issue: widening `MctlToolHandlerFaults` in
  `deploy/alerts/mctl-telegram.rules.yaml` from `panic|handler_error` to
  `panic|handler_error|encode_failed`. That scope was fixed by a recorded human decision
  (mctlhq/mctl-gitops#1478) and the issue explicitly requires a new operator decision; this
  proposal does not change the alert rule, its unit tests, or the SLO input set for
  `encode_failed`.
- Other `Server.audit` error sites that are not on the #717 review list (for example the
  `get_media` download-size cap at `internal/mcp/media_tools.go` around line 246) — see Open
  questions.
- Any change to `auditRefusal`, `flushRecordedCall`'s rules, the `Reason*` constant set, or
  metric names/labels.

## Open questions
- Encode_failed alerting (issue item 4) needs an explicit operator decision; recorded here,
  not acted on.
- Which reason fits `ErrAccountAlreadyActive`? The issue only says "an explicit reason like
  the ErrUserNotFound branches". This proposal uses `refused` (a policy refusal that is
  neither a scope nor an argument problem, per the `ReasonRefused` doc comment). An
  alternative is `invalid_argument`; no new constant is introduced either way.
- `get_media`'s `ErrConfirmationInFlight` ("download already in progress") is a concurrency
  refusal; this proposal maps it to `refused`. Today it classifies as `unknown`.
- Should the `get_media` size-cap refusal ("file size ... exceeds the ...-byte download cap")
  also move to `auditRefusal`? It is a policy limit but was not on the review list; left
  unchanged here to keep the change set to the reviewed sites.
