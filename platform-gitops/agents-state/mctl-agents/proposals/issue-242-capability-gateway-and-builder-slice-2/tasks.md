# Tasks: issue-242-capability-gateway-and-builder-slice-2

**Slice 2 of 3 for mctlhq/mctl-agents#242.** Slice 1 (ADR 017,
`orchestrator/capability.py`, the consequence table) merged as
mctl-agents#485 → `cf5adda`. This slice builds the gateway and the builder
parameter on top of it. Slice 3 (investigator mode switch, prompt block,
mode-aware `validate_manifest.py`, mctl-gitops catalog field, benchmark,
pilot status doc) is NOT part of this run and must not be started.

Task numbers 5–8 and 12 keep revision 1's numbering so cross-references in
the slice-1 proposal stay meaningful; R1–R3 and 6b are new in this slice.

**PR body:** the implementation PR must reference the issue with
`Refs mctlhq/mctl-agents#242`, never `Closes`/`Fixes`/`Resolves` — slice 3
is still pending, and a closing keyword would close #242 on merge.

## Contract hardening (review follow-ups from #485)

- [ ] R1. `CapabilitySet.validate()` internal consistency in
      `orchestrator/capability.py`: `tool_name == f"mcp__{alias}__{tool}"`,
      `capability_id` matches its ADR 017 sec. 4 derivation, every member's
      `provider` is in the set's `providers`, and the `collision` check (two
      members with one `tool_name`, or two providers with one alias).
      `CapabilityError` has no reason field today, so add
      `CapabilityCollisionError(CapabilityError)` with
      `reason_code = "collision"`, letting the gateway report the `collision`
      reason from `REASON_CODES` without parsing messages. — DoD: each rule
      has a failing-input test; the golden fixture's `content_hash` is
      unchanged.

- [ ] R2. Numeric bounds: negative `rank`, `input_schema_bytes` and
      `retention.expires_after_days` are rejected; `_optional_float` rejects
      `nan` and `inf`. — DoD: one test per field.

- [ ] R3. Error-type consistency: wrong-typed `keywords`/`annotations` raise
      `CapabilityError` (not `TypeError`); `_require_str(allow_empty=True)`
      message no longer says "non-empty"; unhashable-key diagnostic;
      `yaml.YAMLError` from `load_consequence_table` wrapped in
      `CapabilityError`; `RetentionPolicy.__post_init__` enforces what
      `from_dict` enforces; drop the sentinel indirection in
      `test_seal_refuses_what_from_dict_would_refuse`. — DoD: existing
      `tests/test_capability.py` passes unchanged except the sentinel test.

## Gateway and builder

- [ ] 5. Add `orchestrator/capability_gateway.py`
      `resolve_eligible(plan, correlation, providers) -> CapabilitySet`
      (depends on R1): remote providers via `mcp.client.streamable_http`
      with the headers `options.mctl_mcp_config()` builds (reuse
      `_execution_context_headers()`, do not copy it), execution-local
      providers via an in-process registry, `fnmatch` against
      `plan.tools`, alias assignment by the order of `providers`,
      consequence from `load_consequence_table()`/`classify_consequence()`,
      then `seal()` and `validate()`. — DoD: a provider that fails to list
      raises `provider-unavailable` instead of sealing a short set; an
      advertised tool matching no `plan.tools` pattern never appears in the
      set.

- [ ] 6. Add the three in-process gateway tools via
      `claude_agent_sdk.create_sdk_mcp_server` and `@tool` —
      `capability_search`, `capability_describe`, `capability_invoke`
      (depends on 5). `MAX_DESCRIBE_IDS` does not exist on `main`: define it
      as a module constant in `capability_gateway.py` with value 10 (neither
      ADR 017 nor the requirements fix a number; 10 is a reviewable
      default). — DoD: search returns compact rows with no schemas;
      describe is capped at `MAX_DESCRIBE_IDS` and answers `not-found` for
      any id outside the sealed set exactly as for a nonexistent id; invoke
      checks membership, then the `PolicyCheckpoint`, then dispatches
      (remote via the provider session, local in process) and returns
      exactly one reason code from `REASON_CODES` on failure.

