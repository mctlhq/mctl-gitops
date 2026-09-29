# Design: issue-8-2-4-executor-verifier-structured-conditi

## Current state

Read in the clone at `mctlhq/newton-mcp-gateway` (Python 3.12, `uv`, Pydantic v2, `mcp>=2.2,<3`
per `pyproject.toml`; `pytest` with `asyncio_mode = "auto"`).

**The contract.** `src/newton_mcp/action/contract.py` defines `PhysicalActionContract` with
`version: str = Field(default="0.1", pattern=r"^0\.1$")` and

```python
class Verification(BaseModel):
    condition: str = Field(description="Declarative success condition, e.g. 'temperature_c <= 24'.")
    timeout_seconds: int = Field(default=300, ge=1)
    retry_limit: int = Field(default=0, ge=0)
```

The string is inert today: nothing in the repo reads it. `grep -rn condition` finds it only in
`examples/physical-action.json`, the embedded twin `src/newton_mcp/action/examples.py`
(`MOCK_CONTRACT_EXAMPLE`), `README.md:125`, the generated
`schemas/physical-action-contract.schema.json`, a "not done yet" line in
`docs/action-runtime.md:320`, and four test fixtures
(`tests/runtime/test_catalog.py:270`, `tests/runtime/test_resolver.py:46` and `:289`,
`tests/test_policy_yaml.py:62`).

Three sync invariants already bind these files together, enforced by
`tests/test_action_contract.py`: the committed schema equals
`PhysicalActionContract.model_json_schema()`, `MOCK_CONTRACT_EXAMPLE` equals
`examples/physical-action.json`, and that example validates. `CONTRIBUTING.md` documents the
one-liner that regenerates the schema; `src/newton_mcp/action/prompts.py` embeds
`PhysicalActionContract.model_json_schema()` verbatim into the strict-JSON system prompt under
the marker `physical-action-contract/v0.1/strict-json`, so the prompt cannot drift from the
model.

**The runtime.** `src/newton_mcp/runtime/` is discovery and bookkeeping only:

- `config.py` — `runtime.yaml` models, all `extra="forbid"`. `CapabilityConfig` already carries
  `read_tool: str | None` and `idempotent: bool = False`. `ServerConfig.binding_identity` is
  `f"{resolved_identity}@sha256:{transport_fingerprint}"`.
- `catalog.py` — `CapabilityCatalog.refresh()` connects through the `ClientFactory` seam
  (`_default_client_factory` maps `StdioTransport -> StdioServerParameters`, `HttpTransport -> url`,
  both wrapped in `mcp.Client`), pages `list_tools` inside one `anyio.fail_after(...)` scope, and
  catches only `Exception`. `DiscoveredTool` records `read_only_hint`, currently unused by any
  consumer. `CatalogEntry.read_tool` is `None` when the configured read tool was not discovered
  (a `read_tool_missing` problem).
- `resolver.py` — synchronous; produces `CandidateAction(server_identity,
  server_binding_identity, tool_name, args, read_tool, idempotent, score, why)`.
  `render_arguments` deliberately refuses `verification.*` as a template root, and
  `tests/runtime/test_resolver.py:289` pins that.
- `lifecycle.py` — `ActionState` (ten members), the read-only `ALLOWED_TRANSITIONS` mapping, and
  `transition()` as the single guarded mutation point. `EXECUTING -> FAILED` and
  `UNKNOWN -> EXECUTING` deliberately do not exist. `FAILED -> EXECUTING` requires
  `verified_failure=True`, increments `attempt`, and is the *only* transition that may replace
  the attempt-scoped `tool_call_id`/`verification_id` pair. `ActionRecord` is frozen.
- `audit.py` — `AuditSink` `Protocol`, `AuditEvent` with `from`/`to` aliases, `MemoryAuditSink`
  (default, what tests use), `JsonlAuditSink`, and key-name-only `redact_args`.

`docs/action-runtime.md` closes with an explicit list of what the package does *not* do: execute
tools, retry, verify a physical outcome, evaluate `verification.condition`. `tests/runtime/conftest.py`
supplies the doubles this proposal extends: `build_fake_server` / `in_memory_factory` (in-process
`mcp.Client(MCPServer)`, no subprocess or socket), `hanging_factory`, `raising_factory`,
`deterministic_id_factory` and `fixed_now`.

