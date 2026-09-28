# Design: issue-4-2-1-newton-propose-action-contract-gener

## Current state

Read in the clone at `HEAD`:

- `src/newton_mcp/server.py` — `create_server(settings, backend)` builds one
  `mcp.server.mcpserver.MCPServer` and registers exactly three tools with `@server.tool(...)`,
  all annotated `ToolAnnotations(read_only_hint=True, open_world_hint=True)`. Every tool reads
  its dependencies through `_state(ctx)` -> `AppState(settings, backend)` yielded by the
  `lifespan`. Each tool builds a `NewtonQueryRequest`, awaits `state.backend.query(request)` and
  returns `result.model_dump(exclude={"raw"})`. `newton_query` already maps
  `text_events` -> `DataEvent.text(t)` and `json_events` -> `DataEvent(type="data.json",
  event_data={"contents": j})`, and already documents `system_prompt` as the way to "force
  structured JSON output". `newton_analyze_image` is the precedent for a tool that validates its
  input and raises `ValueError` *before* any backend call.
- `src/newton_mcp/newton/protocol.py` — `NewtonBackend` is a `runtime_checkable` `Protocol` with
  `name`, `query`, `upload_image`, `aclose`. This is the single seam to Newton.
- `src/newton_mcp/newton/models.py` — `NewtonQueryRequest` (model, query, `system_prompt`,
  `instruction_prompt`, `file_ids`, `events`, `max_new_tokens`, `normalize_input`) and
  `NewtonQueryResult` (`backend: Literal["mock","api"]`, `query_id`,
  `status: Literal["completed","failed"]`, `model`, `outputs: list[Any]`, `inference_time_sec`,
  `error`, `raw`). `outputs` is `response.response` from the API: strings for Newton C.
- `src/newton_mcp/newton/mock.py` — `MockNewtonBackend.query` branches on the request shape
  (`model.startswith("OmegaEncoder::")`, a `data.base64_img` event, an image `file_id`, else a
  generic fallback) and returns deterministic, `[mock]`-prefixed text with `backend="mock"`.
  No clock, no randomness; `_embedding` uses `hashlib.sha256` for determinism.
- `src/newton_mcp/newton/api.py` — `ArchetypeNewtonBackend.query` POSTs
  `{endpoint}/query`; `build_backend(settings)` picks mock vs api and uses a *function-local*
  import of `MockNewtonBackend`, the established pattern for avoiding import-order coupling.
- `src/newton_mcp/action/contract.py` — `PhysicalActionContract` (Pydantic v2) with `version`
  pinned `^0\.1$`, `goal`, `reason`, `confidence`, `target: Target`, `constraints`, `risk: Risk`,
  `reversible`, `requires_confirmation`, `verification: Verification`,
  `evidence: Evidence | None`. `Evidence` has `observation_id` and `summary`, both optional.
  `Target` is `extra="allow"`.
- `src/newton_mcp/action/policy.py` — deterministic `Policy.evaluate` -> `AUTO/CONFIRM/DENY`.
  Nothing calls it from the server; it is library-only today.
- `src/newton_mcp/action/__init__.py` — re-exports `Decision`, `PhysicalActionContract`,
  `Policy`, `PolicyRule`, `Risk`, `Target`, `Verification`.
- `examples/physical-action.json` — the hand-written example contract
  (`goal: reduce_room_temperature`, kitchen HVAC, `risk: low`), validated by
  `tests/test_action_contract.py::test_example_contract_validates`.
  `schemas/physical-action-contract.schema.json` is kept byte-equal to
  `PhysicalActionContract.model_json_schema()` by `test_schema_file_is_in_sync_with_model` —
  the repo's existing "generated artifact stays in sync, enforced by a test" convention.
- `tests/conftest.py` — `mock_backend` / `server` fixtures plus `call_tool(...)`, which builds a
  `Context` with a `SimpleNamespace(lifespan_context=AppState(...))` because
  `MCPServer.call_tool` provides no request context. Every tool test goes through it.
- `tests/test_mcp_server.py::test_lists_exactly_the_documented_tools` asserts the tool-name set
  is exactly the current three, and `test_tools_are_marked_read_only` asserts every tool is
  read-only. Both must be updated/satisfied by this change.
- `pyproject.toml` — Python >= 3.12, `mcp>=2.2,<3`, `pydantic>=2.7,<3`, `httpx`, dev
  `pytest` + `pytest-asyncio` with `asyncio_mode = "auto"`. Wheel packages only
  `["src/newton_mcp"]` — **`examples/` and `schemas/` are not shipped in the wheel**, which
  constrains how the mock path can reach the example contract (see below).
