# Tasks: issue-9-2-5-smart-home-testbed-end-to-end-closed

- [ ] 1. Add `examples/smart-home/fake_alice.py`: a Pydantic v2 `RoomState`
      (`room`, `temperature_c`, `occupancy`, `ac_online`, `ac_target_c`, `light_on`,
      `brightness_pct`, `cooling_step_c`, `announcements`), `build_fake_alice(state, *, call_log)`
      returning an `mcp.server.mcpserver.MCPServer` with the five tools from design.md, and
      `in_process_factory(server)` returning `mcp.Client(server)` for any `ServerConfig`.
      — DoD: `get_room_state` is annotated `ToolAnnotations(read_only_hint=True)` and returns a
      mapping with a top-level `temperature_c`; each read advances `temperature_c` one
      `cooling_step_c` toward `ac_target_c` only while `ac_online` is true;
      `set_ac_temperature` returns `{"accepted": true, ...}` even when offline and declares an
      unbounded `int` for `target_temperature_c`; `announce` is non-idempotent and has no read
      counterpart; `call_log` records `(tool_name, arguments)` per call; type hints throughout; no
      import from `tests/` and no import from `newton_mcp.runtime` beyond type convenience.
- [ ] 2. Add `examples/smart-home/runtime.yaml` (depends on 1) — one `alice` server,
      `streamable-http`, url `https://alice.invalid/mcp`; the four capabilities of design.md's table
      with explicit `idempotent:` on each and `read_tool: get_room_state` where verifiable; a header
      comment matching `examples/runtime.example.yaml`'s safety note.
      — DoD: `load_runtime_config(path)` validates it; every capability's tool name and goal prefix
      is free of `("lock", "oven", "alarm", "industrial", "safety", "start", "stop")`; the tool names
      and argument keys match `fake_alice`'s signatures exactly.
- [ ] 3. Add `examples/smart-home/policy.yaml` (depends on 2) — `policy_version: "smart-home.v1"`,
      `default: deny`, and the five rules of design.md in file order, with
      `arg_ranges: {target_temperature_c: {min: 20, max: 25}}` on the AC rules and
      `decision: confirm` on announcements.
      — DoD: `load_policy(path)` validates it; `Policy.evaluate(mock_contract, ac_candidate)` returns
      `auto` for `target_temperature_c: 23` and `deny` naming `target_temperature_c` for `30`.
- [ ] 4. Add `examples/smart-home/demo.py` skeleton (depends on 1-3): argparse with `--mock`
      (default) / `--real`, `--ac-offline`, `--audit-path`, `--overwrite`, `--deterministic`,
      `--force-desired-temperature-c`; a frozen `DemoResult`; `run_demo(...)`; `main(argv) -> int`
      with exit codes `0` SUCCEEDED / `3` ESCALATED / `4` DENIED / `1` unexpected error.
      — DoD: `--help` works; `main` returns the documented codes; `sys.path` is extended so
      `import fake_alice` resolves from the script's own directory.
- [ ] 5. Wire the propose step in `run_demo` (depends on 4): build the backend
      (`MockNewtonBackend()` in mock mode, `build_backend(Settings.from_env())` in real mode — the
      only thing `--real` changes; the actuator stays `fake_alice`), call
      `propose_action(backend, model=..., text_events=["kitchen 29.4 C, occupied"],
      allowed_goals=[...the runtime.yaml goal prefixes...])`, print the labelled envelope, and create
      the record with `new_action_record(now=..., observation_id=result.observation_id,
      id_factory=...)`.
      — DoD: a failed proposal prints its `errors` and exits `1` without touching the actuator; the
      printed trace shows `backend: "mock"` and the contract's `[mock] ` reason in mock mode.
- [ ] 6. Wire catalog + resolver (depends on 5): build `CapabilityCatalog(config,
      client_factory=...)`, `await catalog.refresh()`, print `snapshot.problems`, then
      `Resolver(catalog).resolve(contract)` and print every candidate (`score`, `why`) and every
      rejection (`stage`, `detail`); pick `candidates[0]`.
      — DoD: an empty candidate list prints the rejections and exits `1` with no tool call; in mock
      mode exactly one candidate (`set_ac_temperature`) survives for the kitchen contract.
- [ ] 7. Wire policy + approval + authorization (depends on 6): apply the optional
      `--force-desired-temperature-c` override (clearly labelled as a testbed override),
      `Policy.evaluate(contract, candidate)`; on `deny` do `transition(record, DENIED, ...)` and exit
      `4`; on `confirm` auto-approve in `--mock` with a mock-labelled `approved_by` or prompt on
      stdin otherwise; on `auto` build `create_approval(..., approved_by=f"policy:{policy_version}:
      {rule}", expires_at=now + 15 min)`; then `transition(record, AUTHORIZED, ...)`.
      — DoD: the deny path writes exactly one audit line and issues no `call_tool` (asserted in T4);
      every approved path goes through `create_approval`, so there is no approval-less execution.
