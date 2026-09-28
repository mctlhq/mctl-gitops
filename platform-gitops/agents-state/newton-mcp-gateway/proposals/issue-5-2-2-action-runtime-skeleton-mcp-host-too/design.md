# Design: issue-5-2-2-action-runtime-skeleton-mcp-host-too

## Current state

What exists in the clone today:

- `src/newton_mcp/server.py` — `create_server()` builds an `MCPServer`
  (`from mcp.server.mcpserver import Context, MCPServer`, the mcp v2 rename of FastMCP) with four
  tools, all annotated `ToolAnnotations(read_only_hint=True)`. The repo is an MCP **server** only;
  nothing in it is an MCP **client**.
- `src/newton_mcp/action/contract.py` — `PhysicalActionContract` (Pydantic v2) with `goal`, `reason`,
  `confidence`, `target: Target` (`type`, `location`, `resource`, `extra="allow"`),
  `constraints: dict[str, Any]`, `risk: Risk`, `reversible`, `requires_confirmation`,
  `verification: Verification`, `evidence`. Its module docstring already points at
  `docs/action-runtime.md`, which **does not exist** in the repo (a dangling reference this proposal
  can close).
- `src/newton_mcp/action/policy.py` — `Policy.evaluate(contract) -> PolicyResult` with an ordered
  first-match-wins rule list. The house pattern for "deterministic decision + a `reason` string" that
  the resolver's `why` / rejection reasons follow.
- `src/newton_mcp/action/propose.py` — `propose_action()` returning a `ProposeActionResult` with
  `status`, the parsed object, and a list of typed `ProposeError` entries (`kind` is a `Literal[...]`
  enum of failure stages). This is the exact shape the resolver's `Resolution` mirrors.
- `src/newton_mcp/config.py` — env parsing only: `Settings.from_env()`, `NEWTON_*` names for
  project-owned variables, blank values treated as unset, explicit `ValueError`s naming the variable.
- `tests/conftest.py` — fixtures `mock_backend`, `server`, plus a `call_tool` helper that reaches into
  `server._tool_manager` because `MCPServer.call_tool` builds a `Context` without a request context.
  `tests/test_mcp_server.py` already reads `tool.input_schema` off a listed tool, confirming the mcp
  v2 attribute name (wire `inputSchema`).
- `pyproject.toml` — deps `mcp>=2.2,<3`, `pydantic>=2.7,<3`, `httpx>=0.27,<1`; dev `pytest`,
  `pytest-asyncio` with `asyncio_mode = "auto"`, `testpaths = ["tests"]`. **No YAML library.**
  `jsonschema` 4.26 is present in `uv.lock` only transitively (via `mcp`).
- `.github/workflows/ci.yml` installs with `uv sync --locked --group dev`, so `uv.lock` must be
  regenerated in the same commit as any `pyproject.toml` dependency change (`CONTRIBUTING.md` says so
  explicitly).
- `docs/architecture.md` already describes the intended Direction A pipeline
  (`capability resolver -> policy -> approval -> executor -> verifier`) and the safety table. This
  proposal implements exactly the first box.

Relevant facts about the pinned `mcp` 2.2 client API (verified by reading the published wheel, since
the clone has no installed venv):

- `mcp.client.Client` accepts a URL string (streamable-http), a `StdioServerParameters`
  (`command`, `args`, `env`, `cwd`), any `Transport`, **or — in tests — a `Server`/`MCPServer`
  instance to connect to in-process** via `mcp.client._memory.InMemoryTransport`. It is an async
  context manager; `await client.list_tools(cursor=...)` returns a `ListToolsResult` with `tools` and
  `next_cursor`.
- `mcp_types.Tool` exposes `name`, `description`, `input_schema` (wire `inputSchema`), `annotations`.

## Proposed solution

New package `src/newton_mcp/runtime/` with four modules, mirroring the issue's file list.

### `runtime/config.py` — the allow-list, validated

Pydantic v2 models, every one with `model_config = ConfigDict(extra="forbid")`. Forbidding unknown
keys is a safety property, not style: a misspelt `goal_prefixes` key that silently defaulted to
"match anything" would widen an actuator allow-list without any diagnostic.

