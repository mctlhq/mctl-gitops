# Design: issue-9-2-5-smart-home-testbed-end-to-end-closed

## Current state

Everything this demo needs already exists in `src/newton_mcp/`, unit-tested with in-process fakes.
What does not exist is any caller that composes it.

**Contract and proposal.** `src/newton_mcp/action/contract.py` defines `PhysicalActionContract`
v0.2 (`version` pinned `^0\.2$`), with `Verification(condition: Condition, timeout_seconds=300,
retry_limit=0)`. `src/newton_mcp/action/propose.py::propose_action(backend, *, model, text_events,
json_events, allowed_goals, observation_id, max_new_tokens)` returns a `ProposeActionResult` with
`status`, `contract`, `backend` and a deterministic `observation_id` (`obs-<16 hex>`).
`src/newton_mcp/newton/mock.py::MockNewtonBackend` detects the contract prompt marker and returns
`newton_mcp.action.examples.MOCK_CONTRACT_EXAMPLE` with `reason` prefixed `[mock] `: goal
`reduce_room_temperature`, `target {type: environment, location: kitchen}`, `constraints
{desired_temperature_c: 23, minimum_temperature_c: 20, maximum_temperature_c: 25}`, `risk: low`,
`confidence: 0.96`, `verification.condition {path: "temperature_c", op: "le", value: 24}`,
`timeout_seconds: 600`, `retry_limit: 1`. That is exactly the kitchen-cooling scenario this issue
asks for, so the demo needs no bespoke contract source in mock mode.

**Allow-list and discovery.** `src/newton_mcp/runtime/config.py` defines `RuntimeConfig` /
`ServerConfig` / `CapabilityConfig` (`extra="forbid"` everywhere), `load_runtime_config(path)`, and
the `resolved_identity` / `transport_fingerprint` / `binding_identity` properties an approval binds
to. `src/newton_mcp/runtime/catalog.py::CapabilityCatalog(config, *, client_factory,
server_timeout_seconds)` connects through a `ClientFactory` seam (`default_client_factory` maps
`stdio`/`streamable-http` to `mcp.Client`), calls `list_tools` only, and records
`DiscoveredTool.read_only_hint`. `src/newton_mcp/runtime/resolver.py::Resolver.resolve(contract)`
renders `${target.*}` / `${constraints.*}` templates, validates the rendered args against the
discovered tool's `input_schema`, and returns ranked `CandidateAction`s plus explicit `Rejection`s.

**Policy, approval, lifecycle, execution, verification, audit.**
`src/newton_mcp/action/policy.py::Policy.evaluate(contract, candidate)` returns
`auto|confirm|deny`; an `arg_ranges` violation denies immediately naming the argument.
`src/newton_mcp/action/approval.py::create_approval(candidate, *, action_id, policy_version,
approved_by, approved_at, expires_at, approval_id)` binds to `candidate.server_binding_identity`.
`src/newton_mcp/runtime/lifecycle.py` provides `new_action_record(now=..., observation_id=...,
id_factory=...)` and the guarded `transition(record, state, reason, *, now, sink, ...)`;
`ALLOWED_TRANSITIONS` has no `UNKNOWN -> EXECUTING` and no `PROPOSED -> EXECUTING` edge.
`src/newton_mcp/runtime/executor.py::Executor` plus `run_action(candidate, contract, record, *,
approval, policy_version, executor, verifier, now_fn)` implement the retry rule and always end
`SUCCEEDED` or `ESCALATED`; `run_action` raises `ValueError` unless `executor.sink is
verifier.sink`. `src/newton_mcp/runtime/verifier.py::Verifier(catalog, *, client_factory,
poll_interval_seconds, read_timeout_seconds, sink, clock, sleep, id_factory)` polls only
`candidate.read_tool` with `candidate.read_args`, turns a result into an observation via
`observation_from_result` (structured mapping preferred), and evaluates
`action/conditions.py::evaluate`. `src/newton_mcp/runtime/audit.py::JsonlAuditSink` appends one
redacted JSON line per accepted transition with all four correlation ids.

**Existing examples and their test precedent.** `examples/runtime.example.yaml` and
`examples/policy.example.yaml` are generic (an `hvac-controller` over stdio, a `home-bridge` over
HTTP). `tests/runtime/test_config.py::test_example_runtime_config_is_valid_and_safe` loads the
example and asserts no capability tool/goal string contains any of
`_FORBIDDEN_SUBSTRINGS = ("lock", "oven", "alarm", "industrial", "safety", "start", "stop")`;
`tests/test_policy_yaml.py` asserts the example policy loads. `tests/runtime/conftest.py` shows the
in-process fake pattern this design reuses: `build_fake_server(name, [FakeToolSpec(...)]) ->
MCPServer`, `in_memory_factory({name: server})` returning `mcp.Client(server)` (no subprocess, no
socket), `DeterministicClock` (a `clock`/`sleep` pair where `sleep` advances a counter instead of
waiting), and a counter-based `id_factory`. CI (`.github/workflows/ci.yml`) runs
`uv sync --locked --group dev && uv run pytest -q`, so no new dependency may be introduced.
`pyproject.toml` sets `testpaths = ["tests"]` and `asyncio_mode = "auto"`; only `src/newton_mcp` is
packaged, so `examples/` is never importable as a module.