- [ ] 8. Wire executor + verifier + `run_action` (depends on 7): one `JsonlAuditSink(audit_path)`
      passed as `sink=` to both `Executor(catalog, client_factory=..., sink=sink, id_factory=...)`
      and `Verifier(catalog, client_factory=..., sink=sink, poll_interval_seconds=..., clock=...,
      sleep=..., id_factory=...)`; in mock mode inject a simulated clock whose `sleep` advances a
      float (no real waiting) and `poll_interval_seconds=60.0`; call `run_action(...)` with
      `now_fn`; print the terminal state, the actuator call count, the observation count, the four
      correlation ids and the audit path.
      — DoD: `--mock` ends `SUCCEEDED`; `--mock --ac-offline` ends `ESCALATED`; neither takes more
      than a few seconds of wall-clock time; `--overwrite` truncates the audit file before the run
      while the sink itself still only appends.
- [ ] 9. Record and commit `examples/smart-home/trace.jsonl` (depends on 8) with
      `uv run python examples/smart-home/demo.py --mock --deterministic
      --audit-path examples/smart-home/trace.jsonl --overwrite`.
      — DoD: five lines forming `PROPOSED->AUTHORIZED->EXECUTING->EXECUTED->VERIFYING->SUCCEEDED`,
      each with four non-empty correlation ids; no credential, API key, real hostname or real device
      id anywhere in the file.
