# Design: issue-7-2-3b-action-lifecycle-incl-unknown-corre

> **Amended at owner review (before approval):**
> (1) **No `EXECUTING -> FAILED` edge.** A synchronous MCP error response is still a completed
> call attempt and goes `EXECUTING -> EXECUTED -> VERIFYING`. `FAILED` is reachable only
> through `VERIFYING`, so "failed" always means verified failure; `verified_failure=True` on
> `FAILED -> EXECUTING` remains an additional guard.
> (2) **Attempt-scoped ids.** `observation_id` and `action_id` are immutable for the whole
> action. `tool_call_id` and `verification_id` belong to one attempt. Attempt 1 uses the ids
> created by `new_action_record()`. `AUTHORIZED -> EXECUTING` changes no id (only `attempt`
> 0 -> 1), and `EXECUTED/UNKNOWN -> VERIFYING` does not change `verification_id`. Only a retry
> `FAILED -> EXECUTING` opens a new attempt and replaces **both** `tool_call_id` and
> `verification_id` together. Explicitly supplied ids may override the generated pair only on
> that transition.
> (3) `observation_id` is normally propagated from `newton_propose_action`; generation in
> `new_action_record()` is a fallback only.

## Current state

The repo is a Python 3.12 / `uv` / Pydantic v2 project (`pyproject.toml`, `AGENTS.md`) with two
halves: a Newton MCP gateway (`src/newton_mcp/server.py`, `newton/`) and the experimental action
runtime proposal.

What already exists on the action path, in pipeline order:

- `src/newton_mcp/action/contract.py` — `PhysicalActionContract` (`goal`, `reason`, `confidence`,
  `Target`, `constraints`, `Risk`, `reversible`, `requires_confirmation`, `Verification` with
  `timeout_seconds` / `retry_limit`, and `Evidence.observation_id`). `Risk` is a `StrEnum`; this is
  the model that `schemas/physical-action-contract.schema.json` is generated from, and
  `tests/test_action_contract.py` asserts the committed schema matches it byte-for-byte.
- `src/newton_mcp/action/propose.py` — turns an observation into a contract. It already mints an
  observation id: `_observation_id()` returns `"obs-" + sha256(...)[:16]`, and `ProposeActionResult`
  carries `observation_id`. That prefix-plus-16-hex shape is the precedent for the ids added here.
- `src/newton_mcp/runtime/config.py` — the reviewable `runtime.yaml` allow-list. Every model sets
  `extra="forbid"`; `load_runtime_config()` reads `NEWTON_MCP_RUNTIME_CONFIG` and raises `ValueError`
  when the variable is unset/blank, the file is missing, or the YAML is unparseable. There is
  deliberately no fallback to a default config.
- `src/newton_mcp/runtime/catalog.py` — the MCP host. Notable conventions reused below: the
  `SupportsListTools` `Protocol` and the `ClientFactory` seam (a `Callable` type alias) that tests
  substitute; frozen Pydantic models (`DiscoveredTool`, `CatalogEntry`, `CatalogProblem`,
  `CatalogSnapshot`); module-level constants (`DEFAULT_SERVER_TIMEOUT_SECONDS`, `MAX_TOOL_PAGES`,
  `_MAX_DETAIL_CHARS = 500`) and a private `_truncate()` helper.
- `src/newton_mcp/runtime/resolver.py` — deterministic, synchronous resolution to
  `CandidateAction(server_identity, server_binding_identity, tool_name, args, read_tool, idempotent,
  score, why)` plus explicit `Rejection`s.
- `src/newton_mcp/action/policy.py` — `Decision` (`auto`/`confirm`/`deny`) from a reviewable
  `policy.yaml` with a required `policy_version`.
- `src/newton_mcp/action/approval.py` — `Approval` bound to one exact action via
  `compute_binding()`; it stores `args_digest = sha256_hex(candidate.args)` and pins
  `policy_version`. Its module docstring states that "Lifecycle, correlation ids beyond `action_id`,
  audit, revocation and execution are all out of scope here too", and `docs/action-runtime.md`
  attributes audit to "issue #7".
