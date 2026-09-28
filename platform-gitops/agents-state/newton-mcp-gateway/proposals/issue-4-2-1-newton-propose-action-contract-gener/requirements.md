# newton_propose_action: contract generation through Newton

> **Amended at owner review (before approval):** a backend-reported failure
> (`NewtonQueryResult.status == "failed"`) is a terminal `backend_failed` error with no retry and
> with the backend's own `error` text preserved. The single retry is reserved for bad *model
> output*: it corrects what the model wrote and must not mask a backend incident. Added a test
> for the mock path with an `allowed_goals` set that excludes the example contract's goal.

## Context

`newton-mcp-gateway` today implements Direction B only: three read-only MCP tools
(`newton_query`, `newton_embed_timeseries`, `newton_analyze_image` in
`src/newton_mcp/server.py`) over the documented Archetype `/query` endpoint. Direction A —
this project's experimental proposal that MCP can be a safe, auditable action boundary for
Newton — exists so far only as data and policy: `PhysicalActionContract` in
`src/newton_mcp/action/contract.py`, the deterministic `Policy` in
`src/newton_mcp/action/policy.py`, the generated `schemas/physical-action-contract.schema.json`
and the hand-written `examples/physical-action.json`. Nothing in the repo can yet *produce* a
contract: the example file is written by hand and the only test that consumes it is
`tests/test_action_contract.py`.

