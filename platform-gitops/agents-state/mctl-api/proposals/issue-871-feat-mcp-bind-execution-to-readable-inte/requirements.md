# Bind MCP execution requests to a readable intent and prove cross-surface resume

## Context
mctl-api#871 is the second slice after mctl-api#868 and mctl-agents#904/#573 (parent mctlhq/.github#281). The REST route
`POST /api/v1/work-items/{id}/execution-requests` already accepts an optional `intent_id`
(`executionRequestBody.IntentID` in `internal/api/handlers_execution_requests.go`). The MCP wrapper
`mctl_request_work_item_execution` (`internal/mcp/workitems.go`) cannot send it. The store
(`CreateExecutionRequest` in `internal/workitems/execution_requests.go`) checks only that the intent row exists. An
intent whose text retention has swept (`work_item_intents.text IS NULL`, surfaced as `Intent.TextRedacted`) is still
accepted, so a worker could assemble execution context from an empty retention placeholder.

This proposal does four things. It exposes `intent_id` on the MCP wrapper with exactly the REST semantics. It refuses a
pinned intent that is unreadable with a typed `409 intent_unavailable`, both at request time and again when the request
is fulfilled. It never substitutes another intent. It specifies the end-to-end proof that an MCP resume of a
Telegram-origin item seals `current_surface=mcp` and `surface_transition=true`. mctl-agents#573 computes and seals that
snapshot; this repo supplies the provenance it needs.

## User stories
- AS a user resuming work from an MCP client I WANT to name the exact intent the execution should act on SO THAT the run does what I asked, not a stale or swept statement.
- AS the execution platform I WANT a request whose pinned intent became unreadable after enqueue to be refused at fulfilment SO THAT I never run on placeholder text.
- AS a reviewer I WANT surface labels to grant no approval authority SO THAT moving from Telegram to MCP cannot widen what a principal may do.

## Acceptance criteria (EARS)
- WHEN `mctl_request_work_item_execution` is called with `intent_id` THE SYSTEM SHALL forward it as the integer JSON field `intent_id` in the REST body, unchanged, and otherwise send the same body as today.
- IF `intent_id` is present but is not a positive integer no larger than 2^53 THEN THE SYSTEM SHALL refuse locally with a tool error and make no HTTP call.
- WHEN `intent_id` is omitted THE SYSTEM SHALL send no `intent_id` key, so the REST semantics stay unchanged.
- WHEN an execution request is created with an `intent_id` whose stored text is NULL (redacted or unavailable) THE SYSTEM SHALL refuse with HTTP 409, code `intent_unavailable`, details `{intent_id}`, and SHALL record no request, event or idempotency entry.
- IF `intent_id` names no intent of this work item, including an intent of another item or another tenant, THEN THE SYSTEM SHALL keep answering 404 `intent_not_found`, and the answer SHALL not tell a foreign intent apart from a missing one.
- WHEN a claimed request is fulfilled and its pinned intent's text is now NULL THE SYSTEM SHALL refuse the fulfil with 409 `intent_unavailable`, attach no execution, and leave the request claimed so the holder can reject it.
- WHEN a claimed request is returned by `POST /api/v1/execution-requests/claim` THE SYSTEM SHALL include `intent_available` (true or false, never omitted when `intent_id` is set), so the dispatcher can reject the request before it delivers it to any loop (mctlhq/mctl-agents#963).
- WHILE a request pins an intent THE SYSTEM SHALL never substitute another intent. Binding a replacement intent requires a new request, authorized for the caller, with its own idempotency key.
- WHEN the same idempotency key and body are replayed THE SYSTEM SHALL return the original request (200, `replayed: true` over MCP) and SHALL never create a second request or execution.
- IF the same idempotency key is reused with a different `intent_id` THEN THE SYSTEM SHALL refuse with 409 `idempotency_key_reused`.
- IF the caller's tenant role is below developer (for example viewer) THEN THE SYSTEM SHALL refuse every execution-request write with 403 `tenant_role_forbidden`, with or without `intent_id`.
- WHEN an MCP resume is fulfilled for a work item whose origin surface is Telegram THE SYSTEM SHALL record `surface="mcp"` on the request and `requested_by` from the token, so the sealed snapshot (mctl-agents#573) can derive `current_surface=mcp` and `surface_transition=true`.
- IF the request's surface provenance is missing or empty THEN THE SYSTEM SHALL NOT present it as a known surface. A consumer must treat it as unknown and refuse, never as `surface_transition=false`.
- WHILE a request moves between surfaces THE SYSTEM SHALL grant no additional approval authority from the surface label. Existing approvals stay usable only under their original content digest, authority and freshness conditions.
- WHEN the same principal switches between MCP clients (MCP to MCP) THE SYSTEM SHALL record the same surface `mcp`, which is not a transition.
- WHEN executions are listed (`GET /api/v1/work-items/{id}/executions`) or a work item is read with its latest execution, THE SYSTEM SHALL include, for each execution that was minted by fulfilling an execution request, that request's `surface` and `requested_by` (and `acting_principal` when set). An execution with no fulfilled request, such as a DevLoop attach, SHALL carry neither field: absent means unknown, never a surface. This is what lets the snapshot's `surface_transition` compare against the previous execution instead of the item's origin (mctlhq/mctl-agents#960).

## Out of scope
- The three-wrapper manual handoff deliverable (separate slice).
- Enabling Portal `request_execution`. It stays disabled pending a separate owner decision.
- Implementing the retention sweeper (mctl-api#353). Tests use fixtures (`UPDATE work_item_intents SET text=NULL`) and do not claim a sweeper exists.
- Worker-side behaviour, which is owned by mctl-agents:
  - Since mctl-agents 1.114.1 (ADR 011 §10, #961), the investigator **refuses** a pinned intent that is redacted, absent or foreign (`refused` / `intent-redacted` | `intent-absent` | `intent-foreign-principal`). It does **not** park with an ADR 013 clarification. The remedy is a new request that pins a replacement intent.
  - The dispatcher's handling of the new code and field is mctlhq/mctl-agents#963.
  - The snapshot's `surface_transition` computation is mctlhq/mctl-agents#960.
  - This repo provides the inputs and the API-side guard only.
- Any approval, agents:intake, rollout or roadmap graph mutation.

## Open questions
- Final error code name: the issue proposes `intent_unavailable`. This proposal adopts it for both request-time and fulfil-time refusals.
- Should the fulfil-time refusal also be enforced on `kind=start`? Proposed yes: the guard is kind-independent.
- Whether `intent_available` belongs on the claim response or whether the worker should re-read `GET /work-items/{id}/intents/{intent_id}`. Proposed: both work; the claim field saves a round trip, and the fulfil guard is the backstop either way.
- The cross-surface proof itself was done live on 2026-11-01 (mctlhq/mctl-agents#573, closed). This repo does not validate snapshot canonical bytes. What this repo still owes is the per-execution provenance above, so that the agents side of #960 can stop using the origin as its baseline.
- The deployed mctl-api configuration and which worker image claims execution requests could not be confirmed (see design.md "Deployed state checked").
