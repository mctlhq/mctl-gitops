# Tasks: issue-7-2-3b-action-lifecycle-incl-unknown-corre

- [ ] 1. Add `src/newton_mcp/runtime/audit.py` with the `AuditSink` `Protocol`, the frozen
      `AuditEvent` model (`from`/`to` via field aliases on `from_state`/`to_state`,
      `populate_by_name=True`), `SECRET_KEY_PATTERNS`, `REDACTED`, `_MAX_VALUE_CHARS` and
      `redact_args()` — DoD: `redact_args()` returns a new structure (input untouched), recurses into
      nested dicts and lists, matches key names case-insensitively by substring, truncates long
      strings following `catalog.py`'s `_truncate` convention; the module imports nothing from
      `lifecycle.py` or `action/`; the docstring states plainly that there is no value-shape detection.
- [ ] 2. Add `MemoryAuditSink` and `JsonlAuditSink` to `audit.py` (depends on 1) — DoD:
      `MemoryAuditSink.events` collects `AuditEvent`s in order; `JsonlAuditSink.write()` opens in
      append mode per event and writes exactly one compact UTF-8 JSON line terminated by `\n`, using
      `model_dump(by_alias=True, exclude_none=True)`; the docstring states that rotation, retention,
      fsync durability and multi-process coordination are out of scope.
- [ ] 3. Add `AUDIT_PATH_ENV_VAR = "NEWTON_MCP_AUDIT_PATH"` and `load_audit_sink(path=None)` to
      `audit.py` (depends on 2) — DoD: unset/blank returns `MemoryAuditSink()`; a set-but-unusable
      path (missing parent directory, path is a directory, not writable) raises `ValueError` naming
      the variable and the path; the docstring explains why this differs from
      `load_runtime_config()` / `load_policy()`, which fail loudly when unset.
- [ ] 4. Add `src/newton_mcp/runtime/lifecycle.py` with `ActionState(StrEnum)` (ten lowercase
      members), `ALLOWED_TRANSITIONS` as a `MappingProxyType`, `REQUIRES_VERIFIED_FAILURE`,
      `TERMINAL_STATES` and `IllegalTransition(ValueError)` carrying `from_state` / `to_state` /
      `allowed` — DoD: the table matches requirements.md edge for edge; `UNKNOWN` omits `EXECUTING`
      and `PROPOSED` omits `EXECUTING` with an inline comment saying why; `DENIED`, `SUCCEEDED` and
      `ESCALATED` have empty outgoing sets; the table's keys cover every `ActionState` member.
