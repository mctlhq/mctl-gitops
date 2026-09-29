# Executor + verifier: structured conditions, verify-before-retry (contract v0.2)

> **Amended at owner review (2026-09-29).** (a) The executor re-checks the context-bound
> `Approval` with `verify_approval()` immediately before every call attempt, including a retry;
> (b) `Executor.execute()` is the single owner of every `-> EXECUTING` transition, and
> `run_action()` only decides retry vs escalate; (c) a capability may declare `read_arguments`,
> rendered by the resolver like `arguments`, and the verifier calls `read_tool` with exactly those
> arguments; plus three documented edge cases (a read-tool error result is a failed poll, a
> capability without `read_tool` always ends `ESCALATED`, the last poll may overrun the deadline
> by at most `read_timeout_seconds`).

## Context

`newton-mcp-gateway` can already discover MCP tools (`src/newton_mcp/runtime/catalog.py`),
resolve a `PhysicalActionContract` into ranked `CandidateAction`s
(`src/newton_mcp/runtime/resolver.py`), decide auto/confirm/deny
(`src/newton_mcp/action/policy.py`), bind an approval to one exact action
(`src/newton_mcp/action/approval.py`) and track an action through a guarded state machine with
four correlation ids and an append-only audit trail
(`src/newton_mcp/runtime/lifecycle.py`, `src/newton_mcp/runtime/audit.py`). It executes
nothing: `docs/action-runtime.md` states plainly that no code in the repo ever calls
`call_tool`, and `tests/runtime/test_catalog.py::test_refresh_never_calls_call_tool` enforces
that for discovery.

This proposal closes the loop. A successful MCP tool call is not a successful physical action:
`set_target_temperature(23)` can return `200 OK` while the AC is offline or the room never
cools, and a timeout means the runtime does not know whether anything happened at all. Two new
modules — an **executor** that calls the chosen tool with a bounded timeout, and a **verifier**
that re-observes the world through the capability's `read_tool` — turn the existing lifecycle
table into behaviour, under one explicit retry rule: *verify before you ever retry, and never
re-send a non-idempotent action whose outcome is unknown*. Making that decidable requires
replacing today's free-text `verification.condition` string
(`src/newton_mcp/action/contract.py:34`) with structured predicates, an owner-approved schema
change that bumps the Physical Action Contract to **v0.2**. Structured predicates mean there is
no expression language and no parser to get wrong, and they are evaluated identically by the
runtime and by a reviewer reading the JSON.

## User stories

- AS an operator of a physical actuator I WANT the runtime to re-observe the world before it
  declares success SO THAT a digital `200 OK` is never mistaken for a physical outcome.
- AS an operator I WANT a tool-call timeout to be verified, never blindly retried SO THAT a
  non-idempotent action (an announcement, a one-shot routine) is never silently performed twice.
- AS an operator I WANT retries bounded by the contract's `retry_limit` and by the capability's
  declared `idempotent` flag SO THAT an unfixable situation escalates to a human instead of
  looping against the hardware.
- AS a contract author (a Newton model under a strict-JSON prompt) I WANT the success condition
  to be a small structured object SO THAT I cannot emit an expression the runtime silently
  misreads.
- AS a reviewer I WANT every state transition in the audit log with all four correlation ids SO
  THAT I can reconstruct exactly which call and which observation led to which outcome.

## Acceptance criteria (EARS)

### Contract v0.2 — structured conditions

- WHEN `verification.condition` is validated THE SYSTEM SHALL accept exactly one of: a predicate
  object `{path, op, value}` with `op` in `eq | ne | lt | le | gt | ge`, an `{all: [Condition, ...]}`
  object, or an `{any: [Condition, ...]}` object, resolved through a Pydantic discriminated
  union.
- WHEN `verification.condition` is a string, or carries an unknown key, or has an empty `all`/`any`
  list THE SYSTEM SHALL reject the contract with a Pydantic `ValidationError`.
- WHILE the contract model is loaded THE SYSTEM SHALL expose no expression parser, no `eval`, and
  no string-to-condition compilation anywhere in `src/newton_mcp/`.
