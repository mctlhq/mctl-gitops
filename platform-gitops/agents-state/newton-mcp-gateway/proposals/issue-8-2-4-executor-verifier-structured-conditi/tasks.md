# Tasks: issue-8-2-4-executor-verifier-structured-conditi

- [ ] 1. Add `src/newton_mcp/action/conditions.py`: `Op` (`StrEnum`: eq, ne, lt, le, gt, ge),
      `Scalar`, `Predicate` (`path` min_length 1, `op`, `value`), `AllOf` (field `all`), `AnyOf`
      (field `any`), the callable-`Discriminator` `Condition` union with `Tag("predicate"|"all"|"any")`,
      `model_rebuild()` for the recursive members, and `MAX_CONDITION_DEPTH = 8` enforced by a
      `model_validator(mode="after")`. Every model `extra="forbid"`, `frozen=True`.
      — DoD: `Condition` validates the three wire shapes from the issue, rejects a string, an
      unknown key, an empty `all`/`any` and an over-deep nest; `model_dump()` round-trips the exact
      wire shape with no aliases; the module imports nothing from `newton_mcp.runtime`.
- [ ] 2. Add `evaluate(condition, observation) -> ConditionResult(satisfied, reason)` and
      `resolve_path(path, observation)` to `conditions.py` (depends on 1) — DoD: mapping-only dotted
      traversal; missing path never satisfied for any op including `ne`; `eq`/`ne` compare only
      type-compatible operands with `bool` never a number; ordering ops require non-bool
      `int`/`float` on both sides; every failure path returns a non-empty reason and raises nothing;
      reasons name path, op and expected value but never the raw observed value; no I/O, no `eval`,
      no parser anywhere in the module.
- [ ] 3. Bump the contract to v0.2 in `src/newton_mcp/action/contract.py` (depends on 1):
      `version` default `"0.2"` with `pattern=r"^0\.2$"`, `Verification.condition: Condition`.
      — DoD: `PhysicalActionContract` validates a v0.2 example and rejects `version: "0.1"` and a
      string condition.
- [ ] 4. Regenerate `schemas/physical-action-contract.schema.json` with the CONTRIBUTING.md
      one-liner and update `examples/physical-action.json` plus
      `src/newton_mcp/action/examples.py::MOCK_CONTRACT_EXAMPLE` to v0.2, using
      `{"path": "temperature_c", "op": "le", "value": 24}` for the kitchen example (depends on 3)
      — DoD: `tests/test_action_contract.py` passes unchanged, including the schema-sync and
      example-sync assertions.
- [ ] 5. Update `src/newton_mcp/action/prompts.py` (depends on 3): marker becomes
      `physical-action-contract/v0.2/strict-json`, plus one instruction line stating that
      `verification.condition` is a structured object (`{path, op, value}`, `{all: [...]}`,
      `{any: [...]}`) and never an expression string — DoD: `tests/test_propose_action.py` passes;
      the embedded schema is still derived at call time from `model_json_schema()`.
- [ ] 6. Fix the four existing `Verification(condition="...")` fixtures
      (`tests/runtime/test_catalog.py:270`, `tests/runtime/test_resolver.py:46`,
      `tests/test_policy_yaml.py:62`) to structured predicates (depends on 3) — DoD: the whole
      suite is green again before any new runtime code lands; the
      `${verification.condition}` template-rejection test at `tests/runtime/test_resolver.py:289`
      still passes untouched.
- [ ] 7. Promote `catalog._default_client_factory` to a public `default_client_factory` (alias the
      old name internally if anything still uses it) — DoD: `tests/runtime/test_catalog.py` passes
      unchanged, including `test_refresh_never_calls_call_tool`.
- [ ] 7a. Add `read_arguments: dict[str, Any]` (default `{}`) to `CapabilityConfig`, render it in
      the resolver with `render_arguments` and carry it as `CandidateAction.read_args`; add
      `read_arguments: {location: "${target.location}"}` to the two `read_tool` capabilities in
      `examples/runtime.example.yaml` (owner amendment) — DoD: a `${verification.*}` root in
      `read_arguments` is refused like in `arguments`; a render failure rejects the candidate at
      the arguments stage; existing resolver/config tests stay green.
