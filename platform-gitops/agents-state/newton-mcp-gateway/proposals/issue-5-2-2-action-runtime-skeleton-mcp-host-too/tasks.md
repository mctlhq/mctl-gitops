# Tasks: issue-5-2-2-action-runtime-skeleton-mcp-host-too

- [ ] 1. Add dependencies: `pyyaml>=6,<7` and `jsonschema>=4.26,<5` to `[project].dependencies` in
      `pyproject.toml`, then `uv lock` and commit the updated `uv.lock`.
      — DoD: `uv sync --locked --group dev && uv run pytest -q` passes locally, matching the CI step
      in `.github/workflows/ci.yml`; `jsonschema` resolution is unchanged from the transitive one.
- [ ] 2. Create `src/newton_mcp/runtime/config.py` (depends on 1) with `StdioTransport`,
      `HttpTransport`, discriminated `Transport`, `ServerConfig` (with `resolved_identity`),
      `TargetMatch`, `CapabilityConfig`, `RuntimeConfig` and `load_runtime_config()`.
      — DoD: every model sets `ConfigDict(extra="forbid")`; `RuntimeConfig`'s after-validator rejects
      duplicate server names, duplicate resolved identities, unknown `capability.server` references
      and duplicate `(server, tool)` pairs; `load_runtime_config()` reads
      `NEWTON_MCP_RUNTIME_CONFIG` when no path is given, treats blank as unset, and raises
      `ValueError` naming the variable/path for unset, missing-file and unparseable-YAML cases.
- [ ] 3. Create `examples/runtime.example.yaml` (depends on 2) — DoD: HVAC (stdio, `idempotent: true`,
      `read_tool: get_room_temperature`, bounded temperature arguments), lighting and speaker
      announcement (streamable-http) capabilities only; no lock, oven, alarm, industrial or safety
      tool anywhere; file validates into a `RuntimeConfig`.
- [ ] 4. Create `src/newton_mcp/runtime/catalog.py` (depends on 2) with `DiscoveredTool`,
      `CatalogEntry`, `CatalogProblem`, `CatalogSnapshot`, the `ClientFactory` type, the default
      factory (`StdioServerParameters` for `stdio`, URL string for `streamable-http`) and
      `CapabilityCatalog.refresh()`.
      — DoD: `refresh()` pages `list_tools` to exhaustion under `MAX_TOOL_PAGES`, keeps only
      allow-listed tools that exist, records `tool_missing` / `read_tool_missing` /
      `server_unavailable` problems, catches `Exception` only (never `BaseExceptionGroup`) per
      server, applies one `anyio.fail_after(server_timeout_seconds)` around the full per-server
      cycle (connect + initialize + every `list_tools` page), records observed `serverInfo`
      (`name`, `version`) as metadata only, replaces the snapshot atomically, and returns an
      empty snapshot before the first refresh. No `call_tool` anywhere in the module.
- [ ] 5. Create `src/newton_mcp/runtime/resolver.py` (depends on 4) with `render_arguments()` +
      `TemplateError`, `CandidateAction`, `Rejection`, `Resolution`, `Resolver.resolve()` and the
      scoring constants `BASE_SCORE`, `GOAL_WEIGHT`, `LOCATION_BONUS`, `READ_TOOL_BONUS`.
      — DoD: the ordered filter chain (availability -> goal prefix -> target type -> target location
      -> template -> `jsonschema` input-schema check) records the first failing stage as the
      rejection; whole-string placeholders preserve JSON type; candidates sort by
      `(-score, server_identity, tool_name)`; `resolve()` is synchronous and performs no I/O;
      `idempotent` does not contribute to the score.
- [ ] 6. Create `src/newton_mcp/runtime/__init__.py` (depends on 2, 4, 5) — DoD: explicit `__all__`
      re-exporting `RuntimeConfig`, `load_runtime_config`, `CapabilityCatalog`, `CatalogSnapshot`,
      `CatalogProblem`, `Resolver`, `CandidateAction`, `Rejection`, `Resolution`, in the style of
      `src/newton_mcp/action/__init__.py`.