- WHEN `PhysicalActionContract` is validated THE SYSTEM SHALL require `version` to match `^0\.2$`.
- WHEN the test suite runs THE SYSTEM SHALL find `schemas/physical-action-contract.schema.json`
  byte-equal to `PhysicalActionContract.model_json_schema()`
  (`tests/test_action_contract.py::test_schema_file_is_in_sync_with_model`), and
  `examples/physical-action.json`, `src/newton_mcp/action/examples.py::MOCK_CONTRACT_EXAMPLE` and
  the README example SHALL all be valid v0.2 contracts that agree with each other.
- WHEN the strict-JSON system prompt is built (`src/newton_mcp/action/prompts.py`) THE SYSTEM
  SHALL embed the v0.2 schema and a marker naming v0.2, and SHALL instruct the model that
  `verification.condition` is a structured object and never an expression string.

### Condition evaluation

- WHEN a predicate is evaluated against an observation THE SYSTEM SHALL resolve `path` as a
  dotted path into the observed mapping and compare the observed value to `value` under `op`,
  returning a `satisfied` boolean and a non-empty human-readable `reason`.
- IF `path` does not resolve in the observation THEN THE SYSTEM SHALL return not-satisfied with a
  reason naming the missing path, for every `op` including `ne`.
- IF the observed value and `value` cannot be compared under `op` (for example a string against a
  number, or any non-numeric operand under `lt | le | gt | ge`) THEN THE SYSTEM SHALL return
  not-satisfied with a reason naming the type mismatch, and SHALL NOT raise.
- WHILE evaluating `eq`/`ne` THE SYSTEM SHALL treat a `bool` as incomparable with a number, the
  same rule `src/newton_mcp/action/policy.py` already applies to `arg_ranges`.
- WHEN an `{all: [...]}` condition is evaluated THE SYSTEM SHALL be satisfied only if every child
  is satisfied; WHEN an `{any: [...]}` condition is evaluated THE SYSTEM SHALL be satisfied if at
  least one child is satisfied; nesting SHALL work to the declared maximum depth.
- WHILE producing a `reason` THE SYSTEM SHALL name the path, the operator and the contract-author's
  expected `value`, and SHALL NOT echo the raw observed value (only its type), following the
  precedent in `src/newton_mcp/action/approval.py` that a failure reason never echoes an argument
  value.
- WHEN evaluation runs THE SYSTEM SHALL perform no I/O and consult no LLM.

### Executor

- WHEN the executor runs a `CandidateAction` THE SYSTEM SHALL transition the record
  `AUTHORIZED -> EXECUTING` (or `FAILED -> EXECUTING` on a retry) through
  `newton_mcp.runtime.lifecycle.transition()` before any tool call is issued, writing the
  transition to the audit sink with the redacted args.
- WHEN the executor issues the call THE SYSTEM SHALL call exactly the candidate's `tool_name` with
  exactly the candidate's `args` on the configured server, inside one cancellation scope bounded
  by a configurable timeout that covers connect, handshake and the call.
- WHEN the call returns any result, including an MCP error result THE SYSTEM SHALL transition
  `EXECUTING -> EXECUTED`, because a completed call attempt does not prove the physical action did
  not happen (there is deliberately no `EXECUTING -> FAILED` edge).
- IF the call times out or the transport fails THEN THE SYSTEM SHALL transition
  `EXECUTING -> UNKNOWN`.
- IF the server named by the candidate is absent from the loaded `runtime.yaml`, or its
  `binding_identity` no longer equals `candidate.server_binding_identity` THEN THE SYSTEM SHALL
  refuse to call the tool and SHALL raise before any transport is opened.
- WHEN the executor is about to issue any call attempt, the first one or a retry, THE SYSTEM SHALL
  call `newton_mcp.action.approval.verify_approval(approval, candidate, record.action_id,
  policy_version, now)` immediately before the `-> EXECUTING` transition, and SHALL proceed only
  if it returns `valid=True` (owner amendment).
- IF that check fails on the first attempt THEN THE SYSTEM SHALL raise `ApprovalRejected` (a
  subclass of `ExecutorError`) naming the failing field, SHALL leave the record in `AUTHORIZED`,
  SHALL write no audit line and SHALL open no transport.