Issue #4 adds the first Direction A building block: one read-only MCP tool,
`newton_propose_action`, that turns an observation into exactly one *validated*
`PhysicalActionContract` by calling Newton C `/query` with a strict JSON system prompt — a
documented usage pattern already advertised in the `newton_query` tool description
("Use system_prompt to force structured JSON output"). This matters because it closes the
first link of the hypothesis in epic #1 (`observation -> Newton -> contract -> policy ->
actuator -> verification`) and because it establishes the non-negotiable rule for every later
phase: the gateway either returns a contract that validated against the Pydantic model, or it
returns a failure with the raw model text. It never guesses, repairs or partially fills a
contract. The tool proposes; it authorises and executes nothing.

## User stories

- AS an MCP host agent I WANT to hand Newton a physical-world observation and get back one
  schema-valid `PhysicalActionContract` SO THAT I can reason about what should happen in the
  physical world without inventing the contract myself.
- AS an operator of a physical deployment I WANT to restrict the proposal to a fixed set of
  `allowed_goals` SO THAT the model cannot propose an outcome my environment has no safe
  capability for.
- AS a reviewer or auditor I WANT a failed proposal to return the raw model text and the exact
  validation errors SO THAT I can see what Newton actually said instead of a silently repaired
  artifact.
- AS a developer with no Archetype credentials I WANT the mock backend to return the repo's
  example contract, clearly labelled as mock SO THAT I can wire and test the whole path without
  a key and without ever mistaking mock output for real inference.
- AS a maintainer I WANT the strict JSON prompt to live in one tested module SO THAT the schema
  and the `allowed_goals` constraint it embeds cannot drift away from the model.

## Acceptance criteria (EARS)

Tool surface

- WHEN an MCP client calls `tools/list` THE SYSTEM SHALL include `newton_propose_action`
  alongside `newton_query`, `newton_embed_timeseries` and `newton_analyze_image`.
- WHEN `newton_propose_action` is listed THE SYSTEM SHALL annotate it
  `read_only_hint=True` (and `open_world_hint=True`, matching the other three tools), because
  it only proposes an action and never executes one.
- WHEN `newton_propose_action` returns THE SYSTEM SHALL return an envelope whose keys are
  exactly `status`, `contract`, `raw_text`, `errors`, `backend`, `observation_id`.
- WHEN a proposal succeeds THE SYSTEM SHALL set `status` to `"completed"`, `contract` to the
  dumped validated `PhysicalActionContract`, `raw_text` to `null` and `errors` to `[]`.
- WHEN a proposal fails THE SYSTEM SHALL set `status` to `"failed"`, `contract` to `null`,
  `raw_text` to the last raw model text and `errors` to the accumulated errors of every attempt.

Input handling

- WHEN the caller supplies `text_events` and/or `json_events` THE SYSTEM SHALL send them to
  `/query` as `data.text` and `data.json` events, using the same mapping `newton_query` already
  uses in `src/newton_mcp/server.py`.
- IF neither `text_events` nor `json_events` contains at least one non-empty entry THEN THE
  SYSTEM SHALL raise a `ValueError` naming both parameters and SHALL make no backend call.
- IF an entry of `json_events` is not a parseable JSON document THEN THE SYSTEM SHALL raise a
  `ValueError` naming the offending index and SHALL make no backend call (the documented
  `data.json` `contents` field must be a serialized JSON string).
- WHEN `observation_id` is omitted THE SYSTEM SHALL derive one deterministically from the
  observation content as `obs-<first 16 hex chars of the sha256 of the canonicalised events>`.
- WHEN `observation_id` is supplied THE SYSTEM SHALL use it verbatim and echo it in the envelope.
- IF `allowed_goals` is supplied but contains no non-blank entry THEN THE SYSTEM SHALL raise a
  `ValueError` and SHALL make no backend call, so that an empty list can never be silently read
  as "any goal is allowed".
- WHEN `allowed_goals` is supplied THE SYSTEM SHALL strip and de-duplicate it while preserving
  the caller's order.

Prompt

- WHILE building the request THE SYSTEM SHALL use a system prompt built in
  `src/newton_mcp/action/prompts.py` that embeds `PhysicalActionContract.model_json_schema()`
  verbatim, lists the `allowed_goals` when present, and demands exactly one JSON object with no
  prose and no markdown fences.
- WHILE building the system prompt THE SYSTEM SHALL state the epic's safety bound as prompt
  guidance: benign reversible demo actions only (lights, HVAC within bounds, speaker
  announcements, benign routines) and never locks, ovens, alarms, industrial start/stop or
  safety systems.
- WHEN `allowed_goals` is absent THE SYSTEM SHALL build a prompt that omits the goal-restriction
  section rather than inventing a default goal list.

Parsing, validation and the single retry

- WHEN the model returns text THE SYSTEM SHALL parse it with `json.loads` after stripping
  surrounding whitespace only, and SHALL NOT strip markdown fences, extract a JSON substring, or
  otherwise repair the text.
- WHEN the parsed object validates against `PhysicalActionContract` THE SYSTEM SHALL return it.
- IF the backend returns a result with `status == "failed"` on any attempt THEN THE SYSTEM SHALL
  stop immediately without another `/query` call and return `status: "failed"`, `contract: null`,
  and an `errors` list that ends with one `backend_failed` error for that attempt. The error's
  message SHALL be the backend's `error` text verbatim. When the backend gave none, it SHALL be
  a fixed statement that the backend reported `status=failed` without an error message.
  `raw_text` SHALL be the first output only if `outputs` is non-empty and that first output
  is a string, and `null` otherwise (including `outputs == []`); nothing is synthesised. Transport or HTTP errors that the backend raises
  (`NewtonApiError`, including 401) keep propagating as tool errors, unchanged.
- IF an attempt whose backend result is `status == "completed"` yields non-JSON text, a JSON
  value that is not an object, a Pydantic validation error, an empty `outputs` list, or a
  non-string first output THEN THE SYSTEM SHALL retry exactly once, appending the recorded
  errors of the first attempt to the prompt. Only these model-output errors (and
  `goal_not_allowed`, below) are retryable.
- IF the second attempt also fails THEN THE SYSTEM SHALL return `status: "failed"` with the raw
  text of the second attempt and the errors of both attempts.
- WHILE handling any failure THE SYSTEM SHALL NOT return a guessed, defaulted or repaired
  contract, and SHALL NOT make more than two `/query` calls per tool call.
- IF `allowed_goals` is in force and the validated contract's `goal` is not a member THEN THE
  SYSTEM SHALL treat it as a validation failure of that attempt (so it is retried once, then
  fails), recording an error that names the rejected goal and the allowed set.

Evidence and provenance

- WHEN a contract validates THE SYSTEM SHALL overwrite `evidence.observation_id` with the
  effective `observation_id` and `evidence.summary` with a bounded summary derived from the
  observation, regardless of what the model put there.
- WHILE deriving `evidence.summary` THE SYSTEM SHALL build it only from the caller's
  `text_events` / `json_events` and SHALL truncate it to a fixed maximum length with an explicit
  ellipsis marker.

Mock backend

- WHEN the mock backend receives a request carrying the contract-proposal prompt marker THE
  SYSTEM SHALL return the repo's example contract from `examples/physical-action.json` as the
  single output, with `reason` prefixed by `[mock] `, and `backend: "mock"`.
- WHILE running on the mock backend THE SYSTEM SHALL still fill `evidence` from the caller's
  observation through the same code path used for the real backend.
- WHILE running on the mock backend THE SYSTEM SHALL keep the mock label visible in the returned
  artifact (`backend: "mock"` in the envelope and the `[mock] ` prefix inside `contract.reason`),
  so mock output can never be read as real inference.

Documentation

- WHEN the README's Direction A section is read THE SYSTEM SHALL describe `newton_propose_action`
  and SHALL keep the existing "this project's experimental proposal, not Archetype's" wording for
  the Physical Action Contract and the action runtime.
- WHEN the README Tools table is read THE SYSTEM SHALL list `newton_propose_action` with its
  Newton model family (Newton C) and note that it is read-only.

## Out of scope

- Executing, authorising or approving anything; no MCP client, no actuator, no tool invocation.
- Policy evaluation inside the tool. `Policy.evaluate` stays a separate, deterministic step owned
  by the action runtime (issues #5-#8). The proposal envelope carries no decision field.
- Any change to `PhysicalActionContract`, `Risk`, `Target`, `Verification`, `Evidence` or the
  generated `schemas/physical-action-contract.schema.json`. Contract v0.2 (structured
  `verification.condition`) is issue #8.
- Newton Agents API tools, image or time-series observations as input to this tool, batching,
  streaming, more than one contract per call.
- Live validation against a real `ATAI_API_KEY` (issue #12). This change is mock-validated only.
- Audit persistence, correlation-id propagation beyond `observation_id`, lifecycle states
  (issue #7); no DB, no Temporal, no Kubernetes, no auth platform, no UI.
- New runtime dependencies. Everything needed is already in `pyproject.toml` plus the stdlib.

## Open questions

- **Success status vocabulary.** The issue pins only `status: "failed"`. This proposal uses
  `"completed"` for success to match the repo's existing vocabulary
  (`NewtonQueryResult.status: Literal["completed", "failed"]` in `newton/models.py`). If the
  reviewer prefers the shorter `"ok"`, it is a one-line `Literal` change plus test updates.
- **Strict JSON parsing vs. fence tolerance.** Real chat-style models frequently wrap JSON in
  ```` ```json ```` fences. Because the repo's hard rule is "never return a guessed or repaired
  contract" and because the real adapter has never been exercised against a live account, this
  proposal parses strictly and lets the single retry (whose appended error explicitly says "no
  markdown fences") do the correcting. If live validation in issue #12 shows Newton C reliably
  fences its output, fence stripping can be added then as an explicit, tested normalisation step
  — not as silent repair.
- **Deterministic `observation_id`.** A content-derived sha256 id keeps tests and the mock path
  deterministic (the repo deliberately avoids clocks and randomness in the mock: see
  `MockNewtonBackend._embedding`), but two identical observations at different times collapse to
  the same id. A `uuid4`-based id would be unique but untestable without monkeypatching. The
  deterministic form is chosen here; issue #7, which owns correlation ids and audit, is the right
  place to revisit it.
- **No `query_id` in the envelope.** The acceptance criteria fix the envelope key set, so the
  underlying `NewtonQueryResult.query_id` is not surfaced. That loses the only handle linking a
  proposal to its `/query` call. Recorded for issue #7 rather than silently adding a key.
- **`allowed_goals` enforcement is advisory in the prompt, authoritative in Python.** The prompt
  lists the allowed goals, but the binding check is a post-validation membership test. A
  dynamically built `Literal` type would push it into the schema; see design.md for why that was
  dropped.