- `src/newton_mcp/canonical.py` — `canonical_json_bytes()`, `sha256_hex()` and
  `canonical_timestamp()` (aware datetimes only, UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ`). It sits outside
  both packages precisely so `action/` and `runtime/` can share it. `action/` must never import
  `runtime/`; `runtime/` already imports `action/contract.py`.

What is missing, confirmed by grep: there is no `ActionState`, no `lifecycle`, no `audit`, no
`tool_call_id` and no `verification_id` anywhere in `src/`. The only traces are aspirational prose —
`docs/architecture.md:47` lists `PROPOSED -> AUTHORIZED -> EXECUTING -> EXECUTED -> VERIFYING ->
SUCCEEDED | FAILED | ESCALATED` (no `UNKNOWN`, no `DENIED`), `docs/architecture.md:49-50` names the
four correlation ids, and `docs/action-runtime.md:8` plus `README.md:164` both advertise "no
lifecycle, no audit".

Test conventions to follow: `tests/runtime/` is a package with its own `conftest.py` full of
seam doubles; tests are plain `pytest` functions with `from __future__ import annotations`, type
hints on test functions, module-level fixture dicts (`MINIMAL_CONFIG`, `MINIMAL_POLICY`),
`@pytest.mark.parametrize` for table-driven cases, `tmp_path` for file tests, and dataclass fakes
(`FakeCandidate` in `tests/test_policy_yaml.py`). `asyncio_mode = "auto"`. CI runs
`uv sync --locked --group dev && uv run pytest -q`.

## Proposed solution

Two new modules under `src/newton_mcp/runtime/`, exactly as the issue names them. They are pure,
synchronous, dependency-free (stdlib plus Pydantic), and they execute nothing — no MCP call, no
network, no LLM. `runtime/lifecycle.py` imports `runtime/audit.py`; `audit.py` imports neither
`lifecycle.py` nor anything from `action/`, which keeps the dependency edge one-directional and
leaves `audit.py` reusable by a future executor without dragging the state machine in.

### `runtime/lifecycle.py`

`ActionState(StrEnum)` with ten members, lowercase values, matching `Risk` and `Decision`:
`PROPOSED`, `AUTHORIZED`, `DENIED`, `EXECUTING`, `EXECUTED`, `UNKNOWN`, `VERIFYING`, `SUCCEEDED`,
`FAILED`, `ESCALATED`.

The safety argument lives in one readable data structure, not in control flow:

```python
ALLOWED_TRANSITIONS: Mapping[ActionState, frozenset[ActionState]] = MappingProxyType({
    ActionState.PROPOSED:   frozenset({ActionState.AUTHORIZED, ActionState.DENIED}),
    ActionState.AUTHORIZED: frozenset({ActionState.EXECUTING}),
    ActionState.EXECUTING:  frozenset({ActionState.EXECUTED, ActionState.UNKNOWN}),
    ActionState.EXECUTED:   frozenset({ActionState.VERIFYING}),
    ActionState.UNKNOWN:    frozenset({ActionState.VERIFYING, ActionState.ESCALATED}),
    ActionState.VERIFYING:  frozenset({ActionState.SUCCEEDED, ActionState.FAILED, ActionState.ESCALATED}),
    ActionState.FAILED:     frozenset({ActionState.EXECUTING, ActionState.ESCALATED}),
    ActionState.DENIED:     frozenset(),
    ActionState.SUCCEEDED:  frozenset(),
    ActionState.ESCALATED:  frozenset(),
})

REQUIRES_VERIFIED_FAILURE: frozenset[tuple[ActionState, ActionState]] = frozenset({
    (ActionState.FAILED, ActionState.EXECUTING),
})

TERMINAL_STATES = frozenset(s for s, targets in ALLOWED_TRANSITIONS.items() if not targets)
```

`MappingProxyType` makes the table read-only at runtime, so an importer cannot widen it in place —
the same fail-loudly instinct as `extra="forbid"` in `runtime/config.py`. A module-level assertion (or
a test, see tasks) checks the table's keys cover every `ActionState` member, so adding a state without
deciding its outgoing edges fails immediately instead of producing a silently terminal state.

`EXECUTING` deliberately omits `FAILED` (owner amendment): a synchronous MCP error response is a
completed call attempt that goes to `EXECUTED` and then `VERIFYING`, because an error reply does not
prove the physical action did not (partly) happen. `FAILED` is reachable only from `VERIFYING`.

Two edges deserve their rationale inline, because they are the whole point of the issue:
`UNKNOWN` deliberately omits `EXECUTING` (an unobserved outcome must be *verified* or *escalated*,
never blindly re-attempted), and `PROPOSED` deliberately omits `EXECUTING` (execution requires
passing through authorization).

`ActionRecord` is a frozen Pydantic model, following `CandidateAction`/`Approval`:

```python
class ActionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    action_id: str
    tool_call_id: str
    verification_id: str
    state: ActionState
    attempt: int
    created_at: datetime
    updated_at: datetime
```

Construction goes through a `new_action_record(*, now, observation_id=None, action_id=None,
tool_call_id=None, verification_id=None, id_factory=None)` factory that generates every id the caller
omits. Ids are `f"{prefix}-{id_factory()}"` with prefixes `obs-`, `act-`, `call-`, `ver-` and a
default `id_factory = lambda: secrets.token_hex(8)` (16 hex chars), echoing `propose.py`'s
`obs-<16 hex>` shape. `id_factory` is the injectable seam that makes ids deterministic in tests,
exactly like `ClientFactory` in `catalog.py`. All four ids exist from creation, so every audit line
carries four non-null ids. The creation-time `tool_call_id`/`verification_id` are **attempt 1's**
ids (owner amendment): they are not placeholders and are not replaced when attempt 1 enters
`EXECUTING` or `VERIFYING`. Callers normally pass `observation_id` from the `newton_propose_action`
result (its deterministic `obs-<sha256>`); generating one here is a fallback only.

`transition()` is the single mutation point and returns a new record rather than mutating:

```python
def transition(
    record: ActionRecord,
    new_state: ActionState,
    reason: str,
    *,
    now: datetime,
    sink: AuditSink | None = None,
    verified_failure: bool = False,
    args: dict[str, Any] | None = None,
    id_factory: Callable[[], str] | None = None,
    **ids: str,
) -> ActionRecord:
```

Order of checks, each failing before anything is written:

1. `reason.strip()` non-empty, else `ValueError`.
2. `**ids` keys are validated: `observation_id`/`action_id` are rejected outright (correlation roots
   are immutable); `tool_call_id` and `verification_id` are accepted **only** on a retry
   (`record.state is FAILED and new_state is EXECUTING`), where they override the generated pair;
   on every other transition, including `AUTHORIZED -> EXECUTING` and any entry into `VERIFYING`,
   either key raises; any other key is rejected. This keeps the issue's `**ids` signature while
   making a silent mid-attempt id rewrite impossible (owner amendment).
3. `new_state in ALLOWED_TRANSITIONS[record.state]`, else `IllegalTransition`. A record in a terminal
   state produces a message that says so, since its allowed set is empty.
4. `(record.state, new_state) in REQUIRES_VERIFIED_FAILURE` implies `verified_failure is True`, else
   `IllegalTransition` explaining that a retry requires a verified failure.
5. `now` must be aware — enforced for free by calling `canonical_timestamp(now)` when building the
   audit event, and asserted explicitly up front so the failure is the same whether or not a sink was
   passed.

Then the new record is computed: `state = new_state`, `updated_at = now`,
`attempt = record.attempt + 1` when entering `EXECUTING` (so first execution is attempt 1, a retry is
attempt 2) else unchanged. Ids are attempt-scoped (owner amendment): only a retry
`FAILED -> EXECUTING` replaces `tool_call_id` **and** `verification_id` together, each with the
supplied value or a freshly minted one. `AUTHORIZED -> EXECUTING` and `EXECUTED/UNKNOWN -> VERIFYING`
leave both unchanged. This stops a retry from reusing the previous attempt's ids, and it never lets a
call belong to attempt 2 while its verification id is still attempt 1's:

```text
creation              attempt=0  call-1  ver-1
AUTHORIZED->EXECUTING attempt=1  call-1  ver-1
EXECUTED->VERIFYING   attempt=1  call-1  ver-1
VERIFYING->FAILED     attempt=1  call-1  ver-1
FAILED->EXECUTING     attempt=2  call-2  ver-2
```

Finally, if `sink is not None`, exactly one `AuditEvent` is written — after the new record exists, so
the line always reflects a transition that actually happened. An illegal transition writes nothing.

`IllegalTransition(ValueError)` carries `from_state`, `to_state` and `allowed` attributes so a caller
can branch on it without parsing the message, following `TemplateError(ValueError)` in
`runtime/resolver.py`.

### `runtime/audit.py`

```python
class AuditSink(Protocol):
    def write(self, event: "AuditEvent") -> None: ...
```

A `Protocol`, matching `SupportsListTools`, so the sink is a seam rather than a class hierarchy.

`AuditEvent` is a frozen Pydantic model. `from`/`to` are the field names the issue asks for in the
JSON, but `from` is a Python keyword, so the fields are `from_state`/`to_state` with
`alias="from"`/`alias="to"`, `populate_by_name=True`, and serialization via
`model_dump(by_alias=True, exclude_none=True)`. Fields: `observation_id`, `action_id`,
`tool_call_id`, `verification_id`, `from_state`, `to_state`, `reason`, `attempt`,
`verified_failure`, `at` (a string, produced by `canonical_timestamp`), `args` (redacted, optional)
and `args_digest` (optional). `from_state`/`to_state` are typed `str`, not `ActionState`, which is
what keeps `audit.py` free of any `lifecycle.py` import — an `ActionState` is a `StrEnum`, so passing
one is type-correct and serializes to its value.

`args_digest` is `newton_mcp.canonical.sha256_hex(args)` over the **unredacted** args, deliberately:
that is byte-identical to `Approval.args_digest` in `action/approval.py`, which is what lets an
auditor prove a logged transition is the action an approval was granted for. The redacted `args`
mapping is what goes on disk in readable form.

Redaction:

```python
SECRET_KEY_PATTERNS = ("token", "secret", "password", "passwd", "api_key", "apikey",
                       "key", "credential", "auth", "bearer", "cookie", "session", "signature")
REDACTED = "[redacted]"
_MAX_VALUE_CHARS = 500
```

`redact_args(args)` walks mappings and lists, replaces the value of any key whose casefolded name
contains any pattern with `REDACTED`, truncates surviving strings longer than `_MAX_VALUE_CHARS`
via the `_truncate` convention from `catalog.py`, and returns a new structure — it never mutates the
input, so the executor's own `args` stay intact for the actual tool call. Matching is substring-based
and therefore over-eager on purpose (`keypad_zone` is redacted); over-redaction is the safe
direction, and the module docstring states plainly what it does not do: no value-shape detection, so
a secret under a harmless key name still reaches the log.

Two sinks:

- `MemoryAuditSink` — `events: list[AuditEvent]`. This is the default, the "disabled" mode, and what
  the test suite uses, so no test writes a file.
- `JsonlAuditSink(path)` — one line of compact JSON per event. Each `write()` opens the file with
  `open(path, "a", encoding="utf-8")`, writes
  `json.dumps(event.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False, separators=(",", ":")) + "\n"`,
  and closes. Append mode (`O_APPEND`) is the mechanism behind the append-only property: re-opening an
  existing audit file never truncates it, so lines survive a restart. Opening per write keeps the
  file consistent without an explicit flush/fsync dance and keeps the sink stateless; the volume is
  one line per state change of a physical action, not a hot path. The docstring says outright that
  this is a small, simple, single-process sink: no rotation, no retention, no fsync durability
  guarantee, and no multi-process write coordination (the `_MAX_VALUE_CHARS` cap keeps a line small,
  which makes an interleaved partial line unlikely but not impossible).

`load_audit_sink(path=None)` mirrors `load_runtime_config()`/`load_policy()` in shape but not in its
unset behaviour: reading `NEWTON_MCP_AUDIT_PATH` (constant `AUDIT_PATH_ENV_VAR`), a missing or blank
value returns `MemoryAuditSink()` — the issue's explicit "default: disabled / in-memory sink". A value
that *is* set but unusable (parent directory missing, path is a directory, not writable) raises
`ValueError` naming the variable and the path, so a typo is loud. The docstring carries this contrast
explicitly, because the difference from the allow-list loaders is intentional and a reviewer will
ask: an allow-list that silently widens is a safety hole; an audit sink is not an authority boundary,
and an operator who never set the variable never asked for a file.

### Wiring, tests and docs

`src/newton_mcp/runtime/__init__.py` re-exports the new public names alphabetically, matching the
existing file. No change to `action/`, `server.py`, `config.py` (`Settings`), or any MCP tool: nothing
here is exposed over MCP, consistent with how the resolver, policy and approval landed.

Tests go in `tests/runtime/test_lifecycle.py` and `tests/runtime/test_audit.py`. The transition table
test is genuinely table-driven: it parametrizes over every `(from, to)` pair in the full cartesian
product of `ActionState`, asserts success exactly for pairs in `ALLOWED_TRANSITIONS` and
`IllegalTransition` for every other pair. That is stronger than the acceptance criteria's "every
allowed transition plus some illegal ones": it makes the test fail if a future edit *adds* an edge
without updating the table, which is the only way a safety table stays honest. `UNKNOWN -> EXECUTING`
and `PROPOSED -> EXECUTING` also get named, standalone tests, because a named test is what a reviewer
greps for. A shared `tests/runtime/conftest.py` fixture supplies a deterministic `id_factory`
(a counter producing `0000000000000001`, ...) and a fixed aware `datetime`, so ids and timestamps in
assertions are literals.

Doc updates, all small and all required for honesty: `docs/action-runtime.md` gets a "Lifecycle,
correlation ids and audit" section and its header/`What this package does not do` lines stop claiming
"no lifecycle, no audit"; `docs/architecture.md:47` gains `UNKNOWN` and `DENIED` in the lifecycle
line; `README.md:164` is corrected the same way; `.env.example` documents `NEWTON_MCP_AUDIT_PATH`
next to the existing commented `NEWTON_MCP_RUNTIME_CONFIG` / `NEWTON_MCP_POLICY_PATH` entries, stating
that unset means disabled. Every doc keeps the existing framing: this is *this project's experimental
proposal*, not an Archetype standard, and it is mock-validated only — no live Newton, no live MCP
actuator.

## Alternatives

- **Mutable `ActionRecord` with an in-place `record.transition(...)` method.** Shorter at the call
  site, and the issue's signature is a free function anyway. Dropped because every other value type
  in this runtime is `frozen=True` (`CandidateAction`, `Approval`, `CatalogSnapshot`), and because
  in-place mutation makes "the record was left unchanged when the transition was rejected" a property
  you have to test rather than one the type system gives you for free.
- **Derive legality from code (a `match` statement, or per-state handler methods).** Rejected because
  the safety property of this issue *is* the table. A reviewer must be able to audit
  `UNKNOWN -> EXECUTING`'s absence by reading one mapping, not by tracing branches; and a data table
  can be enumerated exhaustively by a parametrized test, whereas branches cannot.
- **Sniff a verified failure out of the `reason` string** (for example, requiring a `verified:`
  prefix), which is the most literal reading of "carries a verified-failure reason". Dropped: a
  guard that depends on prose is a guard that a typo disables. The explicit `verified_failure=True`
  keyword is checked against `REQUIRES_VERIFIED_FAILURE`, and the free-text `reason` stays free text
  (still mandatory and still non-empty).
- **Put the audit log behind Python's `logging` module** with a JSON formatter and a `FileHandler`.
  Dropped: handler configuration is global process state, a host application's `logging.config` could
  silently drop or reformat audit lines, and the append-only property would then be someone else's
  handler's business. A 30-line sink the module owns end to end is both smaller and more auditable.
- **One combined `lifecycle.py` holding both the state machine and the sink.** Dropped: the issue asks
  for two files, and keeping `audit.py` ignorant of `ActionState` (typing `from`/`to` as `str`) means
  the executor in #8 can log non-lifecycle events through the same sink without an import cycle.

## Platform impact

- **Migrations:** none. No database, no queue, no persisted `ActionRecord`, no change to
  `PhysicalActionContract`, so `schemas/physical-action-contract.schema.json` is untouched and
  `tests/test_action_contract.py` keeps passing unchanged.
- **Backward compatibility:** purely additive. Two new modules, new re-exports in
  `runtime/__init__.py`, and one new optional environment variable. No existing signature, model or
  env var changes, so nothing in `server.py`, `newton/`, `action/` or the existing 15 test modules is
  affected. `pyproject.toml` needs no new dependency (`secrets`, `json`, `enum`, `types`, `os`,
  `pathlib` are stdlib; Pydantic v2 is already required), so `uv.lock` does not move.
- **Resource impact:** negligible. `transition()` is synchronous and allocation-only. The JSONL sink
  performs one `open`/`write`/`close` per state change of a physical action — a handful of lines per
  action, not a per-request hot path. Each line is bounded by the `_MAX_VALUE_CHARS` cap on redacted
  string values.
- **Risk: incomplete redaction.** Key-name matching cannot catch a secret passed under a benign key
  name, and `args_digest` is computed over unredacted args. *Mitigation:* the pattern list is
  deliberately over-eager (substring, case-insensitive); the module docstring and
  `docs/action-runtime.md` state the limitation outright rather than implying the log is
  secret-free; the digest is the same value `Approval.args_digest` already stores, so no new exposure
  class is introduced; `NEWTON_MCP_AUDIT_PATH` unset means nothing is written at all.
- **Risk: the audit file grows unbounded.** *Mitigation:* explicitly out of scope and documented as
  such (no rotation, no retention); the variable is opt-in, so an operator who enables it chooses the
  path and can point it at a rotated location.
- **Risk: concurrent or multi-process writers interleaving a line.** *Mitigation:* `O_APPEND` plus a
  single bounded `write()` per event makes this unlikely for realistic line sizes; the docstring
  states that multi-process coordination is not provided, so no one relies on a guarantee that was
  never made.
- **Risk: the table drifts from the documentation, or a new state is added with no outgoing edges by
  accident.** *Mitigation:* a test asserts `ALLOWED_TRANSITIONS` covers every `ActionState` member,
  and the exhaustive cartesian-product test fails on any added or removed edge, so the table and its
  tests cannot diverge quietly.
- **Risk: a reviewer reads the new lifecycle as a claim of working execution.** *Mitigation:* the
  modules call no tool and hold no MCP session; the updated docs keep saying that nothing here has
  been run against a live Newton account or a live MCP actuator server, and that the Physical Action
  Contract and action runtime are this project's experimental proposal.
- **Safety framing:** the states and examples stay on benign demo actions (HVAC within bounds,
  lighting, a speaker announcement, as in `examples/runtime.example.yaml` and
  `examples/policy.example.yaml`). No lock, oven, alarm, industrial start/stop or safety-system
  example is introduced anywhere in the code, tests or docs.