- IF that check fails on a retry (for example the approval expired between attempts) THEN THE
  SYSTEM SHALL transition `FAILED -> ESCALATED` with a reason naming the failing field and SHALL
  issue no further tool call.
- WHILE a policy decision is `auto` THE SYSTEM SHALL still execute only against an `Approval`: the
  caller issues one with `approved_by="policy:<policy_version>:<rule>"`, so there is exactly one
  execution path and no approval-less bypass.
- WHEN a call attempt starts THE SYSTEM SHALL perform its `-> EXECUTING` transition exactly once and
  only inside `Executor.execute()`: `AUTHORIZED -> EXECUTING` for the first attempt and
  `FAILED -> EXECUTING` with `verified_failure=True` for a retry (owner amendment).
- WHILE a call is in flight THE SYSTEM SHALL let task or process cancellation
  (`BaseException`/`BaseExceptionGroup`) propagate untouched, as `CapabilityCatalog.refresh()`
  already does.
- WHEN any transition is written THE SYSTEM SHALL carry the record's `tool_call_id` on the audit
  line, together with the other three correlation ids.

### Verifier

- WHEN verification begins THE SYSTEM SHALL transition `EXECUTED -> VERIFYING` or
  `UNKNOWN -> VERIFYING` before the first observation.
- WHILE verifying THE SYSTEM SHALL poll the capability's `read_tool` at a configurable interval,
  evaluating the condition on each observation, with the first poll issued immediately and the
  whole loop bounded by `verification.timeout_seconds`.
- WHEN the condition is satisfied by an observation THE SYSTEM SHALL transition
  `VERIFYING -> SUCCEEDED` and stop polling.
- IF at least one observation was obtained and the condition was never satisfied by the deadline
  THEN THE SYSTEM SHALL transition `VERIFYING -> FAILED`, a verified failure.
- IF no observation could be obtained at all — the capability declares no `read_tool`, the
  `read_tool` was not discovered (`CatalogEntry.read_tool is None`), the discovered read tool
  declares `read_only_hint is False`, or every poll failed — THEN THE SYSTEM SHALL transition
  `VERIFYING -> ESCALATED` and SHALL NOT report `FAILED` or `SUCCEEDED`.
- WHILE polling THE SYSTEM SHALL call only the `read_tool`, never the action tool.
- WHEN the verifier calls `read_tool` THE SYSTEM SHALL pass exactly `candidate.read_args`, rendered
  by the resolver from the capability's optional `read_arguments` template with the same
  `${...}` roots and the same refusal of `verification.*` as `arguments`; an absent template means
  `{}` (owner amendment).
- IF the `read_tool` returns an MCP error result THEN THE SYSTEM SHALL count that poll as failed
  (no observation), never as an observation, even if it carries structured content.
- WHILE a capability declares no `read_tool` THE SYSTEM SHALL still end the run `ESCALATED` after
  the call (it can never be verified); `docs/action-runtime.md` SHALL say so, since it applies to
  capabilities such as `announce`.
- WHILE polling THE SYSTEM SHALL issue no poll after the deadline; a poll started before it may
  complete up to `read_timeout_seconds` later, and the docs SHALL state that bound.

### Retry rule

- WHEN an attempt ends in `UNKNOWN` THE SYSTEM SHALL verify before any retry decision, and IF the
  outcome is already satisfied THEN THE SYSTEM SHALL report `SUCCEEDED` with no second tool call.
- IF a verified `FAILED` is reached and the capability is not `idempotent` THEN THE SYSTEM SHALL
  transition `FAILED -> ESCALATED` with no further tool call.
- IF a verified `FAILED` is reached, the capability is `idempotent`, and the number of attempts so
  far is less than or equal to `verification.retry_limit` THEN THE SYSTEM SHALL transition
  `FAILED -> EXECUTING` with `verified_failure=True`, minting a fresh attempt-scoped
  `tool_call_id`/`verification_id` pair; otherwise THE SYSTEM SHALL transition
  `FAILED -> ESCALATED`.