```python
class StdioTransport(BaseModel):      kind: Literal["stdio"]; command: str; args: list[str] = []; env: dict[str, str] = {}
class HttpTransport(BaseModel):       kind: Literal["streamable-http"]; url: str
Transport = Annotated[StdioTransport | HttpTransport, Field(discriminator="kind")]

class ServerConfig(BaseModel):        name: str; transport: Transport; identity: str | None = None
                                      @property def resolved_identity(self) -> str: return self.identity or self.name

class TargetMatch(BaseModel):         type: str; locations: tuple[str, ...] = ()
class CapabilityConfig(BaseModel):    server: str; tool: str; goal_prefixes: tuple[str, ...] (min_length=1)
                                      target: TargetMatch; arguments: dict[str, Any] = {}
                                      read_tool: str | None = None; idempotent: bool = False

class RuntimeConfig(BaseModel):       servers: tuple[ServerConfig, ...]; capabilities: tuple[CapabilityConfig, ...]
```

A `@model_validator(mode="after")` on `RuntimeConfig` enforces: unique server `name`, unique resolved
identity (because `CandidateAction.server_identity` must name exactly one server), every
`capability.server` declared, and unique `(server, tool)` pairs. It also builds a
`servers_by_name` lookup used by the catalog.

`load_runtime_config(path: str | Path | None = None) -> RuntimeConfig` resolves the path from
`NEWTON_MCP_RUNTIME_CONFIG` when none is given, using the same blank-is-unset convention as
`newton_mcp/config.py::_resolve`, then `yaml.safe_load` + `RuntimeConfig.model_validate`. Errors name
the path. This needs a new runtime dependency `pyyaml>=6,<7`; `jsonschema>=4.26,<5` is promoted from
a transitive dependency of `mcp` to a declared direct one, because the resolver imports it directly.
Both land in `uv.lock` in the same commit, or CI's `uv sync --locked` fails.

### `runtime/catalog.py` — MCP host, discovery only

```python
DiscoveredTool   : name, description, input_schema: dict[str, Any], read_only_hint: bool | None
CatalogEntry     : capability: CapabilityConfig, server: ServerConfig, tool: DiscoveredTool,
                   read_tool: DiscoveredTool | None
CatalogProblem   : kind: Literal["server_unavailable", "tool_missing", "read_tool_missing"],
                   server: str, tool: str | None, detail: str
CatalogSnapshot  : entries: tuple[CatalogEntry, ...], problems: tuple[CatalogProblem, ...]
```

```python
ClientFactory = Callable[[ServerConfig], AbstractAsyncContextManager[SupportsListTools]]

class CapabilityCatalog:
    def __init__(self, config: RuntimeConfig, *, client_factory: ClientFactory | None = None,
                 connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS) -> None
    @property def snapshot(self) -> CatalogSnapshot          # empty before the first refresh
    async def refresh(self) -> CatalogSnapshot
```

`refresh()` walks servers in config order (deterministic output ordering), and per server:

1. opens the client from `client_factory` inside `anyio.fail_after(connect_timeout_seconds)`;
2. pages `list_tools()` until `next_cursor is None`, with a hard `MAX_TOOL_PAGES` guard so a
   misbehaving server cannot loop forever;
3. intersects the listing with the capabilities allow-listed for that server. Tools the server
   advertises but the allow-list does not name are dropped silently by design — they are not
   "problems", they are simply not ours. An allow-listed tool missing from the listing becomes a
   `tool_missing` problem; a configured `read_tool` missing becomes `read_tool_missing` (the
   capability still resolves, it is just not verifiable later);
4. catches `Exception` **and** `BaseExceptionGroup` (anyio task groups wrap failures) and records a
   single `server_unavailable` problem with `repr(exc)` truncated; the loop continues.

`refresh()` builds a fresh snapshot and assigns it atomically at the end, so a tool that vanished
from a server vanishes from the catalog — no merge with stale state. The default `client_factory`
maps `StdioTransport -> Client(StdioServerParameters(...))` and `HttpTransport -> Client(url)`; the
factory is the seam that makes the tests subprocess-free and network-free: they pass a factory
returning `Client(<in-process MCPServer>)`, which mcp 2.2 routes through `InMemoryTransport`.

No code path in this package calls `call_tool`. A test asserts it: the fake server's tool bodies set a
flag that must stay false.

### `runtime/resolver.py` — deterministic v0