So: every seam this issue needs already exists (`ClientFactory`, `id_factory`, `AuditSink`,
`idempotent`, `read_tool`, the state table). What is missing is the code that uses them, plus a
condition model that a machine can actually decide.

## Proposed solution

Four pieces: a structured condition model plus evaluator, an executor, a verifier, and a small
attempt loop that implements the retry rule. Nothing is registered as an MCP tool; `server.py`
and `config.py` (`Settings`) are untouched.

### 1. `src/newton_mcp/action/conditions.py` (new) — the model and the evaluator

```python
class Op(StrEnum):
    EQ = "eq"; NE = "ne"; LT = "lt"; LE = "le"; GT = "gt"; GE = "ge"

Scalar = bool | int | float | str | None

class Predicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str = Field(min_length=1)
    op: Op
    value: Scalar

class AllOf(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    all: tuple["Condition", ...] = Field(min_length=1)

class AnyOf(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    any: tuple["Condition", ...] = Field(min_length=1)

Condition = Annotated[
    Annotated[Predicate, Tag("predicate")] | Annotated[AllOf, Tag("all")] | Annotated[AnyOf, Tag("any")],
    Discriminator(_condition_tag),
]
```

`_condition_tag` is a callable discriminator: `"all"` if the input carries an `all` key/attribute,
`"any"` for `any`, else `"predicate"`. A callable `Discriminator` (not a field discriminator) is
the right tool because the issue fixes the wire shape as `{path, op, value}` / `{all: [...]}` /
`{any: [...]}` with **no tag field**; it still gives single-branch, precise validation errors
instead of smart-union ambiguity. This shape was prototyped against Pydantic 2.13 before writing
this design: recursive validation works after `AllOf.model_rebuild()` / `AnyOf.model_rebuild()`,
`model_json_schema()` emits clean `$defs` + `oneOf` `$ref` recursion, `model_dump()` round-trips
the exact wire shape, and smart-union keeps `24` an `int` and `true` a `bool`. Fields are named
`all`/`any` directly rather than `all_`/`any_` with aliases — they are builtins, not keywords, and
shadow nothing on `BaseModel` — so `model_dump()` needs no `by_alias=True` and
`propose.py`'s `contract.model_copy(...)` / MCP structured output keep emitting the contract
shape unchanged.

A `@model_validator(mode="after")` on `AllOf`/`AnyOf` enforces `MAX_CONDITION_DEPTH = 8`, in the
spirit of `MAX_TOOL_PAGES` in `catalog.py`.

Evaluation is a pure function:

```python
class ConditionResult(BaseModel):   # frozen
    satisfied: bool
    reason: str

def evaluate(condition: Condition, observation: Mapping[str, Any]) -> ConditionResult: ...
def resolve_path(path: str, observation: Mapping[str, Any]) -> tuple[bool, Any]: ...
```

Rules, all "not satisfied with a reason, never an exception":

- `resolve_path` splits on `.` and walks mappings only. A segment missing, or a non-mapping
  encountered mid-path, or a `None` container, is *not found*. A not-found path is not satisfied
  for every `op`, `ne` included.
- `eq`/`ne` compare only type-compatible operands: number vs number (with `bool` explicitly
  *not* a number, the rule `policy.py` already applies to `arg_ranges`), `str` vs `str`,
  `bool` vs `bool`, `None` vs `None`. Any other pairing is a type mismatch: not satisfied.
- `lt | le | gt | ge` require both operands to be `int`/`float` and not `bool`; anything else is a
  type mismatch.
- `all` is satisfied iff every child is; `any` iff at least one is. The composite reason names the
  first unsatisfied child (`all`) or summarises that no child matched (`any`), so a reason is
  always the most specific true one — the same instinct as the resolver's "first failing stage is
  the recorded rejection".
- Reasons name `path`, `op`, the contract's expected `value` and the observed value's *type*,
  never the observed value, following `approval.py`'s "names the failing field but never echoes an
  args value".