- [ ] 7. Create `tests/runtime/conftest.py` (depends on 4) with a `build_fake_server(name, tools)`
      helper returning an in-process `MCPServer` (`mcp.server.mcpserver`) whose tools record any
      invocation, and an `in_memory_factory(servers_by_name)` `ClientFactory` returning
      `Client(<MCPServer>)`.
      — DoD: no subprocess and no socket is created by any runtime test; a server name absent from
      the mapping raises inside the factory so the catalog records `server_unavailable`.
- [ ] 8. Write the test modules listed under Tests (depends on 2-7) in `tests/runtime/`.
      — DoD: `uv run pytest -q` green; every acceptance criterion in `requirements.md` maps to at
      least one test.
- [ ] 9. Add `docs/action-runtime.md` and a commented `NEWTON_MCP_RUNTIME_CONFIG` block in
      `.env.example`; add at most one short paragraph to `README.md` under Direction A (depends on
      2-6).
      — DoD: the doc describes `runtime.yaml`, the filter chain and the scoring constants, states that
      the contract and runtime are this project's experimental proposal (not Archetype's) and that
      nothing is executed and nothing was validated against live servers or a live Newton account;
      the dangling `See docs/action-runtime.md` reference in `src/newton_mcp/action/contract.py` now
      resolves.
- [ ] 10. Final pass (depends on all): `uv sync --locked --group dev && uv run pytest -q`, confirm
      `grep -rn "call_tool" src/newton_mcp/runtime/` returns nothing, and confirm no Archetype
      endpoint, parameter or model id was added anywhere.

## Tests

`tests/runtime/` (pytest `asyncio_mode = "auto"` is already set in `pyproject.toml`).

- [ ] T1. `test_config.py`: a minimal valid config loads; `identity` defaults to `name`; an explicit
      `identity` is kept.
- [ ] T2. `test_config.py`: unknown key anywhere (server, transport, capability, target) is rejected
      by `extra="forbid"`; duplicate server names, duplicate resolved identities, a capability naming
      an undeclared server, and a duplicate `(server, tool)` pair are each rejected with an error
      naming the offender.
- [ ] T3. `test_config.py`: `load_runtime_config()` with `NEWTON_MCP_RUNTIME_CONFIG` unset or blank
      raises naming the variable; a missing file and malformed YAML each raise naming the path.
- [ ] T4. `test_config.py`: `examples/runtime.example.yaml` validates into a `RuntimeConfig`, and no
      tool or goal prefix in it matches the forbidden classes (lock, oven, alarm, industrial
      start/stop, safety).
- [ ] T5. `test_catalog.py`: a fake server advertising `set_target_temperature`,
      `get_room_temperature` and a non-allow-listed `reboot_gateway` yields catalog entries only for
      allow-listed tools; `reboot_gateway` appears neither as an entry nor as a problem.
- [ ] T6. `test_catalog.py`: an allow-listed tool missing from the listing is reported as a
      `tool_missing` problem while the remaining entries stay usable; a missing `read_tool` is
      reported as `read_tool_missing` and the entry still resolves.
- [ ] T7. `test_catalog.py`: a server whose factory raises, and a second one that raises an ordinary
      error inside a task group (surfacing as an `ExceptionGroup`), each produce a
      `server_unavailable` problem. `refresh()` does not raise, and the other server's tools are
      still discovered.
- [ ] T7a. Cancellation propagates (owner amendment). Run `refresh()` in a task group or cancel
      scope and cancel it while a fake server's `list_tools` is blocked on an `anyio.Event`. The
      cancellation propagates: the scope reports `cancelled_caught`, and `refresh()` does not
      return a snapshot. No problem is recorded, and `catalog.snapshot` still equals the snapshot
      from the previous successful refresh. Mutation check: adding `BaseExceptionGroup` (or
      `BaseException`) to the catch must fail this test.