- `AGENTS.md` and `docs/architecture.md` fix the conventions: publicly documented Archetype
  behaviour only, labelled mock output, small explicit code, the contract and runtime are this
  project's proposal, and Direction A's lifecycle/correlation-id plan.

Nothing in the repo produces a contract today, and no module imports `newton_mcp.action` from
`newton_mcp.server` or `newton_mcp.newton`.

## Proposed solution

Four code changes, one doc change, one existing test to update. No dependency, schema or
contract-model change.

### 1. `src/newton_mcp/action/prompts.py` (new)

Pure, side-effect-free prompt construction. No I/O, no backend import.

```python
CONTRACT_PROMPT_MARKER = "physical-action-contract/v0.1/strict-json"

def build_contract_system_prompt(allowed_goals: tuple[str, ...] = ()) -> str: ...
def build_retry_suffix(errors: Sequence[ProposeError]) -> str: ...
```

`build_contract_system_prompt` embeds, in this order: the marker line (so the mock backend can
recognise a contract-proposal request without guessing), the instruction to emit exactly one
JSON object with no prose and no markdown fences, the safety bound from the epic's hard rule 7
(lights / HVAC within bounds / speaker announcements / benign reversible routines only; never
locks, ovens, alarms, industrial start/stop or safety systems), the `allowed_goals` block when
non-empty, and `json.dumps(PhysicalActionContract.model_json_schema(), indent=2, sort_keys=True)`.
Deriving the schema from the model at call time — not from
`schemas/physical-action-contract.schema.json` — means the prompt cannot drift from the model and
does not need the unshipped `schemas/` directory at runtime. When `allowed_goals` is empty the
goal block is omitted entirely rather than filled with a default list.

### 2. `src/newton_mcp/action/examples.py` (new)

`MOCK_CONTRACT_EXAMPLE: dict[str, Any]` — the contents of `examples/physical-action.json` as a
module-level literal, with a new test asserting it equals
`json.loads(Path("examples/physical-action.json").read_text())`.

This exists because the wheel ships only `src/newton_mcp` (`[tool.hatch.build.targets.wheel]`),
so reading `examples/physical-action.json` at runtime would work from a source checkout and fail
inside the Docker image the repo builds. Embedding the literal and enforcing equality with a test
reuses the convention `test_schema_file_is_in_sync_with_model` already established for
`schemas/`, and keeps packaging configuration untouched.

### 3. `src/newton_mcp/action/propose.py` (new)

The whole proposal algorithm, backend-agnostic, driven through the `NewtonBackend` protocol so it
is testable with a scripted fake.

```python
class ProposeError(BaseModel):
    attempt: int                      # 1 or 2
    kind: Literal["backend_failed", "empty_output", "not_a_string", "invalid_json",
                  "not_an_object", "validation_error", "goal_not_allowed"]
    message: str
    loc: str | None = None            # dotted Pydantic error location when available

class ProposeActionResult(BaseModel):
    status: Literal["completed", "failed"]
    contract: PhysicalActionContract | None = None
    raw_text: str | None = None
    errors: list[ProposeError] = Field(default_factory=list)
    backend: Literal["mock", "api"]
    observation_id: str

MAX_ATTEMPTS = 2
SUMMARY_MAX_CHARS = 280

async def propose_action(
    backend: NewtonBackend, *, model: str,
    text_events: Sequence[str] = (), json_events: Sequence[str] = (),
    allowed_goals: Sequence[str] | None = None,
    observation_id: str | None = None,
    max_new_tokens: int = 700,
) -> ProposeActionResult: ...
```

Flow, in one small explicit function plus helpers:

1. `_normalise_observation` — reject a blank observation (no non-empty `text_events` and no
   non-empty `json_events`) and any `json_events` entry that `json.loads` rejects, both as
   `ValueError` before any backend call, mirroring `newton_analyze_image`'s pre-flight style.
2. `_normalise_allowed_goals` — strip, drop blanks, de-duplicate preserving order; raise
   `ValueError` if a supplied list reduces to empty (an empty list must never read as
   "unconstrained").
3. `_observation_id` — the caller's value, or
   `"obs-" + sha256(json.dumps({"text": [...], "json": [...]}, sort_keys=True)).hexdigest()[:16]`.
   Deterministic, clock-free, consistent with the mock backend's style.
4. `_summary` — join the events with `" | "`, collapse whitespace, truncate to
   `SUMMARY_MAX_CHARS` with a trailing `"..."`.