`conditions.py` lives under `action/`, not `runtime/`, because it is part of the contract model —
and `action/` must never import `runtime/` (stated in `canonical.py`'s docstring). `contract.py`
then becomes:

```python
version: str = Field(default="0.2", pattern=r"^0\.2$")
class Verification(BaseModel):
    condition: Condition
    timeout_seconds: int = Field(default=300, ge=1)
    retry_limit: int = Field(default=0, ge=0)
```

Everything the contract touches is regenerated or updated in lockstep: the schema file, the
example JSON, `examples.py`, `README.md:125`, the four test fixtures, and `prompts.py` (marker
becomes `physical-action-contract/v0.2/strict-json`, plus one sentence telling the model the
condition is a structured object and never an expression string — the schema itself is already
embedded verbatim, so nothing else needs restating).

### 2. `src/newton_mcp/runtime/executor.py` (new)

```python
class SupportsCallTool(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...

ToolClientFactory = Callable[[ServerConfig], AbstractAsyncContextManager[SupportsCallTool]]

class ExecutionOutcome(BaseModel):   # frozen
    state: ActionState               # EXECUTED | UNKNOWN
    tool_call_id: str
    detail: str
    result: Any | None = None

class Executor:
    def __init__(self, catalog: CapabilityCatalog, *, client_factory: ToolClientFactory | None = None,
                 call_timeout_seconds: float = DEFAULT_CALL_TIMEOUT_SECONDS, sink: AuditSink | None = None): ...
    async def execute(self, candidate, record, *, now) -> tuple[ActionRecord, ExecutionOutcome]: ...
```

`catalog.py`'s `_default_client_factory` is promoted to a public `default_client_factory` (same
body, `mcp.Client` already speaks both `list_tools` and `call_tool`) and reused here, so there is
exactly one place that maps a transport to a client. The catalog's own protocol and behaviour are
unchanged, including the test that proves `refresh()` never calls `call_tool`.

`execute()`:

1. Resolves the `ServerConfig` by `resolved_identity` from `catalog.config.servers`. Absent, or
   `binding_identity != candidate.server_binding_identity` → raise `ExecutorError` **before** any
   transport is opened. A re-pointed server must never receive a call resolved against the old
   one; this mirrors why `approval.py` binds to `binding_identity` rather than the label.
2. `transition(record, EXECUTING, reason, now=now, sink=sink, args=candidate.args)` — the audit
   line therefore carries the redacted args and `args_digest`, provable against the approval for
   the same action.
3. `with anyio.fail_after(call_timeout_seconds): async with factory(server) as client:
   result = await client.call_tool(candidate.tool_name, candidate.args)` — one scope over
   connect, handshake and the call, exactly as `catalog.refresh()` bounds its per-server cycle.
4. Any returned result, including an MCP error result → `transition(..., EXECUTED, ...)`. A
   completed call attempt does not prove nothing happened; there is no `EXECUTING -> FAILED` edge
   to take even if one wanted to.
5. `TimeoutError` or any `Exception`/`ExceptionGroup` from the transport → `transition(..., UNKNOWN, ...)`.
   `BaseException`/`BaseExceptionGroup` propagate untouched, as in `refresh()`.

### 3. `src/newton_mcp/runtime/verifier.py` (new)

```python
class VerificationOutcome(BaseModel):   # frozen
    state: ActionState                  # SUCCEEDED | FAILED | ESCALATED
    observations: int
    reason: str

class Verifier:
    def __init__(self, catalog, *, client_factory=None, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
                 read_timeout_seconds=DEFAULT_READ_TIMEOUT_SECONDS, sink=None,
                 clock=None, sleep=None): ...
    async def verify(self, candidate, contract, record, *, now) -> tuple[ActionRecord, VerificationOutcome]: ...
```

`clock` and `sleep` are injectable seams in the established style of `ClientFactory` and
`id_factory`, so tests drive the deadline deterministically without real waiting (the suite runs
under `asyncio_mode = "auto"`; `anyio.sleep` is the default `sleep`).

`verify()` transitions `EXECUTED|UNKNOWN -> VERIFYING` first, then decides:

- **Unverifiable, decided before any poll:** the candidate has no `read_tool`; or the matching
  `CatalogEntry.read_tool is None` (configured but not discovered); or that discovered tool
  declares `read_only_hint is False`. Each → `VERIFYING -> ESCALATED` with a naming reason. An
  unannotated (`None`) hint is allowed and the fact is recorded in the reason, per hard rule 5.