- WHEN `run_action()` decides to retry THE SYSTEM SHALL delegate the `FAILED -> EXECUTING`
  transition to `Executor.execute()`, which runs the approval check first; `run_action()` itself
  SHALL never transition into `EXECUTING`.
- WHILE the runtime is in `UNKNOWN` THE SYSTEM SHALL never transition directly to `EXECUTING` (the
  edge does not exist in `ALLOWED_TRANSITIONS`).
- WHEN a run finishes THE SYSTEM SHALL end in exactly one of `SUCCEEDED` or `ESCALATED`.

### Audit and docs

- WHEN any transition in a run is accepted THE SYSTEM SHALL write exactly one `AuditEvent`
  carrying `observation_id`, `action_id`, `tool_call_id`, `verification_id`, `from`/`to`,
  `reason`, `attempt` and `verified_failure`.
- WHEN `docs/architecture.md` is read THE SYSTEM SHALL present a section titled around "digital
  success is not physical success" that states the retry rule, and `docs/action-runtime.md` SHALL
  no longer claim the runtime executes and verifies nothing.
- WHILE documenting this work THE SYSTEM SHALL keep the "this project's experimental proposal, not
  an Archetype standard" wording and SHALL label every result as mock-validated, since no run
  against a live actuator or live Newton credentials is part of this proposal.

## Out of scope

- The smart-home demo and any end-to-end wiring of a real actuator (issue #9).
- LLM-based or model-assisted verification; the verifier is deterministic.
- New MCP tools on the gateway: nothing here is registered in `create_server()` and
  `newton_mcp.config.Settings` is untouched.
- Authenticating the approver. The `Approval` binding is context binding (it pins server,
  tool, args, action, policy version and expiry), not authentication; who may approve stays the
  caller's concern. (The earlier "wiring `verify_approval` is out of scope" line was removed at
  owner review: the executor now enforces it.)
- Backward compatibility with v0.1 contracts, a migration shim, or dual-version acceptance.
- Long-lived MCP sessions, connection pooling, reconnection backoff.
- Temporal, Kubernetes, a database, an auth platform or a UI.

## Open questions

Recorded, not blocking; each has a chosen default below.

1. **Path semantics.** Does `path` traverse list indices (`zones.0.temperature_c`)? Default
   chosen: mapping traversal only in v0.2, a numeric segment against a list is a *missing path*,
   documented. A later contract version can widen this without breaking existing conditions.
2. **Reason strings and observed values.** Naming the observed value would help debugging but the
   audit redactor is key-name-only, so an observed value could leak into a log line under a benign
   key. Default chosen: reasons name path, op, expected value and the observed value's *type*,
   never the raw observed value.
3. **Where the retry loop lives.** The issue names `runtime/executor.py` and `runtime/verifier.py`
   only. Default chosen: the attempt loop `run_action()` lives in `executor.py` (a retry is an
   execution-attempt decision) and the verifier stays a pure observer with no retry knowledge.
4. **Shape of an observation.** The MCP result to mapping conversion (`structured_content`, else a
   single JSON text block) is a seam, `observation_from_result`. Whether a non-JSON text result
   should ever count as an observation: default chosen, no — it counts as a failed poll.
5. **`retry_limit` counted across an `UNKNOWN` first attempt.** The issue's acceptance criterion
   (`retry_limit=1` after a forced timeout gives exactly one retry) implies one uniform counter.
   Default chosen: one counter, `record.attempt <= verification.retry_limit`, regardless of whether
   the failed attempt ended `EXECUTED` or `UNKNOWN`.
6. **Unannotated read tools.** Hard rule 5 says read tools are annotated `read_only_hint`. Default
   chosen: an explicit `read_only_hint is False` blocks verification (escalate); `None`
   (unannotated) is allowed with the fact recorded in the transition reason.
7. **Nesting depth.** A cap keeps a hostile or runaway model-authored condition bounded. Default
   chosen: `MAX_CONDITION_DEPTH = 8`, enforced at validation time, in the spirit of
   `MAX_TOOL_PAGES` in `runtime/catalog.py`.