- [ ] 8. Add `src/newton_mcp/runtime/executor.py` with `SupportsCallTool`, `ToolClientFactory`,
      `ExecutionOutcome`, `ExecutorError`, `ApprovalRejected` and `Executor.execute(candidate, record,
      *, approval, policy_version, now, verified_failure=False)` (depends on 7) — DoD: checks run
      in design.md's order on every attempt: (1) server resolution / `binding_identity` check →
      `ExecutorError`, (2) `verify_approval(approval, candidate, record.action_id, policy_version,
      now)` → `ApprovalRejected`, (3) the `-> EXECUTING` transition, (4) the call; a failure at (1)
      or (2) leaves no transition, no audit line and no transport opened; is the only code that transitions into `EXECUTING`
      (`AUTHORIZED -> EXECUTING`, or `FAILED -> EXECUTING` with `verified_failure=True`); resolves
      the `ServerConfig` by `resolved_identity` and raises `ExecutorError` before opening any
      transport when the server is unknown or `binding_identity != candidate.server_binding_identity`;
      transitions to `EXECUTING` (with `args` on the audit line) before calling; one
      `anyio.fail_after` scope covers connect, handshake and the call; any returned result
      (including an MCP error result) → `EXECUTED`; timeout/transport `Exception` → `UNKNOWN`;
      `BaseException`/`BaseExceptionGroup` propagate untouched.
- [ ] 9. Add `src/newton_mcp/runtime/verifier.py` with `VerificationOutcome`, `Verifier` and
      `observation_from_result()` (depends on 2, 7, 7a) — DoD: transitions into `VERIFYING` first;
      escalates before any poll when there is no `read_tool`, the read tool was not discovered, or
      it declares `read_only_hint is False`; calls the read tool with exactly `candidate.read_args`;
      an MCP error result from it is a failed poll, never an observation; no poll starts after the
      deadline; polls only the read tool, first poll at t=0, bounded
      by `verification.timeout_seconds` on an injected `clock`/`sleep`; satisfied → `SUCCEEDED`;
      deadline with at least one observation → `FAILED`; deadline with zero observations →
      `ESCALATED`.
- [ ] 10. Add `run_action()` to `executor.py` implementing the retry rule (depends on 8, 9) — DoD:
      always verifies before any retry decision; retries only when `candidate.idempotent and
      record.attempt <= contract.verification.retry_limit`, by calling `execute(...,
      verified_failure=True)` — `run_action()` itself never transitions into `EXECUTING`; an
      `ApprovalRejected` on a retry → `FAILED -> ESCALATED`, on the first attempt it propagates with
      the record still `AUTHORIZED`; otherwise `FAILED -> ESCALATED`; returns terminating in
      exactly `SUCCEEDED` or `ESCALATED`; every transition goes through `lifecycle.transition()`
      with the shared sink.
- [ ] 11. Export the new symbols from `src/newton_mcp/action/__init__.py` (`Condition`,
      `Predicate`, `AllOf`, `AnyOf`, `Op`, `ConditionResult`, `evaluate`) and
      `src/newton_mcp/runtime/__init__.py` (`Executor`, `ExecutionOutcome`, `ExecutorError`,
      `ApprovalRejected`, `Verifier`, `VerificationOutcome`, `run_action`), keeping `__all__` sorted (depends on 10)
      — DoD: `from newton_mcp.runtime import run_action` works; `action/` still imports nothing
      from `runtime/`.
- [ ] 12. Docs (depends on 10): add a "digital success is not physical success" section to
      `docs/architecture.md` stating the retry rule; update `docs/action-runtime.md` (drop the
      "executes nothing / no verification logic / no retry decision" claims, add executor and
      verifier sections including the zero-observation escalation, the `read_only_hint` refusal,
      the approval re-check before every attempt, `read_arguments`, the fact that a capability
      without `read_tool` always ends `ESCALATED`, and the `read_timeout_seconds` deadline overrun);
      update the `README.md` contract example to v0.2 and its runtime paragraph — DoD: no doc still
      says the runtime executes nothing; "experimental proposal, not an Archetype standard" and
      "mock-validated" wording preserved; no emoji.