```python
class CandidateAction(BaseModel):  server_identity, tool_name, args: dict[str, Any],
                                   read_tool: str | None, idempotent: bool, score: float, why: str
class Rejection(BaseModel):        server_identity, tool_name,
                                   stage: Literal["server_unavailable", "tool_missing", "goal_prefix",
                                                  "target_type", "target_location", "template_error",
                                                  "schema_mismatch"], detail: str
class Resolution(BaseModel):       candidates: tuple[CandidateAction, ...], rejections: tuple[Rejection, ...]

class Resolver:
    def __init__(self, catalog: CapabilityCatalog) -> None
    def resolve(self, contract: PhysicalActionContract) -> Resolution
```

`resolve()` is synchronous: it reads the last `CapabilityCatalog.snapshot` and performs no I/O, which
keeps it trivially testable and makes "no network, no LLM" structural rather than a promise. Every
configured capability is evaluated through one ordered chain, and the **first** failing stage is the
recorded rejection (so a reason is always the most specific true one):

1. `server_unavailable` / `tool_missing` — from catalog problems.
2. `goal_prefix` — no configured prefix is a prefix of `contract.goal`.
3. `target_type` — `capability.target.type != contract.target.type` (exact, case-sensitive; contract
   types are machine-produced enumerable strings such as `environment`).
4. `target_location` — if `capability.target.locations` is non-empty, `contract.target.location` must
   match one case-insensitively; a contract without a location is rejected against a
   location-constrained capability. An empty `locations` is a wildcard and matches anything.
5. `template_error` — `render_arguments(capability.arguments, contract)`.
6. `schema_mismatch` — the rendered args validated against `tool.input_schema` with `jsonschema`
   (`validator_for(schema)`, `check_schema`, then `best_match(iter_errors(args))`, the same pattern
   `mcp.client.session` uses for structured output). An invalid schema on the server side is itself a
   `schema_mismatch` rejection, never an exception out of `resolve()`.

Argument templating, in the same module, is small and explicit: a value that is exactly `"${path}"`
is replaced by the resolved contract value **with its JSON type preserved** (so
`"${constraints.desired_temperature_c}"` becomes the int `23` and passes an `integer` schema); a
string containing `${path}` among other text gets string interpolation; dicts and lists are rendered
recursively; anything else passes through as a literal. Supported roots: `goal`, `reason`,
`confidence`, `target.type`, `target.location`, `target.resource`, `constraints.<key>`,
`verification.condition`, `verification.timeout_seconds`. An unknown root or a missing
`constraints` key raises `TemplateError`, caught by the resolver into a `template_error` rejection
naming the placeholder. There is no escape sequence in v0.

Scoring is a small sum of documented module-level constants, so `why` can spell it out:

```
score = BASE (0.50)
      + GOAL_WEIGHT (0.20) * len(longest matching prefix) / len(contract.goal)
      + LOCATION_BONUS (0.20) if the capability matched an explicit location, else 0.0
      + READ_TOOL_BONUS (0.10) if a read_tool is configured and was discovered
```

An exact goal match on an explicitly located capability with a working read tool scores 1.0. Ranking
is `sorted(key=lambda c: (-c.score, c.server_identity, c.tool_name))` — stable and independent of
dict iteration order. `idempotent` deliberately does **not** affect the score: it is retry-safety
metadata that later issues consume, not a measure of match quality. `why` is a single human-readable
sentence naming the matched prefix, the location match kind, and the read-tool state.

### `runtime/__init__.py`

Re-exports the public surface (`RuntimeConfig`, `load_runtime_config`, `CapabilityCatalog`,
`CatalogSnapshot`, `Resolver`, `CandidateAction`, `Rejection`, `Resolution`) with an explicit
`__all__`, matching `newton_mcp/action/__init__.py`.

### `examples/runtime.example.yaml`

Safe demo capabilities only, per the epic's hard rule 7: an HVAC server (`set_target_temperature`
bounded by the contract's `minimum_temperature_c`/`maximum_temperature_c` constraints, read tool
`get_room_temperature`, `idempotent: true`), a lighting server (`set_light_state`, read tool
`get_light_state`), and a speaker announcement (`announce`, `idempotent: false`). Both transports are
exercised: the HVAC server over `stdio`, the lighting/speaker server over `streamable-http`. A test
loads the file and validates it, and also asserts the example contains no capability whose tool name
matches a forbidden class (lock/oven/alarm/industrial).

### Docs