- [ ] 5. Add `ActionRecord` (frozen, `extra="forbid"`) and `new_action_record(...)` with the
      `id_factory` seam and the `obs-` / `act-` / `call-` / `ver-` prefixes (depends on 4) — DoD: all
      four ids are non-`None` after creation, generated only where the caller omitted them; default
      factory is `secrets.token_hex(8)` (16 hex chars, matching `propose.py`'s `obs-<16 hex>` shape);
      initial state is `PROPOSED`, `attempt` is `0`, `created_at == updated_at == now`; a naive `now`
      raises `ValueError`.
- [ ] 6. Implement `transition(record, new_state, reason, *, now, sink=None, verified_failure=False,
      args=None, id_factory=None, **ids)` (depends on 4, 5) — DoD: checks run in the documented order
      (blank reason, `**ids` key validation, table legality, verified-failure guard, aware `now`);
      returns a new `ActionRecord` and never mutates the input; `attempt` increments only on entering
      `EXECUTING`; a fresh `tool_call_id` / `verification_id` is minted on entering
      `EXECUTING` / `VERIFYING` when not supplied; `observation_id` / `action_id` in `**ids` raise
      `ValueError`, as does an id key that does not belong to the target state or an unknown key.
- [ ] 7. Wire the audit write into `transition()` (depends on 2, 6) — DoD: exactly one `AuditEvent` is
      written per accepted transition and only after the new record is computed; it carries all four
      ids, `from`, `to`, `reason`, `attempt`, `verified_failure` and `at` via
      `canonical_timestamp(now)`; when `args` is supplied the event carries redacted `args` plus
      `args_digest = sha256_hex(args)` over the unredacted args; a rejected transition writes nothing;
      `sink=None` writes nothing.
- [ ] 8. Re-export the new public names from `src/newton_mcp/runtime/__init__.py` (depends on 3, 7) —
      DoD: `ActionRecord`, `ActionState`, `AuditEvent`, `AuditSink`, `IllegalTransition`,
      `JsonlAuditSink`, `MemoryAuditSink`, `load_audit_sink`, `new_action_record`, `redact_args` and
      `transition` are importable from `newton_mcp.runtime`, `__all__` stays sorted, and existing
      exports are unchanged.
- [ ] 9. Extend `tests/runtime/conftest.py` with a deterministic `id_factory` fixture (a counter
      yielding `0000000000000001`, ...) and a fixed aware `datetime` fixture (depends on 5) — DoD:
      existing fixtures untouched; a lifecycle test can assert ids and timestamps as literals.
- [ ] 10. Update `docs/action-runtime.md` (depends on 8) — DoD: a new "Lifecycle, correlation ids and
      audit" section documents the table (including why `UNKNOWN -> EXECUTING` is absent), the four
      ids, the verified-failure guard, the JSONL line shape, `NEWTON_MCP_AUDIT_PATH` (unset =
      disabled, set-but-unusable = loud), and the redaction limits; the header line and the "What this
      package does not do" list no longer claim "no lifecycle, no audit"; execution and verification
      are still listed as out of scope; the "this project's experimental proposal" and no-live-
      validation framing is preserved.
- [ ] 11. Update `docs/architecture.md`, `README.md` and `.env.example` (depends on 10) — DoD:
      `docs/architecture.md`'s lifecycle line includes `UNKNOWN` and `DENIED` and notes that `UNKNOWN`
      cannot return directly to `EXECUTING`; `README.md`'s "no execution, no lifecycle, no audit"
      sentence becomes "no execution, no verification" and keeps the mock-validated wording;
      `.env.example` documents `NEWTON_MCP_AUDIT_PATH` (commented out) alongside
      `NEWTON_MCP_RUNTIME_CONFIG` / `NEWTON_MCP_POLICY_PATH`, stating that unset means disabled.
- [ ] 12. Run `uv sync --locked --group dev && uv run pytest -q` (depends on all) — DoD: the whole
      suite is green, `uv.lock` is unchanged, no new dependency was added, and
      `tests/test_action_contract.py` still passes without regenerating
      `schemas/physical-action-contract.schema.json`.

## Tests

All in `tests/runtime/test_lifecycle.py` and `tests/runtime/test_audit.py`, plain `pytest` functions
with type hints and `from __future__ import annotations`, matching `tests/runtime/test_config.py`.

- [ ] T1. Exhaustive table-driven transition test: parametrize over the full cartesian product of
      `ActionState` x `ActionState`; every pair listed in `ALLOWED_TRANSITIONS` succeeds and returns a
      record in the target state, and every other pair raises `IllegalTransition`. `FAILED ->
      EXECUTING` is exercised with `verified_failure=True` in the allowed half. This covers the
      acceptance criterion "every allowed transition" and additionally fails if an edge is ever added
      without updating the table.
- [ ] T2. `test_unknown_cannot_go_straight_back_to_executing` — a named standalone test asserting
      `UNKNOWN -> EXECUTING` raises `IllegalTransition`, with the exception's `allowed` attribute
      equal to `{VERIFYING, ESCALATED}`.
- [ ] T3. `test_proposed_cannot_skip_authorization` — `PROPOSED -> EXECUTING` raises
      `IllegalTransition`.
- [ ] T4. Terminal states: parametrize `DENIED`, `SUCCEEDED`, `ESCALATED` and assert every outgoing
      transition (to every other state, and to itself) raises, with a message that says the state is
      terminal.
- [ ] T5. `ALLOWED_TRANSITIONS` covers every `ActionState` member exactly once, and all its targets
      are valid `ActionState`s.
- [ ] T6. `FAILED -> EXECUTING` raises without `verified_failure=True` and succeeds with it; the
      resulting audit line carries `verified_failure: true`.
- [ ] T7. A rejected transition leaves the input record byte-identical (compare
      `model_dump()` before and after the raising call) and writes nothing to a `MemoryAuditSink`.
- [ ] T8. Id generation: `new_action_record()` with no ids produces four ids with the correct
      prefixes; with a deterministic `id_factory` the values are exact literals; explicitly supplied
      ids are preserved verbatim.
- [ ] T9. Attempt counter: `PROPOSED -> AUTHORIZED -> EXECUTING` yields `attempt == 1`; a
      `FAILED -> EXECUTING` retry yields `attempt == 2`; no other transition changes `attempt`.
- [ ] T10. `tool_call_id` is freshly minted on each entry into `EXECUTING` (a retry's id differs from
      the first attempt's), `verification_id` is freshly minted on entry into `VERIFYING`, and an
      explicitly supplied id on those transitions wins.
- [ ] T11. Id-keyword validation: passing `observation_id` or `action_id` to `transition()` raises
      `ValueError`; passing `tool_call_id` on a non-`EXECUTING` transition (or `verification_id` on a
      non-`VERIFYING` one) raises `ValueError`; an unknown `**ids` key raises `ValueError`.
- [ ] T12. A blank or whitespace-only `reason` raises `ValueError`, and a naive `now` raises
      `ValueError`.
- [ ] T13. Happy-path audit test (the issue's acceptance criterion): drive `PROPOSED -> AUTHORIZED ->
      EXECUTING -> EXECUTED -> VERIFYING -> SUCCEEDED` through a `JsonlAuditSink` in `tmp_path`;
      assert the file has exactly 5 lines, each parses as JSON, each carries all four non-null ids
      plus `from`, `to`, `reason`, `attempt` and `at`, and the `from`/`to` sequence matches the path
      walked.
- [ ] T14. Append-only test: write one transition, construct a *second* `JsonlAuditSink` on the same
      path, write another, and assert the file now has both lines in order — re-opening never
      truncates.
- [ ] T15. Redaction test (the issue's acceptance criterion): args containing `api_key`,
      `access_token`, `Authorization`, `session_cookie`, a nested `{"creds": {"password": ...}}` and a
      list of dicts are all replaced with `[redacted]`, while benign keys (`location`,
      `target_temperature_c`, `brightness_pct`) survive with their JSON types intact; `redact_args()`
      does not mutate its input.
- [ ] T16. `args_digest` on an audit line equals `newton_mcp.canonical.sha256_hex(args)` for the
      unredacted args, and therefore equals the `args_digest` that
      `newton_mcp.action.create_approval()` produces for a candidate with the same `args` — asserted
      directly, since that equality is the audit-to-approval link.
- [ ] T17. A very long string argument value is truncated to `_MAX_VALUE_CHARS` with the `...`
      suffix, and the emitted JSON is still a single line (no embedded raw newline).
- [ ] T18. `load_audit_sink()` returns a `MemoryAuditSink` when `NEWTON_MCP_AUDIT_PATH` is unset,
      blank or whitespace-only (`monkeypatch.delenv` / `setenv`), and a `JsonlAuditSink` when it names
      a usable path in `tmp_path`.
- [ ] T19. `load_audit_sink()` raises `ValueError` naming the variable and path when the variable
      points at a directory, or at a file inside a non-existent parent directory.
- [ ] T20. `transition(..., sink=None)` performs the state change and writes nothing anywhere (no file
      created in `tmp_path`).
- [ ] T21. `MemoryAuditSink` records events in transition order and is the sink every other test in
      the suite uses, so the suite writes no file except in the `tmp_path` tests above.

## Rollback

Self-contained and additive, so rollback is a revert with no cleanup:

1. `git revert` the merge commit (or delete `src/newton_mcp/runtime/lifecycle.py`,
   `src/newton_mcp/runtime/audit.py`, `tests/runtime/test_lifecycle.py` and
   `tests/runtime/test_audit.py`, and restore `src/newton_mcp/runtime/__init__.py`,
   `tests/runtime/conftest.py`, `docs/action-runtime.md`, `docs/architecture.md`, `README.md` and
   `.env.example`).
2. No dependency, no lockfile and no generated schema changed, so nothing else has to be rebuilt or
   regenerated; `uv run pytest -q` is green again immediately after the revert.
3. No state exists to migrate back: nothing persists an `ActionRecord`, and `NEWTON_MCP_AUDIT_PATH` is
   opt-in. Any audit file an operator enabled stays on disk as an inert plain-text artifact and can be
   deleted at will.
4. Partial rollback is also possible: unsetting `NEWTON_MCP_AUDIT_PATH` (or passing `sink=None`)
   disables all file writing while leaving the state machine in place, since the audit sink is an
   injected seam and not a hard dependency of `transition()`.