- [ ] T7b. A hung server does not block the others (owner amendment). With
      `server_timeout_seconds` small, a fake server that completes initialize and then never
      answers `list_tools` (or answers page 1 and hangs on page 2) produces `server_unavailable`
      whose detail indicates a timeout, and a second, healthy server's allow-listed tools are still
      discovered in the same `refresh()`. A variant where the client factory itself hangs before
      initialize gives the same result, which shows the deadline covers connect, initialize and
      pagination.
- [ ] T7c. Observed `serverInfo` is metadata only (owner amendment). The snapshot's `server_info`
      carries the fake server's `name`, and `version` as the server reports it. Renaming the fake
      server's `serverInfo.name` changes no `CandidateAction` (same `server_identity`, `score` and
      ranking).
- [ ] T8. `test_catalog.py`: `refresh()` picks up changes — a tool added to the fake server between
      two refreshes appears, a tool removed disappears, and the snapshot before any refresh is empty.
- [ ] T9. `test_catalog.py`: the fake server's tool bodies flip a module-level flag when invoked; after
      a full `refresh()` the flag is still false (nothing but `list_tools` was called).
- [ ] T10. `test_resolver.py`: with two matching capabilities (one exact-goal + explicit location +
      read tool, one prefix-only + wildcard location), both are returned, the first ranks higher, and
      the ordering is stable across repeated runs.
- [ ] T11. `test_resolver.py`: a capability whose rendered args violate the tool's `input_schema`
      (e.g. a string where the schema demands `integer`, and a missing `required` property) is
      rejected with stage `schema_mismatch` and a detail carrying the validation message.
- [ ] T12. `test_resolver.py`: a contract with no matching capability returns
      `Resolution(candidates=(), rejections=...)` with one rejection per configured capability, each
      naming the stage — covering `goal_prefix`, `target_type`, `target_location`,
      `server_unavailable` and `tool_missing`.
- [ ] T13a. `test_resolver.py`: `"${verification.condition}"` and
      `"${verification.timeout_seconds}"` are rejected as unknown roots with a `template_error`
      naming the placeholder (owner amendment).
- [ ] T13. `test_resolver.py`: `render_arguments()` preserves JSON type for a whole-string placeholder
      (`"${constraints.desired_temperature_c}"` -> `23`), interpolates an embedded placeholder into a
      string, renders nested dicts/lists, and a placeholder naming a missing constraint or an unknown
      root produces a `template_error` rejection naming the placeholder.
- [ ] T14. `test_resolver.py`: `CandidateAction` carries `read_tool`, `idempotent` and a non-empty
      `why`; two capabilities identical except for `idempotent` receive the same score.
- [ ] T15. `test_resolver.py`: resolving against the `examples/runtime.example.yaml` capabilities and
      the repo's own example contract (`src/newton_mcp/action/examples.py::MOCK_CONTRACT_EXAMPLE`
      loaded as a `PhysicalActionContract`) returns at least one candidate — an end-to-end check that
      the shipped example and the shipped contract actually fit each other.

## Rollback

The change is purely additive: `src/newton_mcp/runtime/`, `tests/runtime/`,
`examples/runtime.example.yaml`, `docs/action-runtime.md`, plus dependency lines in `pyproject.toml`
/ `uv.lock` and doc-only edits to `.env.example` and `README.md`. Nothing imports the new package at
runtime — `src/newton_mcp/server.py`, `create_server()` and `Settings` are untouched — so the shipped
MCP server behaves identically with or without it.

- Revert the merge commit (`git revert -m 1 <sha>`): the gateway returns to its current state with no
  migration, no data and no config to clean up.
- Partial rollback if only the dependencies are the problem: drop the two entries from
  `pyproject.toml`, re-run `uv lock`, and delete `src/newton_mcp/runtime/` plus `tests/runtime/`;
  nothing else references them.
- If the mcp 2.x client API turns out to differ from the published 2.2.0 wheel, only the default
  `ClientFactory` in `runtime/catalog.py` needs fixing; the tests use their own factory and stay
  green, which localises the blast radius.
