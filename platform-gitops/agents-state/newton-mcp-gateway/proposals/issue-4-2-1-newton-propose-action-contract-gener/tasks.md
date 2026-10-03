# Tasks: issue-4-2-1-newton-propose-action-contract-gener

- [ ] 1. Add `src/newton_mcp/action/prompts.py` with `CONTRACT_PROMPT_MARKER`,
      `build_contract_system_prompt(allowed_goals=())` and `build_retry_suffix(errors)` — DoD:
      pure functions, no I/O and no `newton_mcp.newton` import; the prompt embeds
      `json.dumps(PhysicalActionContract.model_json_schema(), indent=2, sort_keys=True)`, the
      "exactly one JSON object, no prose, no markdown fences" instruction, the hard-rule-7 safety
      bound (lights / HVAC within bounds / speaker announcements / benign reversible routines;
      never locks, ovens, alarms, industrial start/stop, safety systems), and the `allowed_goals`
      block only when the tuple is non-empty; type hints throughout.
- [ ] 2. Add `src/newton_mcp/action/examples.py` with `MOCK_CONTRACT_EXAMPLE: dict[str, Any]`
      holding the literal contents of `examples/physical-action.json` — DoD: literal is
      byte-equivalent in value to the JSON file (enforced by T1); no filesystem read at import
      time; docstring states why the literal exists (the wheel ships only `src/newton_mcp`).
- [ ] 3. Add `src/newton_mcp/action/propose.py` with `ProposeError`, `ProposeActionResult`,
      `MAX_ATTEMPTS = 2`, `SUMMARY_MAX_CHARS = 280` and `async def propose_action(backend, *,
      model, text_events=(), json_events=(), allowed_goals=None, observation_id=None,
      max_new_tokens=700)` (depends on 1) — DoD: pre-flight `ValueError`s for a blank observation,
      a non-JSON `json_events` entry and an `allowed_goals` list that reduces to empty, all raised
      before any `backend.query`; deterministic
      `obs-<sha256(canonical events)[:16]>` fallback id; bounded `" | "`-joined summary; at most
      two `backend.query` calls; a result with `status == "failed"` is a terminal
      `backend_failed` error carrying `result.error` verbatim, returned with no retry;
      model-output failures classified as `empty_output` / `not_a_string` /
      `invalid_json` / `not_an_object` / `validation_error` / `goal_not_allowed`; retry appends
      `build_retry_suffix(errors_so_far)` to both `system_prompt` and `instruction_prompt`;
      `allowed_goals` membership checked after Pydantic validation; on success `evidence` is
      overwritten with the effective `observation_id` and derived summary; on exhaustion
      `status="failed"`, `contract=None`, `raw_text` = last raw text, `errors` = both attempts;
      never constructs a contract from defaults or partial data.
- [ ] 4. Add the contract-proposal branch to `MockNewtonBackend.query` in
      `src/newton_mcp/newton/mock.py` (depends on 1, 2) — DoD: branch triggers only when
      `CONTRACT_PROMPT_MARKER` is present in `system_prompt` or `instruction_prompt`; placed after
      the Omega and image branches and before the generic fallback; returns
      `outputs=[json.dumps(copy_of_example_with_reason_prefixed_by_"[mock] ")]` with
      `backend="mock"`; imports `newton_mcp.action.examples` function-locally (same pattern as
      `build_backend` in `newton/api.py`); every existing mock behaviour unchanged.
- [ ] 5. Register the `newton_propose_action` tool in `src/newton_mcp/server.py` (depends on 3) —
      DoD: `@server.tool(name="newton_propose_action", annotations=ToolAnnotations(
      read_only_hint=True, open_world_hint=True))`; description says it proposes exactly one
      validated Physical Action Contract and executes/authorises nothing; parameters
      `text_events`, `json_events`, `allowed_goals`, `observation_id`, `max_new_tokens=700`,
      `model=None`; body only resolves `_state(ctx)` / `state.settings.text_model` and returns
      `result.model_dump()`; no validation logic duplicated in the server.
- [ ] 6. Re-export `propose_action`, `ProposeActionResult`, `ProposeError` from
      `src/newton_mcp/action/__init__.py` (depends on 3) — DoD: added to `__all__` in sorted order
      alongside the existing exports; `import newton_mcp.action` raises no circular-import error.
