# Design: issue-242-capability-gateway-and-builder-slice-2

> **Slice 2 of 3 for mctlhq/mctl-agents#242.** The full design is the slice-1
> proposal `issue-242-feat-agent-platform-role-aware-capabilit/design.md`,
> and the normative contract is ADR 017
> (`docs/adr/017-capability-discovery-and-gateway-contract.md`, merged in
> mctl-agents#485 → `cf5adda`). This file restates only what slice 2 builds
> and records the deltas found by re-reading `main` at `cf5adda`. Where this
> file and ADR 017 disagree, ADR 017 wins; its sec. 1–9 may not be reopened
> here (ADR 017, "Implementation map").

## What already exists on `main` (slice 1)

- `orchestrator/capability.py` (stdlib only): `ProviderRef`,
  `CapabilityDescriptor`, `CapabilitySet`, `ExecutionCorrelation`,
  `DiscoveryDecision`, `InvocationRecord`, `CheckpointVerdict`, `seal()`,
  `recompute_content_hash()`, the `PolicyCheckpoint` protocol,
  `AbsentPolicyCheckpoint`, `reason_code_for_verdict()`,
  `policy_checkpoint_status()`, `load_consequence_table()`,
  `classify_consequence()`, and the closed vocabularies `REASON_CODES`,
  `PROVIDER_TYPES` (`mcp-remote`, `mcp-local`, `sdk-builtin`),
  `CONSEQUENCE_VALUES`.
- `config/capability-consequence.yaml` with the fail-safe `consequential`
  default.
- `tests/test_capability.py` and the golden fixture
  `tests/fixtures/capability/investigator-capability-set.json`.

Nothing imports `orchestrator/capability.py` yet. Slice 2 is the first
consumer.

## What slice 2 builds

### 1. Contract hardening in `orchestrator/capability.py` (review follow-ups from #485)

These were deferred from #485's review to "the slice-2 builder PR" and are
listed in the #242 comment issuecomment-5841414702. They belong before the
gateway because the gateway is the first code that will feed real provider
data into `seal()`/`validate()`:

- `CapabilitySet.validate()` internal consistency: `tool_name ==
  f"mcp__{alias}__{tool}"` for the member's provider alias,
  `capability_id` equals its derivation (ADR 017 sec. 4), every
  `capability.provider` is an element of the set's `providers`, and the
  sealing-time `collision` check (two members with one `tool_name`, or two
  providers with one alias).
- Numeric bounds: reject negative `rank`, `input_schema_bytes` and
  `retention.expires_after_days`; `_optional_float` rejects `nan`/`inf`.
- Error-type consistency: wrong-typed `keywords`/`annotations` raise
  `CapabilityError`, not `TypeError`; `_require_str(allow_empty=True)` stops
  saying "non-empty"; the unhashable-key diagnostic; `yaml.YAMLError` from
  `load_consequence_table` is wrapped in `CapabilityError`; `RetentionPolicy`
  gets a `__post_init__` so direct construction cannot bypass `from_dict`'s
  checks; the sentinel indirection in
  `test_seal_refuses_what_from_dict_would_refuse` is removed.

The golden fixture's `content_hash` must stay byte-identical: none of these
changes alter the canonical payload of a valid set. If one does, that is a
contract change and stops the run (ADR 017 sec. 2).

### 2. `orchestrator/capability_gateway.py` — the runtime

As ADR 017 sec. 5 specifies. Two points re-read against `main`:

- **Remote provider connection.** Use `mcp.client.streamable_http` with the
  same headers `orchestrator/options.py::mctl_mcp_config()` builds today
  (`Authorization: Bearer $MCTL_TOKEN` plus `_execution_context_headers()`).
  The `#196` correlation metadata is added on top of those headers, not in
  place of them: `_execution_context_headers()` already fails closed under
  `MCTL_REQUIRE_EXECUTION_CONTEXT`, and the gateway must inherit that, not
  reimplement it. Reuse the helper; do not copy the header logic.
- **`providers` is a parameter in this slice.** The profile field that
  declares providers (`spec.capabilityDiscovery.providers`, mctl-gitops) is
  slice 3. Slice 2's `resolve_eligible(plan, correlation, providers)` takes
  an explicit, ordered provider list; alias assignment is by that order, as
  ADR 017 sec. 4 requires of the profile later.

The three gateway tools (`capability_search`, `capability_describe`,
`capability_invoke`) are registered with `claude_agent_sdk`'s
`create_sdk_mcp_server` / `@tool`, both available in the pinned
`claude-agent-sdk==0.2.136`.

### 3. The `#197` adapter

ADR 017 sec. 6 names slice 2 as the place where `capability_invoke` calls
into the general checkpoint (`orchestrator/policy_checkpoint.py`,
ADR 014) through a `PolicyCheckpoint` adapter, instead of reinventing
policy evaluation. Slice 2 adds that adapter
(`PolicyDecidePolicyCheckpoint`, wrapping `policy_checkpoint.decide`) and
tests it, but **no production code constructs the gateway in this slice**,
so no construction site chooses between it and `AbsentPolicyCheckpoint` yet.
That choice is slice 3's, where the investigator mode is wired.

Out of scope and unchanged: ADR 017 sec. 8's open product question (reads
that disclose sensitive data — `mctl_get_service_config`,
`mctl_get_service_logs`, `mctl_read_openclaw_identity` — rank `read-only`
and never reach a checkpoint). Slice 2 must not reclassify them or add a
disclosure tier; it applies the table as checked in.

### 4. Builder parameter in `orchestrator/options.py`

`build_issue_investigator_options_from_plan(plan, repo_dir, proposal_dir,
gateway=None)`. With `gateway=None` the result is byte-identical to today.
With a gateway: `mcp_servers={"capability": <sdk server config>}` (the
remote `mctl` server is not connected into the model's tool set),
`mcp__mctl__*` in `allowed_tools` becomes `mcp__capability__*`, and
`strict_mcp_config=True`. The `HUMAN_INPUT_CAPABILITY` filtering and the
"profile grants it AND MCP is configured" conjunction in the current
docstring are preserved in both branches. Nothing in slice 2 passes a
gateway from a real run.

### 5. Direct `mcp` dependency

`mcp` is today a transitive dependency (via `claude-agent-sdk`, locked at
`1.29.0`). The gateway imports `mcp.client.streamable_http` directly, so it
becomes a direct pinned dependency: `mcp==1.29.0` in `pyproject.toml` with a
rationale comment like the `httpx` entry.

**Correction to revision 1's DoD** ("`uv.lock` untouched"): that is not
achievable. `pr-validation.yml` runs `uv sync --locked`, and adding a direct
dependency changes the root package's `requires-dist` in `uv.lock`, so the
lock must be regenerated. The real invariant is that no resolved version
changes: `uv lock` produces a diff limited to the root entry's dependency
list, and `mcp` stays at `1.29.0`.

## Worker isolation

`orchestrator/capability_gateway.py` imports `mcp` and `claude_agent_sdk`,
so it must never be imported at module scope by any worker-reachable module
(ADR 017 sec. 5 and sec. 9, `tests/test_worker_isolation.py`).
`orchestrator/capability.py` stays stdlib-only and worker-importable.

## Rollback

Additive. New files: `orchestrator/capability_gateway.py` and its tests.
Changed: `orchestrator/capability.py` (validation only, no payload change),
`orchestrator/options.py` (one defaulted parameter, a no-op at `None`),
`pyproject.toml`/`uv.lock` (one direct pin, no version change). No runtime
path constructs the gateway, so reverting the PR removes dead code only.
