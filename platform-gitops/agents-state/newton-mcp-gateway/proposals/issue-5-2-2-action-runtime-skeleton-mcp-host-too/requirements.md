# Action runtime skeleton: MCP host, tool discovery and deterministic capability resolver

> **Amended at owner review (before approval):**
> (1) Cancellation of `refresh()` propagates. The catalog catches only `Exception`, never
> `BaseExceptionGroup`.
> (2) `server_timeout_seconds` bounds the whole per-server discovery cycle: connect, initialize,
> and every `list_tools` page. A hung server cannot block discovery of the others.
> (3) `verification.*` is removed from the template roots.
> (4) The catalog records the server's observed MCP `serverInfo` (`name`, `version`) as metadata
> only. Transport fingerprints, canonical server identity and approval-binding semantics are
> deliberately left to #6, where they become a security boundary.

## Context

`newton-mcp-gateway` today only implements Direction B: an MCP *server* that exposes Newton as a
capability (`src/newton_mcp/server.py`, four read-only tools). Direction A — MCP as Newton's action
boundary — exists as a proposal plus two building blocks: the Physical Action Contract
(`src/newton_mcp/action/contract.py`) and the deterministic policy engine
(`src/newton_mcp/action/policy.py`). `newton_propose_action` (`src/newton_mcp/action/propose.py`,
issue #4) produces a validated contract and nothing else: the contract says *what* should happen in
the physical world, and no code in the repo yet knows *how* any of it could be done.

This proposal adds the missing link as a new package `src/newton_mcp/runtime/`: the gateway process
also becomes an MCP **host/client**. It reads a `runtime.yaml` allow-list, connects to the configured
MCP servers, discovers their tools with `list_tools`, and resolves a `PhysicalActionContract` into a
ranked list of concrete `CandidateAction`s. It executes nothing — no `call_tool`, no policy
evaluation, no approval, no lifecycle, no audit, no LLM. Discovery and resolution only. This matters
because every later phase (policy binding, approval tied to an exact normalised action, execution,
verification) needs one deterministic, explainable answer to "which tool calls could satisfy this
contract, and why were the others rejected?" — and a resolver that cannot explain a rejection cannot
be trusted with a physical actuator.

The Physical Action Contract and this action runtime are this project's experimental proposal, not
an Archetype standard, and nothing here touches Archetype's API surface.

## User stories

- AS an operator of the gateway I WANT to declare, in one reviewable `runtime.yaml` allow-list, which
  MCP server + tool pairs may ever serve which goals SO THAT no tool becomes reachable to a physical
  action just because some MCP server happens to advertise it.
- AS an operator I WANT the capability catalog to survive a server that is down or that dropped a
  tool SO THAT one unreachable home-automation server does not take the whole runtime with it.
- AS an integrator I WANT a deterministic, LLM-free resolver that returns ranked candidates with a
  `why` SO THAT resolution is reproducible, reviewable and testable before any physical action is
  ever executed.
- AS an integrator I WANT every rejected capability to come back with an explicit reason SO THAT an
  empty result is diagnosable ("wrong location", "argument schema mismatch") instead of silent.
- AS a reviewer I WANT the runtime tested against a fake in-process MCP server SO THAT the test suite
  spawns no subprocess and touches no network.

## Acceptance criteria (EARS)

Configuration

- WHEN `load_runtime_config()` is called with no explicit path THE SYSTEM SHALL read the config path
  from `NEWTON_MCP_RUNTIME_CONFIG` and SHALL raise a `ValueError` naming that variable if it is unset
  or blank.
- WHEN the configured file does not exist or is not parseable YAML THE SYSTEM SHALL raise an error
  naming the path and the underlying parse error, and SHALL NOT fall back to a default config.
- WHEN a `runtime.yaml` declares a server THE SYSTEM SHALL require a unique `name` and exactly one
  transport: `stdio` (with `command`, optional `args`, optional `env`) or `streamable-http` (with
  `url`).
- IF a server omits `identity` THEN THE SYSTEM SHALL default its identity to its `name`.
- IF two servers resolve to the same identity THEN THE SYSTEM SHALL reject the config, because
  `CandidateAction.server_identity` must name exactly one server.
- WHEN a capability entry is validated THE SYSTEM SHALL require `server`, `tool`, at least one
  `goal_prefixes` entry and a `target.type`, and SHALL accept optional `target.locations`,
  `arguments`, `read_tool` and `idempotent` (default `false`).
- IF a capability references a `server` name that is not declared, or two capabilities declare the
  same `(server, tool)` pair, THEN THE SYSTEM SHALL reject the config with an error naming the
  offending entry.
- WHILE validating any runtime config model THE SYSTEM SHALL forbid unknown keys, so that a misspelt
  key can never silently widen an allow-list.
- WHEN `examples/runtime.example.yaml` is loaded THE SYSTEM SHALL validate it into a `RuntimeConfig`,
  and that example SHALL contain only safe demo capabilities (lights, HVAC within bounds, speaker
  announcements) — never locks, ovens, alarms, industrial start/stop or safety systems.

Catalog

- WHEN `CapabilityCatalog.refresh()` runs THE SYSTEM SHALL connect to every configured server as an
  MCP client, call `list_tools` (following pagination cursors), and disconnect.
- WHILE the runtime is in the scope of this proposal THE SYSTEM SHALL issue no MCP request other than
  the connection handshake and `list_tools` — in particular never `tools/call`.
- WHEN a server's listing is received THE SYSTEM SHALL keep only tools that are allow-listed in
  `capabilities` for that server and SHALL discard every other advertised tool.
- IF an allow-listed tool is absent from a server's listing THEN THE SYSTEM SHALL record a
  `tool_missing` problem naming server and tool, and SHALL keep the rest of the catalog usable.
- IF a server cannot be connected, times out, or fails during listing THEN THE SYSTEM SHALL record a
  `server_unavailable` problem carrying the error text and SHALL NOT propagate the exception out of
  `refresh()`. Only `Exception` and its subclasses, including `ExceptionGroup`, are converted into
  problems.
- WHEN the task running `refresh()` is cancelled THE SYSTEM SHALL propagate the cancellation and
  SHALL NOT record it as a problem or swallow it. The catalog SHALL NOT catch `BaseException`,
  `BaseExceptionGroup` or the backend's cancellation exception. The previous snapshot stays in
  place, because an aborted refresh never assigns.
- WHILE discovering one server THE SYSTEM SHALL bound the entire per-server cycle with a single
  `server_timeout_seconds` deadline: client connect, the MCP initialize handshake, and every
  `list_tools` page. IF that deadline expires THEN THE SYSTEM SHALL record `server_unavailable` for
  that server and continue with the remaining servers, so a server that connects and then hangs
  cannot block discovery of the others.
- WHEN a server's initialize handshake completes THE SYSTEM SHALL record the server's observed MCP
  `serverInfo` `name` and `version` in the snapshot as metadata only, or `None` when the connection
  carries no `serverInfo`. The catalog and resolver SHALL NOT use it for filtering, ranking or
  identity. `CandidateAction.server_identity` stays the configured identity.
- WHEN `refresh()` completes THE SYSTEM SHALL replace the previous snapshot atomically, so a tool that
  disappeared from a server disappears from the catalog and a newly added allow-listed tool appears.
- WHEN a caller reads the catalog before any successful `refresh()` THE SYSTEM SHALL return an empty
  snapshot rather than raise.

Resolver

- WHEN `Resolver.resolve(contract)` is called THE SYSTEM SHALL evaluate every configured capability
  through the fixed, ordered filter chain: allow-list/availability -> goal prefix -> target type ->
  target location -> argument template rendering -> argument-schema compatibility.
- WHEN a capability passes every filter THE SYSTEM SHALL emit a `CandidateAction` carrying
  `server_identity`, `tool_name`, `args`, `read_tool`, `idempotent`, `score` and `why`.
- WHEN more than one candidate survives THE SYSTEM SHALL rank them by descending score and SHALL
  break ties deterministically by `(server_identity, tool_name)`.
- WHILE scoring THE SYSTEM SHALL reward a longer matching goal prefix and an explicitly matched
  target location over a wildcard location match, and SHALL NOT let `idempotent` influence the score.
- WHEN an argument template placeholder such as `${constraints.desired_temperature_c}` resolves to a
  contract value THE SYSTEM SHALL substitute that value preserving its JSON type when the placeholder
  is the whole string, and SHALL interpolate its string form when it is embedded in a longer string.
- IF a placeholder names a field or constraint key the contract does not carry THEN THE SYSTEM SHALL
  reject that capability with a `template_error` reason naming the placeholder.
- IF the rendered arguments do not validate against the discovered tool's `input_schema` THEN THE
  SYSTEM SHALL reject that capability with a `schema_mismatch` reason carrying the validation message.
- IF no capability survives THEN THE SYSTEM SHALL return an empty candidate list together with one
  rejection reason per evaluated capability, each naming the server, the tool and the stage that
  rejected it.
- WHILE resolving THE SYSTEM SHALL make no network call of its own and SHALL NOT consult an LLM.

## Out of scope

- Executing tools (`call_tool`), retries, or anything that changes the physical world.
- Policy evaluation, approval binding, action lifecycle, audit trail, verification of outcomes.
- LLM-based or embedding-based capability matching; `Resolver` v0 is purely deterministic.
- Exposing the runtime itself as MCP tools, or wiring it into `create_server()` /
  `newton_mcp.config.Settings`.
- Long-lived MCP sessions, connection pooling, reconnect/backoff strategies.
- Any change to the Newton backends (`src/newton_mcp/newton/`) or to the Physical Action Contract
  model.

## Open questions

- Ambiguity in the issue: `capabilities` maps "server + tool to goal prefixes". This proposal models
  `goal_prefixes` as a list (a capability commonly serves `reduce_room_temperature` and
  `raise_room_temperature`); a single-string form is not accepted, to keep one shape.
- The issue does not define the argument-template language. This proposal uses explicit
  `${path}` placeholders over contract fields (`goal`, `reason`, `confidence`, `target.*`,
  `constraints.*`). `verification.*` is deliberately not a template root (owner amendment): tool
  arguments must not be derived from the verification section, and #8 replaces
  `verification.condition` with structured predicates. There is no escape sequence in v0, so a literal `${` cannot appear in a
  template value; if that ever matters, `$${` is the natural follow-up.
- Target matching uses case-insensitive exact location equality. Hierarchical locations
  (`building/floor2/kitchen`) and `target.resource` matching are deliberately deferred; `resource` is
  readable from templates but is not a filter.
- The issue does not say whether the runtime config path belongs in `newton_mcp.config.Settings`.
  This proposal keeps it in `runtime/config.py` because `Settings` configures the Direction B MCP
  server, which does not use the runtime yet.
- Score weights are a first cut chosen for explainability, not tuned. They are module-level constants
  so a later issue can revise them without touching the filter chain.