- [ ] 13. Run `uv sync --locked --group dev && uv run pytest -q` and re-read the full diff against
      the epic's seven hard rules (depends on 12) — DoD: suite green; no invented Archetype
      endpoint/parameter/model id; no unsafe demo capability added to any example; no mctl.ai
      reference; `uv.lock` unchanged (no new dependency).

## Tests

All new tests use the existing in-process doubles style from `tests/runtime/conftest.py`: no
subprocess, no socket, no credentials, `MemoryAuditSink`, `deterministic_id_factory`, `fixed_now`.

- [ ] T1. `tests/test_conditions.py`: one case per operator (`eq`, `ne`, `lt`, `le`, `gt`, `ge`)
      satisfied and unsatisfied.
- [ ] T2. `tests/test_conditions.py`: `all` nesting (all children satisfied → satisfied; one
      unsatisfied → not satisfied, reason names that child), `any` nesting (one satisfied →
      satisfied; none → not satisfied), and an `all` containing an `any` containing a predicate.
- [ ] T3. `tests/test_conditions.py`: missing path → not satisfied with a reason naming the path,
      parametrised over every op including `ne`; a non-mapping mid-path segment behaves the same.
- [ ] T4. `tests/test_conditions.py`: type mismatch → not satisfied, never raises — string vs
      number under every op, `bool` vs number under `eq`, non-numeric under `lt|le|gt|ge`, `None`
      operands.
- [ ] T5. `tests/test_conditions.py`: validation rejects a string condition, an unknown key, an
      empty `all`/`any`, and a nest deeper than `MAX_CONDITION_DEPTH`; `model_dump()` round-trips
      the wire shape and preserves `int` vs `bool` vs `str` value types.
- [ ] T6. `tests/test_action_contract.py` (existing, must stay green): schema-in-sync,
      example-in-sync, example validates; add an assertion that `version == "0.2"` and that a
      `version: "0.1"` payload is rejected.
- [ ] T7. `tests/runtime/test_executor.py`: a happy call transitions
      `AUTHORIZED -> EXECUTING -> EXECUTED`, calls the tool exactly once with exactly
      `candidate.args`, and writes both transitions to the sink with all four correlation ids.
- [ ] T8. `tests/runtime/test_executor.py`: a forced hang (an `anyio.sleep_forever` tool body)
      under a short `call_timeout_seconds` → `UNKNOWN`; a transport factory that raises → `UNKNOWN`;
      an MCP *error* result → `EXECUTED`, not `FAILED`.
- [ ] T9. `tests/runtime/test_executor.py`: an unknown server identity, and a mutated transport
      under an unchanged name (so `binding_identity` differs), both raise `ExecutorError` with
      **zero** recorded tool calls.
- [ ] T10. `tests/runtime/test_verifier.py`: condition satisfied on the first observation →
      `SUCCEEDED` after exactly one read call; satisfied on the third poll → `SUCCEEDED` with three
      reads and no action-tool call.
- [ ] T11. `tests/runtime/test_verifier.py`: never satisfied by the deadline with observations →
      `FAILED`; zero obtainable observations (every read raises) → `ESCALATED`; no `read_tool`
      configured → `ESCALATED` with zero reads; `read_tool` configured but not discovered
      (`read_tool_missing`) → `ESCALATED`; discovered read tool with `read_only_hint=False` →
      `ESCALATED` with zero reads.
- [ ] T12. `tests/runtime/test_retry_rule.py` — acceptance criterion 1: call succeeds, state never
      changes. Non-idempotent → `ESCALATED` with exactly one action-tool call. Idempotent with
      `retry_limit=2` → exactly three action-tool calls, then `ESCALATED`.