5. Build `NewtonQueryRequest(model=model, query=<fixed instruction>, system_prompt=prompt,
   instruction_prompt=prompt, events=[...], max_new_tokens=...)`. Setting both `system_prompt`
   and `instruction_prompt` copies exactly what `newton_query` and `newton_analyze_image` already
   do; no new or invented API field is introduced.
6. Attempt loop, at most `MAX_ATTEMPTS` iterations: `await backend.query(request)`. **First**,
   if `result.status == "failed"`, record
   `ProposeError(attempt=n, kind="backend_failed", message=result.error or "backend reported
   status=failed without an error message")` and return `status="failed"` at once. In that case
   `raw_text` is `result.outputs[0]` only if it is a `str`, otherwise `None`, and there is no
   retry and no further `/query` call. The retry suffix tells the model how to fix its output,
   which cannot fix a backend failure; a second call would only hide the incident behind a
   second error (owner amendment). Otherwise take `result.outputs[0]` and classify failures into `ProposeError`s
   (`empty_output` / `not_a_string` / `invalid_json` / `not_an_object` / `validation_error` /
   `goal_not_allowed`). On attempt 2 the request's `system_prompt` / `instruction_prompt` get
   `build_retry_suffix(errors_so_far)` appended. `pydantic.ValidationError.errors()` is flattened
   into one `ProposeError` per entry, with `loc` joined by `.`.
7. `allowed_goals` membership is checked *after* Pydantic validation, and a violation is recorded
   as a failure of that attempt — so it gets the same single retry and then fails. The error
   message names the rejected goal and the allowed set.
8. On success, `contract.evidence` is replaced with
   `Evidence(observation_id=effective_id, summary=derived_summary)` unconditionally, so the model
   cannot forge provenance. Then `status="completed"`, `raw_text=None`, `errors=[]`.
9. On exhaustion, `status="failed"`, `contract=None`, `raw_text` = the last attempt's raw text
   (or `None` when there was no text at all), `errors` = every recorded error from both attempts.
   No contract is ever synthesised, defaulted or partially filled.

`backend` in the envelope comes from `NewtonQueryResult.backend`, not from a local guess.

### 4. `src/newton_mcp/newton/mock.py` (edit)

One new branch, placed before the generic text fallback and after the Omega/image branches:
if `CONTRACT_PROMPT_MARKER` appears in `request.system_prompt` (or `instruction_prompt`), return
`outputs=[json.dumps(contract)]` where `contract` is a copy of `MOCK_CONTRACT_EXAMPLE` with
`reason` prefixed by `"[mock] "`. The import of `newton_mcp.action.examples` is function-local,
matching `build_backend`'s local import of `MockNewtonBackend`, so no package-level cycle between
`newton/` and `action/` is introduced.

The output of this branch is deliberately pure JSON rather than `[mock]`-prefixed prose, because
`propose_action` must be able to parse it strictly — the same parser the real backend goes
through, which is the point of the mock path. Labelling is preserved in two places that travel
with the artifact: `backend: "mock"` in the envelope (from `NewtonQueryResult.backend`) and the
`[mock] ` prefix inside `contract.reason`, which a downstream consumer of the contract cannot
miss.

### 5. `src/newton_mcp/server.py` (edit)

A fourth `@server.tool` registration, `newton_propose_action`, annotated
`ToolAnnotations(read_only_hint=True, open_world_hint=True)`, whose description states plainly
that it proposes exactly one contract and executes nothing. Signature:
`(ctx, text_events=None, json_events=None, allowed_goals=None, observation_id=None,
max_new_tokens=700, model=None)`. Body: read `_state(ctx)`, delegate to
`propose_action(state.backend, model=model or state.settings.text_model, ...)`, return
`result.model_dump()`. All argument validation and all logic live in `propose.py`; the server
stays a thin registration layer, as it is for the existing tools.

`action/__init__.py` additionally re-exports `propose_action`, `ProposeActionResult` and
`ProposeError`.

### 6. `README.md` (edit)