- **Poll loop:** first read issued immediately at t=0, then every `poll_interval_seconds` until
  `verification.timeout_seconds` elapses on the injected clock. Each poll calls only the read
  tool, bounded by `read_timeout_seconds`. The result is turned into a mapping by
  `observation_from_result()`: `structured_content` when present, else a single text block parsed
  as JSON into an object, else no observation (a failed poll, counted, never raised).
- Satisfied → `VERIFYING -> SUCCEEDED`, stop polling.
- Deadline reached with `observations >= 1` and never satisfied → `VERIFYING -> FAILED`, the
  verified failure the lifecycle module's invariant ("`FAILED` always means verified") depends on.
- Deadline reached with `observations == 0` → `VERIFYING -> ESCALATED`. Calling an unobservable
  world a verified failure would license a retry on evidence nobody has; this is the one place the
  design is stricter than the issue text, and it is why `FAILED` stays honest.

### 4. The attempt loop — `run_action()` in `executor.py`

The retry rule spans both modules, so it lives in exactly one place, next to the attempt counter:

```python
async def run_action(candidate, contract, record, *, executor, verifier, now_fn) -> tuple[ActionRecord, ActionState]:
    while True:
        record, execution = await executor.execute(candidate, record, now=now_fn())
        record, verification = await verifier.verify(candidate, contract, record, now=now_fn())
        if verification.state in (ActionState.SUCCEEDED, ActionState.ESCALATED):
            return record, verification.state
        # verified FAILED
        if candidate.idempotent and record.attempt <= contract.verification.retry_limit:
            record = transition(record, ActionState.EXECUTING, "retry after verified failure",
                                now=now_fn(), sink=sink, verified_failure=True, args=candidate.args)
            continue                      # attempt += 1, fresh tool_call_id/verification_id pair
        return transition(record, ActionState.ESCALATED, reason, now=now_fn(), sink=sink), ActionState.ESCALATED
```

This is the whole issue in nine lines, and it reads as the issue's rule:

- An `UNKNOWN` attempt cannot skip the verifier: the loop body always verifies, and the state
  machine has no `UNKNOWN -> EXECUTING` edge to take. Outcome already met → `SUCCEEDED`, and the
  loop returns with exactly one tool call ever issued.
- Non-idempotent after a verified failure (whether attempt 1 ended `EXECUTED` or `UNKNOWN`) →
  `ESCALATED`, no second call. "Never re-send a non-idempotent action whose first outcome is
  unknown" falls out of the same gate rather than being a separate special case.
- `record.attempt <= retry_limit` gives exactly the issue's counting: with `retry_limit=1`, attempt
  1 fails (`1 <= 1`) → retry; attempt 2 fails (`2 <= 1` false) → `ESCALATED`. With the default
  `retry_limit=0`, the first verified failure escalates.
- Every arm goes through `transition()` with the shared sink, so all four correlation ids land on
  every line, and a retry's `tool_call_id`/`verification_id` are replaced together by
  `transition()` itself.

### 5. Exports and docs

`newton_mcp/action/__init__.py` gains `Condition, Predicate, AllOf, AnyOf, Op, ConditionResult,
evaluate`; `newton_mcp/runtime/__init__.py` gains `Executor, ExecutionOutcome, Verifier,
VerificationOutcome, run_action`. `docs/architecture.md` gets the "digital success is not physical
success" section stating the retry rule; `docs/action-runtime.md` loses the "executes nothing / no
verification logic" claims and gains executor/verifier sections; `README.md` gets the v0.2 example
and an updated runtime paragraph. All of it keeps the "experimental proposal, not an Archetype
standard" and "mock-validated" wording (AGENTS.md, hard rules 2 and 3) — nothing here has been run
against a live actuator.

## Alternatives

1. **Keep `condition` as a string and write a tiny safe expression parser.** Rejected: the issue
   forbids it outright ("no expression strings and no parser"), and it is right to. A parser is
   attack surface and ambiguity (operator precedence, units, `null` handling) between a
   model-authored string and a physical actuator, and a reviewer of a `runtime.yaml`-adjacent
   artefact would have to learn a grammar to audit a safety condition. Structured predicates are
   auditable by reading the JSON.