- [ ] T13. `tests/runtime/test_retry_rule.py` — acceptance criterion 2: forced timeout
      (`UNKNOWN`), verification shows the outcome already met → `SUCCEEDED`, and the action tool was
      called exactly **once** (assert the recorded call count, not just the state).
- [ ] T14. `tests/runtime/test_retry_rule.py` — acceptance criterion 3: forced timeout, outcome not
      met, `idempotent=False` → `ESCALATED` with exactly one action-tool call.
- [ ] T15. `tests/runtime/test_retry_rule.py` — acceptance criterion 4: forced timeout, outcome not
      met, `idempotent=True`, `retry_limit=1` → exactly one retry (two action-tool calls total),
      then `ESCALATED`; a second case with `retry_limit=2` proves the implementation honours the
      configured value rather than a hard-coded 1.
- [ ] T16. `tests/runtime/test_retry_rule.py`: the full transition sequence for each scenario above
      is asserted against `MemoryAuditSink` — ordered `from`/`to` pairs, `attempt` numbers,
      `verified_failure` flags, and all four correlation ids present and non-null on every line,
      with the retry's `tool_call_id`/`verification_id` pair differing from attempt 1's while
      `observation_id`/`action_id` stay fixed.
- [ ] T17. `tests/runtime/conftest.py` additions: a `call_tool`-capable in-process factory that
      records every `(tool_name, args)` call, a scripted read-tool double returning a queue of
      observations, and a deterministic `clock`/`sleep` pair — DoD: no new test sleeps in real time
      and the whole suite stays subprocess- and socket-free.

- [ ] T18. `tests/runtime/test_executor.py` (owner amendment): an expired approval, an approval
      for another `action_id`, one for another `policy_version`, and one bound to the pre-re-point
      `binding_identity` each raise `ApprovalRejected` with **zero** tool calls, no transport opened,
      no audit line and the record unchanged in `AUTHORIZED`.
- [ ] T19. `tests/runtime/test_retry_rule.py` (owner amendment): idempotent capability,
      `retry_limit=1`, attempt 1 verified `FAILED`, approval expires before the retry (injected
      `now_fn`) → `FAILED -> ESCALATED` with a reason naming the approval, and exactly **one**
      action-tool call.
- [ ] T20. `tests/runtime/test_retry_rule.py` (owner amendment): in a retry scenario the audit log
      has exactly one `-> EXECUTING` line per attempt (`authorized -> executing`, then
      `failed -> executing` with `verified_failure: true`), and none is written by `run_action()`
      (a spy on `transition` from `run_action`'s module sees no `EXECUTING` target).
- [ ] T21. `tests/runtime/test_verifier.py` + `tests/runtime/test_resolver.py` (owner amendment):
      the read tool receives exactly the rendered `read_args` (e.g. `{"location": "kitchen"}`) and
      never the action `args`; absent `read_arguments` → `{}`; `${verification.condition}` in
      `read_arguments` is refused; a read tool returning an MCP error result with structured
      content counts as a failed poll (zero observations → `ESCALATED`).

## Rollback

Every change is additive except the contract bump, and all of it is one PR on one branch, so
`git revert` of the merge commit restores v0.1 wholesale: the three sync tests
(`test_schema_file_is_in_sync_with_model`, `test_mock_contract_example_is_in_sync_with_example_file`,
`test_example_contract_validates`) will immediately prove the revert is internally consistent, since
they fail on any partial rollback of the contract, the schema file and the embedded example.

Nothing in this proposal is wired into `create_server()` or `newton_mcp.config.Settings`, so no
deployed MCP tool surface changes and there is nothing to redeploy or drain: a revert cannot break
a running gateway. There is no database, no persisted contract and no state to migrate back. No
dependency is added, so `uv.lock` is untouched and a revert needs no `uv lock` run.

Partial rollback, if only the execution path proves problematic: delete
`src/newton_mcp/runtime/{executor,verifier}.py`, their exports in `runtime/__init__.py` and their
tests. The v0.2 contract, `conditions.py` and the regenerated schema stand alone and stay green,
because nothing in `action/` imports `runtime/`.