## Proposed solution

Five new files under `examples/smart-home/`, one new test module, and documentation. No file under
`src/newton_mcp/` changes.

### `examples/smart-home/fake_alice.py`

An in-process fake MCP actuator plus the simulated room, built with `mcp.server.mcpserver.MCPServer`
exactly as `tests/runtime/conftest.py::build_fake_server` does.

- `RoomState` — a small Pydantic v2 model (hard rule 4): `room`, `temperature_c`, `occupancy`,
  `ac_online`, `ac_target_c`, `light_on`, `brightness_pct`, plus `cooling_step_c` (how much a single
  read advances the room toward its target) and `announcements: list[str]`.
- `build_fake_alice(state: RoomState, *, call_log: list[tuple[str, dict]] | None = None) ->
  MCPServer` registering exactly five tools:
  - `get_room_state(room: str) -> dict` — annotated `ToolAnnotations(read_only_hint=True)` (hard
    rule 5). Returns a mapping whose **top-level `temperature_c`** is the path
    `MOCK_CONTRACT_EXAMPLE`'s condition reads, alongside `room`, `occupancy`, `ac_online`,
    `ac_target_c`, `light_on`, `brightness_pct`. Each call is where the simulated delay lives: if
    the AC is online and a target has been set, the reported `temperature_c` moves one
    `cooling_step_c` toward `ac_target_c` per read, so the room reaches the target after a couple of
    polls instead of instantly. If `ac_online` is false, `temperature_c` never moves.
  - `set_ac_temperature(room: str, target_temperature_c: int) -> dict` — idempotent absolute set.
    Records the target and returns `{"accepted": true, ...}` **whether or not the AC is online**.
    That is the entire point of the offline mode: a digitally successful call with no physical
    effect, which is the failure this project exists to catch. Its declared schema accepts any
    integer, so the 20-25 C band is enforced by `policy.yaml` alone and the policy-denial test
    cannot be satisfied accidentally by a resolver `schema_mismatch`.
  - `set_light_state(room: str, on: bool) -> dict` — idempotent absolute set.
  - `set_light_brightness(room: str, brightness_pct: int) -> dict` — idempotent absolute set.
  - `announce(message: str) -> dict` — **not** idempotent, and deliberately has no read counterpart,
    so the verifier's "no `read_tool` -> `ESCALATED`" path is reachable.
- `in_process_factory(server: MCPServer) -> ToolClientFactory` — returns `mcp.Client(server)` for
  any `ServerConfig`, ignoring its transport. This is the same seam `Executor`, `Verifier` and
  `CapabilityCatalog` all accept, which is why mock mode needs no socket and no subprocess.
- `call_log` records `(tool_name, arguments)` per invocation, so tests can assert the exact number
  of actuator calls (the non-idempotent single-call criterion).

### `examples/smart-home/runtime.yaml` and `policy.yaml`

One server, `alice`, transport `streamable-http` with the placeholder URL
`https://alice.invalid/mcp` (RFC 2606, non-resolvable, names no real host). Four capabilities, each
with an explicit `idempotent:` value and `read_tool: get_room_state` where verification is possible:

| goal prefixes | tool | args | read_tool | idempotent |
|---|---|---|---|---|
| `reduce_room_temperature`, `raise_room_temperature` | `set_ac_temperature` | `room: ${target.location}`, `target_temperature_c: ${constraints.desired_temperature_c}` | `get_room_state` | `true` |
| `turn_on_light`, `turn_off_light` | `set_light_state` | `room: ${target.location}`, `on: ${constraints.desired_on}` | `get_room_state` | `true` |
| `set_light_brightness` | `set_light_brightness` | `room: ${target.location}`, `brightness_pct: ${constraints.desired_brightness_pct}` | `get_room_state` | `true` |
| `announce` | `announce` | `message: ${reason}` | (none) | `false` |