`docs/action-runtime.md` (new, short) documents `runtime.yaml`, the filter chain and the scoring
constants, and closes the dangling `See docs/action-runtime.md` reference already in
`src/newton_mcp/action/contract.py`. It states plainly that the runtime is this project's proposal,
not Archetype's, and that nothing here has been run against a live Newton account. `.env.example`
gains a commented `NEWTON_MCP_RUNTIME_CONFIG` entry. `README.md` gets at most a short paragraph under
Direction A saying discovery and resolution exist and execute nothing.

## Alternatives

1. **Long-lived MCP sessions held open by the catalog** (one `Client` per server, kept alive, tools
   refreshed on `notifications/tools/list_changed`). Rejected for this issue: session lifecycle,
   reconnect and backoff are real engineering that belongs with the executor, and holding stdio
   subprocesses open in a package that executes nothing is the wrong default. Connect → `list_tools`
   → disconnect per `refresh()` is the smallest thing that satisfies the acceptance criteria; the
   `ClientFactory` seam is where a pooled implementation would later slot in.
2. **LLM-assisted capability matching** (embed the goal and the tool descriptions, rank by
   similarity). Explicitly out of scope in the issue, and wrong as a v0 default: a non-deterministic
   resolver cannot be unit-tested for "why was this actuator chosen", which is exactly the property
   physical actions need. The deterministic chain is also the ground truth a later LLM tier would be
   measured against.
3. **Reuse the tool's `inputSchema` as the only filter and drop the explicit allow-list** (match any
   server tool whose schema accepts the rendered args). Rejected on safety: schema compatibility says
   a call would be well-formed, not that the tool is allowed to be driven by a Newton observation.
   The allow-list stays the primary gate; the schema check is the last, narrowest filter.
4. **Put the runtime config in `Settings.from_env()`** alongside `NEWTON_BACKEND` and friends.
   Rejected for now: `Settings` is threaded into `create_server()`/`AppState` for the Direction B
   server, and this issue does not wire the runtime into that server. Keeping `load_runtime_config()`
   local to `runtime/` avoids touching `tests/test_config.py` and keeps two independent
   configurations independent. Recorded as an open question.
5. **JSON instead of YAML for the runtime config**, avoiding the new `pyyaml` dependency. Rejected
   because the issue names `runtime.yaml` and an operator-facing allow-list wants comments; a
   hand-rolled YAML subset parser would be worse than the dependency.

## Platform impact

- **Migrations / backward compatibility**: none. The new package is additive and imported by nothing
  that ships today; `create_server()`, all four MCP tools and `Settings` are untouched, so the
  existing suite keeps passing unchanged. No change to `PhysicalActionContract`, so
  `schemas/physical-action-contract.schema.json` stays in sync and
  `test_schema_file_is_in_sync_with_model` is unaffected.
- **Dependencies**: `pyyaml` added; `jsonschema` promoted to a declared direct dependency (already
  resolved transitively via `mcp` 2.2, so the resolution should not move). `uv.lock` must be
  regenerated with `uv lock` and committed in the same PR, otherwise CI's
  `uv sync --locked --group dev` fails. Neither package affects the Docker image size materially.
- **Resource impact**: `refresh()` opens one short-lived connection per configured server; for stdio
  servers that means spawning a subprocess per refresh in production use. Bounded by
  `connect_timeout_seconds` and `MAX_TOOL_PAGES`. Tests spawn nothing.
- **Risks and mitigations**:
  - *An MCP server is hostile or broken* (huge listings, malformed schemas, never-returning cursor):
    mitigated by the per-server timeout, the page cap, catching `BaseExceptionGroup`, and treating an
    invalid `inputSchema` as a rejection rather than an exception.
  - *The allow-list is silently widened by a config typo*: mitigated by `extra="forbid"` everywhere
    and by uniqueness validators; a bad config fails loudly at load time.
  - *A reviewer mistakes this for a working action path*: mitigated by the hard invariant that the
    package never calls `call_tool` (asserted by a test), and by docs that say resolution only.
  - *mcp 2.x client API drift* (`Client` accepting an in-process `MCPServer` is what makes the tests
    cheap): mitigated by the `ClientFactory` seam — if the constructor shape changes, one default
    factory changes, not the catalog logic. The pin stays `mcp>=2.2,<3`.
  - *No live validation*: nothing here has been run against real MCP actuator servers or a live
    Newton account. All claims stay "mock-validated" / fake-server-validated in docs and PR text.