2. **A tagged union with an explicit `kind` field (`{kind: "predicate", ...}`).** Rejected: it
   changes the wire shape the issue specifies, makes every contract wordier for the model to emit,
   and buys only a simpler discriminator. The callable `Discriminator` gives the same
   single-branch error quality without the tag, and was verified to work on the pinned Pydantic.

3. **Put the retry loop in a third module (`runtime/runner.py`) or in the verifier.** Rejected:
   the issue names two new runtime modules, and a reviewer looking for the safety-critical rule
   should find it next to the thing that counts attempts. Putting it in the verifier would give
   the observer authority to re-fire an actuator, which is precisely the separation this epic
   keeps.

4. **Treat "no observation obtained" as `FAILED`.** Rejected: `FAILED` is load-bearing in
   `lifecycle.py` — it is the only state from which a retry is legal, and it means *verified*
   failure. Letting an unreachable read tool produce `FAILED` would let a blind runtime retry a
   physical action on no evidence. `ESCALATED` is the honest terminal state.

5. **Verify with an LLM ("does this observation look like the goal was met?").** Explicitly out of
   scope in the issue, and it would put a non-deterministic judge in the safety path.

## Platform impact

**Breaking contract change, no migration.** `version` moves to `^0.2$` and
`verification.condition` changes type, so every v0.1 contract is rejected loudly by Pydantic
rather than silently reinterpreted. That is the intended behaviour for an owner-approved schema
change in a pre-1.0, mock-only repo with no persisted contracts: there is no database, no stored
action history, and the only v0.1 artefacts in existence are the ones in this repo, all updated in
the same commit. A consumer pinning v0.1 (none known outside the repo) must update; the README and
`docs/action-runtime.md` say so.

**Sync tests are the safety net.** `test_schema_file_is_in_sync_with_model` and
`test_mock_contract_example_is_in_sync_with_example_file` both fail until the schema, the example
file and `examples.py` are regenerated together, so a partial change cannot merge. The prompt
builder derives its schema at call time, so it cannot drift.

**No new dependency.** `anyio` (already transitively present and used in `catalog.py`) and
`pydantic` cover everything. No Temporal, Kubernetes, DB, auth platform or UI — hard rule 4.

**Runtime/resource impact.** The verifier introduces the repo's first waiting loop. It is bounded
twice: `verification.timeout_seconds` (`ge=1`, contract-supplied) for the whole loop and
`read_timeout_seconds` per poll, and the read tool is polled at most
`ceil(timeout/poll_interval) + 1` times. A contract can therefore pin a process for at most its own
declared timeout per attempt, times `retry_limit + 1` attempts. Connections are opened per call and
closed — no pooling, consistent with `docs/action-runtime.md`'s stated non-goals.

**Risks and mitigations.**

| Risk | Mitigation |
|---|---|
| A retry physically re-fires a non-idempotent actuator. | One gate: `candidate.idempotent` guards the only `FAILED -> EXECUTING` edge; `UNKNOWN -> EXECUTING` does not exist in `ALLOWED_TRANSITIONS`. Tests assert the *call count*, not just the final state. |
| `idempotent` in `runtime.yaml` is wrong (operator error). | It is an operator-reviewed allow-list, default `false`; the docs already frame it as retry-safety metadata. The failure direction of the default is "escalate to a human". |
| A verified `SUCCEEDED` on a stale or wrong observation. | The condition names an explicit `path`; a missing path is never satisfied; only the configured `read_tool` of the *same capability* is polled; a non-`read_only_hint` tool is refused. |
| Observed sensor values leaking into audit lines. | Reasons carry types, not observed values; `redact_args` still covers the call args. |
| A hostile or runaway model-authored condition (deep nesting, huge `all`). | `MAX_CONDITION_DEPTH = 8` at validation time; `extra="forbid"` on every condition model. |
| Callable-discriminator JSON Schema output surprises a downstream consumer. | The generated schema is committed and diff-reviewed, and `oneOf` + `$ref` recursion was checked against the pinned Pydantic before this design; the prompt embeds whatever the model generates, so model and prompt cannot disagree. |
| Someone reads the new code as a working live integration. | Docs keep "experimental proposal" and "mock-validated"; all tests use in-process fakes, no subprocess, no socket, no credentials. |