`policy.yaml`: `policy_version: "smart-home.v1"`, `default: deny`, rules in file order — AC
reduce/raise (`tool_name: set_ac_temperature`, `max_risk: low`, `min_confidence: 0.8`,
`arg_ranges: {target_temperature_c: {min: 20, max: 25}}`, `decision: auto`), lighting on/off
(`auto`), brightness (`arg_ranges: {brightness_pct: {min: 0, max: 100}}`, `auto`), announcements
(`decision: confirm`). Because `Policy._match_rule` treats an out-of-range `arg_ranges` value as a
*terminal* deny, a `target_temperature_c` of 30 matches the AC rule's earlier predicates and is
denied immediately — it cannot fall through to a broader later rule. No tool name or goal prefix
contains any `_FORBIDDEN_SUBSTRINGS` term, so the smart-home files pass the same safety assertion
the generic examples already face.

### `examples/smart-home/demo.py`

A single-scenario CLI, small and explicit, with `run_demo()` factored out so tests can drive it
in-process:

```
parse args -> build backend -> propose_action -> new_action_record -> catalog.refresh
-> resolver.resolve -> policy.evaluate -> approve -> transition(AUTHORIZED|DENIED)
-> run_action(executor, verifier) -> print summary
```

- **Flags.** `--mock` (default) / `--real` (mutually exclusive); `--ac-offline` (the failure path);
  `--audit-path PATH` (default `examples/smart-home/demo-audit.jsonl`, gitignored) and
  `--overwrite` (truncate before the run — the sink itself only ever appends);
  `--deterministic` (counter `id_factory` + a fixed stepped `now_fn`, used to record
  `trace.jsonl`); `--force-desired-temperature-c N` (a clearly labelled testbed override of the
  proposed contract's constraint, used to demonstrate and test the policy denial).
- **Mock mode.** Backend `MockNewtonBackend()`; one `fake_alice` server; `client_factory =
  in_process_factory(fake)` passed to `CapabilityCatalog`, `Executor` and `Verifier`;
  `Verifier(clock=sim.clock, sleep=sim.sleep, poll_interval_seconds=60.0)` with a simulated clock
  (`sleep` advances a float, never waits), so the contract's 600 s `timeout_seconds` is consumed in
  about ten simulated polls and the failure path finishes in milliseconds. A `confirm` decision is
  auto-approved with an explicitly mock-labelled `approved_by`.
- **Real mode.** Backend from `newton_mcp.newton.api.build_backend(Settings.from_env())`
  (`ATAI_API_KEY` / `ATAI_API_ENDPOINT`); the Alice endpoint from `ALICE_MCP_URL`, applied by
  rebuilding the loaded `RuntimeConfig` with `model_copy`/re-validation so the committed placeholder
  URL is replaced before the catalog is built (`runtime.yaml` has no env interpolation, and adding
  one to `src/` is out of scope). Missing variables fail loudly naming the variable. Real mode uses
  the real `anyio` clock, `default_client_factory`, and prompts on stdin for a `confirm` decision.
  Never selected by any test.
- **Audit.** One `JsonlAuditSink(audit_path)` instance is passed as `sink=` to both the `Executor`
  and the `Verifier` (`run_action` requires the identical object) and is also used for the demo's
  own `PROPOSED -> AUTHORIZED` / `PROPOSED -> DENIED` transition, which no module in `src/` performs.
- **Exit codes**, documented in both READMEs: `0` `SUCCEEDED`, `3` `ESCALATED`, `4` `DENIED`, `1`
  unexpected error. `run_demo()` returns a small frozen `DemoResult` (terminal state, tool-call
  count, observation count, the four ids, audit path) so tests assert on values rather than parsing
  stdout.
- **Printed trace** labels mock provenance at every step: the proposal envelope's
  `backend: "mock"`, the contract's `[mock] ` reason, and an explicit "actuator: in-process fake
  (fake_alice), not a real device" line. Resolution prints every candidate (`score`, `why`) and every
  rejection (`stage`, `detail`).

### `examples/smart-home/trace.jsonl`

A recorded mock success run, regenerated by one documented command
(`... demo.py --mock --deterministic --audit-path examples/smart-home/trace.jsonl --overwrite`).
Five lines: `PROPOSED->AUTHORIZED`, `AUTHORIZED->EXECUTING`, `EXECUTING->EXECUTED`,
`EXECUTED->VERIFYING`, `VERIFYING->SUCCEEDED`, each carrying all four correlation ids plus
`from`/`to`, `reason`, `attempt`, `verified_failure`, canonical `at`, and (on the `EXECUTING` line)
redacted `args` with `args_digest`. No credential, no API key, no real device id or hostname —
arguments are `room: "kitchen"` and `target_temperature_c: 23`.

### `tests/test_demo.py`

Loaded with `importlib.util.spec_from_file_location` (examples are not an importable package), so
the tests call `demo.run_demo(...)` and `fake_alice` directly. One additional test runs the literal
documented command as a subprocess with `sys.executable` and asserts exit code 0, so the README's
command itself is covered. Mock mode only.

### Documentation

`examples/smart-home/README.md` carries the full walkthrough; the root `README.md` gains a short
"Demo" section with the exact command and a short excerpt of both paths, keeping the
"mock-validated" and "this project's experimental proposal" wording. `docs/action-runtime.md` gains
one cross-reference sentence pointing at the testbed.

## Alternatives

1. **Wire the demo into `src/newton_mcp/` (e.g. a `newton_mcp.demo` module or new MCP tools).**
   Dropped: the acceptance criteria require `src/newton_mcp/` to contain nothing Alice-specific, and
   `docs/action-runtime.md` explicitly states the runtime exposes itself as no MCP tool and does not
   wire into `create_server()`/`Settings`. Keeping the demo in `examples/` also keeps the wheel
   (`packages = ["src/newton_mcp"]`) unchanged.
2. **Run `fake_alice` as a real subprocess over stdio, or bind it to a local HTTP port.** Dropped:
   it would make CI depend on process spawning and port availability, and it contradicts the
   established repo pattern — every existing runtime test connects in-process through `mcp.Client(
   MCPServer)` with the `ClientFactory` seam. The fingerprint/binding code paths are identical
   either way, because `binding_identity` is computed from the *declared* transport in
   `runtime.yaml`, not from how the client actually connected.
3. **Use the real `anyio` clock in the verifier and shorten the contract's
   `verification.timeout_seconds`.** Dropped: the contract comes from `MockNewtonBackend`
   (`timeout_seconds: 600`), so shortening it would mean either editing
   `action/examples.py::MOCK_CONTRACT_EXAMPLE` (which is asserted byte-equivalent to
   `examples/physical-action.json` and is not this issue's to change) or hand-authoring a contract in
   the demo and bypassing `propose_action`, which is the very link the demo is supposed to prove. The
   `clock`/`sleep` seam already exists for exactly this reason.
4. **Model the room's settling delay in wall-clock seconds.** Dropped: it makes the success path
   either slow or flaky depending on scheduling. Advancing the room one step per `get_room_state`
   read is deterministic, still shows the verifier polling more than once, and behaves identically
   under a simulated or a real clock.
5. **Add an env-interpolation feature to `runtime/config.py` so `runtime.yaml` can carry
   `${ALICE_MCP_URL}`.** Dropped: it widens an authority-boundary loader (`extra="forbid"`,
   fail-loudly, no defaults) for the benefit of one example, and real mode is opt-in and
   never CI-exercised. Overriding the parsed `RuntimeConfig` inside `demo.py` keeps the change local
   and reviewable.

## Platform impact

- **Migrations / backward compatibility.** None. No schema, model, state table, env-var contract or
  public symbol changes. `schemas/physical-action-contract.schema.json` and
  `action/examples.py::MOCK_CONTRACT_EXAMPLE` are untouched, so
  `tests/test_action_contract.py`'s sync assertions keep passing.
- **Dependencies / CI.** No new dependency, so `uv.lock` stays byte-unchanged and
  `uv sync --locked --group dev` keeps passing. `pyproject.toml` needs no change
  (`testpaths = ["tests"]` already collects `tests/test_demo.py`). The docker job is unaffected.
  `.gitignore` gains `examples/smart-home/demo-audit.jsonl`.
- **Resource impact.** The demo and its tests are in-process: no socket, no subprocess (except the
  one deliberate `sys.executable` smoke test), no credential, no network. With a simulated clock the
  failure path performs about a dozen in-process read calls; expected added CI time is a couple of
  seconds.
- **Risk: the demo appears to validate a live integration.** Mitigation: the printed trace labels
  the mock backend, the `[mock] ` contract reason and the fake actuator explicitly; both READMEs and
  the new docs sentence say "mock-validated"; `--real` is opt-in, env-only and never run in CI.
- **Risk: `trace.jsonl` drifts from what the demo actually emits.** Mitigation: a test parses the
  committed file and asserts the exact transition chain, four non-empty ids per line and the absence
  of secret-looking keys; the README documents the one-line regeneration command; `--deterministic`
  makes regeneration stable.
- **Risk: the fake's tool shapes diverge from the real Alice server**, so `--real` fails on first
  contact. Mitigation: recorded as open question 1, stated in `examples/smart-home/README.md`, and
  contained by design — the shapes live only in `fake_alice.py` and `runtime.yaml`, both under
  `examples/`, so adapting them touches no runtime code.
- **Risk: a future `src/` change silently breaks the composed loop.** Mitigation: that is precisely
  what `tests/test_demo.py` now guards — it is the first test in the repo that exercises
  propose -> resolve -> policy -> approve -> execute -> verify as one chain.
- **Risk: an implementer "fixes" a composition problem inside `src/newton_mcp/`.** Mitigation: a
  test asserts `src/newton_mcp/` contains no Alice-specific string; any genuine `src/` defect found
  while composing the loop should be reported rather than patched under this issue.