- [ ] 6b. Add `PolicyDecidePolicyCheckpoint`, a `PolicyCheckpoint` adapter
      wrapping `orchestrator.policy_checkpoint.decide` (ADR 017 sec. 6)
      (depends on 6). The gateway takes its checkpoint as a constructor
      argument; no production code constructs the gateway in this slice.
      Apply `config/capability-consequence.yaml` as checked in: do not
      reclassify any tool and do not add a disclosure tier (ADR 017 sec. 8
      is an open product question, out of scope). — DoD: with a recording
      fake `decide`, a `denied` decision yields `policy-denied` and no
      provider call; an `allowed` decision records
      `policy_checkpoint: allowed`, while `AbsentPolicyCheckpoint` still
      records `absent`.

- [ ] 7. Propagate `#196` correlation metadata on every remote invocation and
      emit `#195`-shaped trace lines for set sealing and each invocation
      via `to_log_dict()` (depends on 5, 6) — DoD: trace output contains
      ids, hashes, counts, durations and reason codes only; a test greps the
      emitted lines for the argument and result text of a fake invocation
      and finds neither.

- [ ] 8. Extend `orchestrator/options.py`:
      `build_issue_investigator_options_from_plan(..., gateway=None)`; with a
      gateway, `mcp_servers={"capability": ...}`, `mcp__mctl__*` in
      `allowed_tools` becomes `mcp__capability__*`, and
      `strict_mcp_config=True` (depends on 6) — DoD: `gateway=None` produces
      options byte-identical to today; the `HUMAN_INPUT_CAPABILITY` filter
      and the "profile grants it AND MCP configured" conjunction hold in
      both branches; no other builder changes.

- [ ] 12. Promote `mcp` to a direct pinned dependency (`mcp==1.29.0`, the
      version already in `uv.lock`) in `pyproject.toml` with a rationale
      comment in the style of the `httpx` entry (depends on 5) — DoD:
      `uv lock` is re-run and its diff is limited to the root package's
      dependency list, no resolved version changes, and
      `uv sync --locked` (what `pr-validation.yml` runs) passes.
      Revision 1's "`uv.lock` untouched" is not achievable and is replaced
      by this.

## Tests

- [ ] T3. Exclusion is total — a provider advertising a tool outside
      `plan.tools` produces no descriptor, no search row, no describe
      result, and `capability_invoke` on its id returns `not-eligible`
      without any provider call (recording fake provider).

- [ ] T5. Collision safety — two providers resolving to the same
      `mcp__<alias>__<tool>` name, or claiming the same alias, raise
      `collision` at sealing time; no silent rename or shadow.

- [ ] T6. Remote and execution-local capabilities produce the same
      descriptor shape, and a local invocation performs zero network calls
      (transport fake that fails on use).

- [ ] T7. Correlation survives discovery to invocation — every invocation's
      metadata equals the `CapabilitySet.execution` block, which equals the
      `ExecutionPlan` pins.

- [ ] T9. Failure taxonomy — `provider-unavailable`, `provider-error`,
      `timeout`, `invalid-arguments`, `not-found` are distinct and never
      collapse into an empty-but-successful discovery.

- [ ] T10. Compatibility — extend `tests/test_options.py`: with
      `gateway=None` the built options equal today's byte-for-byte; with a
      gateway, `mcp_servers` has no remote entry, `strict_mcp_config` is set,
      and the reachable capabilities are a subset of the eager allow-list
      expansion. (The full no-expansion comparison against the catalog is
      slice 3.)

- [ ] T12. `tests/test_worker_isolation.py` — `orchestrator/capability.py`
      is importable in the worker's environment;
      `orchestrator/capability_gateway.py` is never imported at module scope
      by any worker-reachable module.

- [ ] T16. Consequential invocation calls `PolicyCheckpoint.check` before
      dispatch; a `denied` verdict returns `policy-denied` and performs no
      provider call; the order membership → checkpoint → dispatch is
      asserted with a recording fake provider.

## Rollback

Additive: `orchestrator/capability_gateway.py` and its tests are new; the
`capability.py` changes only tighten validation of inputs that were already
invalid; `options.py` gains a parameter that is a no-op at its default; the
dependency pin changes no resolved version. No runtime path constructs the
gateway, so reverting the PR removes dead code only.

## Deferred: slice 3 (not part of this run)

Tasks 9, 10, 11, 13, 14, 15 and tests T11, T13, T14 from the slice-1
proposal's `tasks.md`: the `ISSUE_INVESTIGATOR_CAPABILITY_MODE` switch, the
discovery prompt block, mode-aware `validate_manifest.py`, the benchmark,
the mctl-gitops `spec.capabilityDiscovery` field (only after task 11), the
pilot status doc, and the choice of which `PolicyCheckpoint` the investigator
constructs. Slice 3 needs its own new slug for the same preflight reason as
this one.