- [ ] 10. Add `examples/smart-home/README.md` (depends on 8): the capability table with idempotency,
      the success path and the "AC offline -> ESCALATED" path with short trace excerpts, every flag
      and exit code, the `trace.jsonl` regeneration command, the opt-in real-mode variables
      (`ATAI_API_KEY`, `ATAI_API_ENDPOINT` only; `--real` = real Newton, fake actuator), why a real
      Alice server is not drivable yet (linking mctlhq/mctl-alice#47 and
      mctlhq/newton-mcp-gateway#28), one sentence that `binding_identity` comes from the declared
      placeholder URL while the in-process factory ignores the transport, and the
      `--force-desired-temperature-c` testbed-override label. Alice is described generically, with no
      hosted deployment mentioned.
      — DoD: the document says "mock-validated", never claims a live Newton or live Alice
      integration works, and keeps the contract/runtime described as this project's experimental
      proposal.
- [ ] 11. Add a "Demo" section to the root `README.md` (depends on 10) with the literal
      `uv run python examples/smart-home/demo.py --mock` command, a short excerpt of the success
      trace, and a short excerpt of the `--ac-offline` run ending `ESCALATED`, both labelled mock and
      linking to `examples/smart-home/README.md`.
      — DoD: acceptance criterion 4's README requirement is satisfied by the root README alone.
- [ ] 12. Add one cross-reference sentence to `docs/action-runtime.md` pointing at
      `examples/smart-home/` as the composed end-to-end testbed (depends on 8), and add
      `examples/smart-home/demo-audit.jsonl` to `.gitignore`.
      — DoD: the existing "mock-validated only" wording in that document is preserved, not weakened.
- [ ] 13. Final gate: `uv sync --locked --group dev && uv run pytest -q` is green and
      `git diff --stat` shows no change under `src/newton_mcp/`, `schemas/`, `pyproject.toml` or
      `uv.lock`.
      — DoD: all five acceptance criteria of the issue are demonstrably met; any defect discovered in
      `src/newton_mcp/` while composing the loop is reported in the PR description rather than
      patched here.

## Tests

All in `tests/test_demo.py` unless stated. `demo.py` and `fake_alice.py` are loaded with
`importlib.util.spec_from_file_location` because `examples/` is not an importable package. Mock mode
only — no test may select `--real`, open a socket or read a credential.

- [ ] T1. `run_demo` in mock mode ends `ActionState.SUCCEEDED`, issues exactly one
      `set_ac_temperature` call (from `call_log`), obtains at least one observation, and returns four
      non-empty correlation ids. (Acceptance criterion 1.)
- [ ] T2. The literal documented command, run as a subprocess with `sys.executable
      examples/smart-home/demo.py --mock` and an audit path inside `tmp_path`, exits `0` and prints
      `SUCCEEDED`. (Acceptance criterion 1: "a test invokes it".)
- [ ] T3. `run_demo(ac_offline=True)` ends `ActionState.ESCALATED`, obtains at least one observation
      (so the run passed through a *verified* `FAILED`, not a zero-observation escalation), and
      issues at most `contract.verification.retry_limit + 1` actuator calls. (Acceptance criterion
      2, first half.)
- [ ] T4. An `announce` contract (`idempotent: false`, no `read_tool`) driven through the same
      helper ends `ESCALATED` with **exactly one** `announce` call in `call_log`. (Acceptance
      criterion 2, second half — the non-idempotent single-call rule.)
- [ ] T5. `--force-desired-temperature-c 30` ends `DENIED` with exit code `4`, the audit file holds
      exactly one `PROPOSED -> DENIED` line, and `call_log` is empty. (Acceptance criterion 3.)
- [ ] T6. Direct policy test: `load_policy(examples/smart-home/policy.yaml)` returns `deny` naming
      `target_temperature_c` for a candidate whose args carry `19` and `26`, and `auto` for `20`,
      `23` and `25` (inclusive bounds). (Acceptance criterion 3, at the policy level.)
- [ ] T7. `load_runtime_config(examples/smart-home/runtime.yaml)` validates; every capability
      declares `idempotent` explicitly; `set_ac_temperature`/`set_light_state`/`set_light_brightness`
      are `idempotent: true` and `announce` is `idempotent: false`; no tool name or goal prefix
      contains any `_FORBIDDEN_SUBSTRINGS` term (mirroring
      `tests/runtime/test_config.py::test_example_runtime_config_is_valid_and_safe`).
- [ ] T8. Every capability's tool name and rendered argument keys exist in the discovered
      `fake_alice` catalog: refresh the catalog against the fake and assert
      `snapshot.problems == ()` — the allow-list and the fake cannot drift apart silently.
- [ ] T9. The committed `examples/smart-home/trace.jsonl` parses as JSONL, its `from`/`to` pairs form
      exactly `PROPOSED->AUTHORIZED->EXECUTING->EXECUTED->VERIFYING->SUCCEEDED`, every line carries
      four non-empty correlation ids and a canonical `at`, and no line contains a key matching
      `newton_mcp.runtime.audit.SECRET_KEY_PATTERNS` with a non-`[redacted]` value. (Acceptance
      criterion 4.)
- [ ] T10. `src/newton_mcp/` contains no Alice-specific string: walk `src/newton_mcp/**/*.py` and
      assert none contains `alice`, `fake_alice` or `ALICE_MCP_URL` (case-insensitive).
      (Acceptance criterion 5.)
- [ ] T13. (owner amendment) `run_demo(real=True)` with a monkeypatched live-backend builder
      (returning the mock backend, so no network) still routes every actuator and read call to the
      in-process `fake_alice` `call_log`, prints the "live Newton backend; actuator: in-process fake"
      line, and never reads any Alice-related environment variable; with `ATAI_API_KEY` unset,
      `--real` fails before proposing, naming the variable.
- [ ] T14. (owner amendment) Under `--deterministic`, the AC-offline run's approval `expires_at`
      is later than every `now_fn` value the run produces, and the run ends `ESCALATED` via verified
      `FAILED` (the audit has no approval-rejection reason).
- [ ] T11. `fake_alice`'s `get_room_state` is advertised with `read_only_hint=True` in the catalog
      snapshot, and its returned mapping carries a top-level `temperature_c` the mock contract's
      `verification.condition` path resolves against.
- [ ] T12. The mock-mode demo opens no real transport: assert `run_demo` is reached with the
      in-process `client_factory` (e.g. by asserting every recorded call arrived at the fake's
      `call_log` and the fake's server object is the only one constructed), and that `--mock`
      completes with `ATAI_API_KEY` absent from the environment (`monkeypatch.delenv`).

## Rollback

Every change is additive and confined to new files plus three documentation edits. To roll back:
`git revert` the merge commit, or delete `examples/smart-home/` and `tests/test_demo.py` and revert
the "Demo" section in `README.md`, the cross-reference sentence in `docs/action-runtime.md` and the
`.gitignore` line. Nothing under `src/newton_mcp/`, `schemas/`, `pyproject.toml` or `uv.lock` is
modified, so no consumer of the package, no published schema and no dependency resolution is
affected, and no data migration or state cleanup is involved. If only the recorded artefact is
wrong, `examples/smart-home/trace.jsonl` can be regenerated with the documented command without
touching code. If the demo turns out to be flaky in CI, the narrowest mitigation is to drop the
subprocess test (T2) and keep the in-process tests, which cover the same chain.