A row in the Tools table (`newton_propose_action` | Newton C | "observation -> exactly one
validated Physical Action Contract; read-only, proposes only") and a paragraph in the
"Direction A: the Physical Action Contract (proposal)" section describing the tool, the strict
JSON prompt, `allowed_goals`, the one-retry-then-fail rule and the mock label. The existing
"this project's experimental proposal, not Archetype's" wording in that section and in the
"What is confirmed vs. proposed" table is left intact; the new text says "mock-validated" and
does not claim live Newton validation.

### 7. Test updates

`tests/test_mcp_server.py::test_lists_exactly_the_documented_tools` gains
`"newton_propose_action"` in the expected set; `test_tools_are_marked_read_only` passes
unchanged given the annotation above. A new `ScriptedNewtonBackend` in `tests/conftest.py`
(implements the `NewtonBackend` protocol, pops queued outputs, records requests, asserts it is
never called more times than scripted) drives the retry matrix deterministically without HTTP.

## Alternatives

1. **Dynamically build a Pydantic model with `goal: Literal[*allowed_goals]` per call.**
   Rejected: it puts the constraint in the schema (nice) at the cost of constructing a new model
   type per call, a second schema shape in the prompt, and Pydantic error messages that read as
   `literal_error` rather than naming the rejected goal and the allowed set. It also creates two
   contract types where the repo intends exactly one (`PhysicalActionContract`, whose generated
   schema a test pins). A post-validation membership check is three lines, produces a precise
   `goal_not_allowed` error, and keeps the schema untouched.

2. **Read `examples/physical-action.json` from disk in the mock branch.**
   Rejected: the wheel ships only `src/newton_mcp`, so this works in a source checkout and breaks
   in the container the repo builds (issue #2 added that Dockerfile). Adding a
   `force-include`/package-data rule to `pyproject.toml` would fix packaging but widens the change
   into build configuration and still does a file read on a hot path. An embedded literal plus a
   sync test reuses the `schemas/` convention already proven in
   `tests/test_action_contract.py`.

3. **Let `propose_action` short-circuit on `backend.name == "mock"` instead of teaching the mock
   backend a new branch.** Rejected: it would mean the mock path never exercises the real parse
   -> validate -> evidence-fill pipeline, which is the only thing the mock path is good for
   before issue #12. It would also put backend-specific behaviour in the backend-agnostic module
   and contradicts the issue's own "Files likely touched" list, which names `newton/mock.py`.

4. **Tolerant parsing: strip ```` ``` ```` fences and extract the first `{...}` span before
   `json.loads`.** Rejected for now: the issue's hard rule is "never return a guessed or repaired
   contract", and with no live account yet (issue #12) any tolerance would be speculation about
   Newton C's actual formatting. The single retry, whose appended error explicitly tells the model
   "no markdown fences", is the sanctioned correction channel. Recorded as an open question.

5. **Reuse `newton_query` with a caller-supplied `system_prompt` and no new tool.** Rejected: the
   issue asks for a tool, and the whole value here is the parse/validate/retry/evidence guarantee.
   Pushing the prompt onto every caller guarantees drift from
   `PhysicalActionContract.model_json_schema()` and returns unvalidated text.

## Platform impact

- **Migrations:** none. No database, no persisted state, no schema change. `schemas/` and
  `examples/` are untouched, so `test_schema_file_is_in_sync_with_model` and
  `test_example_contract_validates` keep passing as-is.
- **Backward compatibility:** additive. The three existing tools, their signatures and their
  responses are unchanged. The only behavioural change to existing code is one new branch in
  `MockNewtonBackend.query`, guarded by a marker string that no existing tool ever sends — the
  generic `[mock] Newton is not connected...` fallback still serves every current request shape.
  One existing test assertion (the exact tool-name set) changes by design, which is the intended
  signal that the public tool surface grew.
- **Resource impact:** at most two extra `/query` calls per tool call, bounded by
  `MAX_ATTEMPTS = 2`; zero on any input that fails pre-flight validation. `max_new_tokens`
  defaults to 700 rather than the 400 used elsewhere because a full contract JSON plus the
  embedded schema's field set does not fit comfortably in 400 tokens; it stays caller-overridable.
  No new dependency, so `uv.lock` and the `uv sync --locked` CI step are unaffected.
- **Risks and mitigations:**
  - *Prompt-injected provenance.* An observation could try to dictate `evidence` or a goal.
    Mitigated by overwriting `evidence` after validation and by the `allowed_goals` membership
    check, both server-side.
  - *Mock output mistaken for real inference.* Mitigated by the `[mock] ` prefix inside
    `contract.reason`, `backend: "mock"` in the envelope, and a test asserting both. README text
    says "mock-validated" only.
  - *Unsafe proposals.* The tool proposes and never executes; the safety bound is prompt guidance
    plus `allowed_goals`, and policy/approval remain owned by the runtime (issues #5-#8). The
    proposal envelope carries no decision, so nothing downstream can mistake a proposal for an
    authorisation.
  - *Strict parsing rejecting real Newton output.* Accepted and documented: the failure path
    returns the raw text, so issue #12's live run produces exactly the evidence needed to decide
    whether a normalisation step is justified.
  - *Unbounded `raw_text` in a failure envelope.* Mitigated by relying on `max_new_tokens` to
    bound the model's output; no additional truncation is applied, because truncating the raw text
    would degrade the one artifact a reviewer needs.