- [ ] 7. Add `ScriptedNewtonBackend` to `tests/conftest.py` (depends on 3) — DoD: satisfies
      `isinstance(b, NewtonBackend)`; constructed from a list of output payloads; records each
      `NewtonQueryRequest`; raises `AssertionError` if queried more times than scripted;
      `name="api"` and `backend="api"` in its results so tests can distinguish it from the mock.
- [ ] 8. Update `tests/test_mcp_server.py` (depends on 5) — DoD:
      `test_lists_exactly_the_documented_tools` expects exactly
      `{"newton_query", "newton_embed_timeseries", "newton_analyze_image",
      "newton_propose_action"}`; `test_tools_are_marked_read_only` still passes unchanged.
- [ ] 9. Update `README.md` (depends on 5) — DoD: a `newton_propose_action` row in the Tools table
      (Newton C, read-only, "observation -> exactly one validated Physical Action Contract"); a
      paragraph in "Direction A: the Physical Action Contract (proposal)" covering the strict JSON
      prompt, `allowed_goals`, one retry then `failed`, and the mock label; the existing "this
      project's experimental proposal, not Archetype's" wording and the "What is confirmed vs.
      proposed" table are unchanged; no claim of live Newton validation anywhere (wording stays
      "mock-validated").
- [ ] 10. Run `uv sync --locked --group dev && uv run pytest` (depends on all above) — DoD: full
      suite green, no new dependency added, `uv.lock` unchanged.

## Tests

All new tests go in `tests/test_propose_action.py` unless noted, and go through
`conftest.call_tool` for the tool-level cases.

- [ ] T1. `tests/test_action_contract.py`: `MOCK_CONTRACT_EXAMPLE` equals
      `json.loads(EXAMPLE.read_text())` — the same sync guarantee
      `test_schema_file_is_in_sync_with_model` gives the schema file.
- [ ] T2. Prompt unit test (no backend): `build_contract_system_prompt(("a_goal", "b_goal"))`
      contains `json.dumps(PhysicalActionContract.model_json_schema(), indent=2, sort_keys=True)`,
      contains both goals, contains `CONTRACT_PROMPT_MARKER`, and contains the "no markdown
      fences" instruction and the forbidden-action list; with no `allowed_goals` the
      goal-restriction section is absent.
- [ ] T3. Valid model output on the first attempt -> `status == "completed"`, `contract` is
      present, `raw_text is None`, `errors == []`, and the scripted backend was queried exactly
      once.
- [ ] T4. Invalid JSON on attempt 1, valid JSON on attempt 2 -> `status == "completed"` with a
      contract; the backend was queried exactly twice; the second request's `system_prompt` and
      `instruction_prompt` both contain the attempt-1 error text.
- [ ] T5. Invalid JSON on both attempts -> `status == "failed"`, `contract is None`, `raw_text`
      equals the second attempt's raw text, `errors` has entries for `attempt == 1` and
      `attempt == 2` with `kind == "invalid_json"`, and the backend was queried exactly twice
      (never three times).
- [ ] T6. Schema-valid JSON whose `goal` is outside `allowed_goals`, returned on both attempts ->
      `status == "failed"` with `kind == "goal_not_allowed"` errors naming the rejected goal and
      the allowed set; no contract returned.
- [ ] T7. Schema-*invalid* JSON (e.g. `confidence: 1.4`, `risk: "banana"`, missing `verification`)
      on both attempts -> `status == "failed"` with `kind == "validation_error"` errors carrying a
      dotted `loc`.
- [ ] T8. Mock path: calling the tool with the `mock_backend` fixture -> `status == "completed"`,
      `backend == "mock"`, `contract["reason"].startswith("[mock] ")`, and the rest of the
      contract equals `examples/physical-action.json` apart from `reason` and `evidence`.
- [ ] T9. Evidence is filled from the observation on both backends: `evidence.observation_id`
      equals the effective id and `evidence.summary` is derived from the caller's events, even
      when the model's JSON supplied a different `evidence` block (provenance cannot be forged).
- [ ] T10. `observation_id` handling: supplied id is echoed verbatim in the envelope and in
      `evidence`; omitted id is `obs-` + 16 hex chars and is stable across two identical calls and
      different for a different observation.
- [ ] T11. Pre-flight `ValueError`s make zero backend calls (assert `backend.requests == []`),
      parametrised over: no events at all, only empty/whitespace strings, a `json_events` entry
      that is not JSON, and `allowed_goals=[]` / `allowed_goals=["  "]`. Use the existing
      `_root_cause` unwrapping helper pattern from `tests/test_analyze_image.py`.
- [ ] T12. Envelope shape: the returned `structured_content` keys are exactly
      `{"status", "contract", "raw_text", "errors", "backend", "observation_id"}` on both the
      success and the failure path.
- [ ] T13. Empty or non-string `outputs` (`[]`, `[None]`, `[{"a": 1}]`) on a
      `status == "completed"` result are classified as `empty_output` / `not_a_string` and still
      get exactly one retry.
- [ ] T17. Backend failure is terminal (owner amendment): the scripted backend returns
      `NewtonQueryResult(status="failed", outputs=[], error="upstream timeout")` on attempt 1 ->
      `status == "failed"`, `contract is None`, `raw_text is None`, `errors ==
      [{kind: "backend_failed", attempt: 1, message: "upstream timeout", ...}]`, and the backend
      was queried **exactly once**. Second case: attempt 1 returns invalid JSON and attempt 2
      returns `status="failed"` with `error=None` -> errors are `[invalid_json@1,
      backend_failed@2]`, the `backend_failed` message is the fixed "no error message" statement,
      and there were exactly two calls. Mutation check: allowing a retry after `backend_failed`
      must fail the first case.
- [ ] T18. Mock + incompatible `allowed_goals` (owner amendment): calling the tool through the
      `mock_backend` fixture with `allowed_goals=["turn_on_light"]`, which excludes the example's
      `reduce_room_temperature`, gives `status == "failed"`, `backend == "mock"`,
      `contract is None`, and two `goal_not_allowed` errors (attempts 1 and 2) that name
      `reduce_room_temperature` and the allowed set. The mock does not adapt its contract to the
      requested goals: doing so would simulate reasoning.
- [ ] T14. `tools/list` shows `newton_propose_action` with `read_only_hint is True` (covered by
      the updated `tests/test_mcp_server.py`, listed here for traceability).
- [ ] T15. `allowed_goals` normalisation: duplicates and surrounding whitespace are collapsed
      while order is preserved, and the prompt lists each goal once.
- [ ] T16. Existing suite regression: `tests/test_mock_backend.py`, `test_analyze_image.py`,
      `test_api_backend.py`, `test_config.py` and `test_action_contract.py` pass unchanged, i.e.
      the new mock branch does not capture any pre-existing request shape.

## Rollback

The change is purely additive and has no persisted state, so rollback is a revert:

1. `git revert <merge commit>` (or close the PR unmerged). That removes
   `action/prompts.py`, `action/examples.py`, `action/propose.py`,
   `tests/test_propose_action.py`, the `ScriptedNewtonBackend` fixture, the fourth
   `@server.tool` registration, the `MockNewtonBackend.query` branch, the
   `action/__init__.py` re-exports and the README edits in one commit.
2. No migration, no data cleanup, no config change: no environment variable was added
   (`NEWTON_*` and `ATAI_*` are untouched), no dependency was added, `uv.lock` is unchanged, and
   `schemas/physical-action-contract.schema.json`, `examples/physical-action.json` and
   `PhysicalActionContract` were never modified.
3. MCP hosts that had started calling `newton_propose_action` see the tool disappear from
   `tools/list`; the other three tools behave exactly as before. Nothing downstream can have
   acted on a proposal, because the tool authorises and executes nothing.
4. Partial rollback, if only the mock path is the problem: drop the branch in
   `newton/mock.py` (task 4) and keep the rest. `propose_action` then falls through to the
   generic `[mock] Newton is not connected...` output, which is correctly reported as
   `status: "failed"` with that raw text — a degraded but truthful mock path. T8 must be marked
   skipped in that case rather than deleted.
