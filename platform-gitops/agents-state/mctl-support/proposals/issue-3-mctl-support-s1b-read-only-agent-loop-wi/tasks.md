# Tasks: issue-3-mctl-support-s1b-read-only-agent-loop-wi

- [ ] 1. Provider configuration in `src/mctl_support/config.py`: `MODEL_PROVIDER`
  (`anthropic` default, `hetzner`), `ANTHROPIC_MODEL`/`ANTHROPIC_API_KEY`,
  `HETZNER_MODEL`/`HETZNER_API_KEY`/`HETZNER_BASE_URL` (default
  `https://inference.hetzner.com/api/v1`), per-model token prices,
  `SUPPORT_MAX_TOOL_CALLS` (25), `SUPPORT_TASK_DEADLINE_SECONDS` (600),
  `SUPPORT_TASK_COST_CAP_USD` (2.00, provisional until S1c),
  `SUPPORT_TOOL_RESULT_MAX_CHARS`, `SUPPORT_CANCEL_POLL_SECONDS`,
  `SUPPORT_CONTEXT_MAX_ITEMS`; secrets in a redacting wrapper; remove
  `SUPPORT_SERVER_THREAD`. `validate()` only checks provider settings when
  `executor == "agent"`. — DoD: `tests/test_config.py` covers each refusal
  (unknown provider, missing model/key, `CLAUDE_CODE_OAUTH_TOKEN` set,
  non-API-key Anthropic key, limits above 25/600) and asserts no key value
  appears in any error message or `repr`.
- [ ] 2. Neutral transcript types and `ModelProvider` protocol in
  `agent/providers/base.py`; `ScriptedProvider` in `agent/providers/scripted.py`
  that replays a list of turns and can block on an `asyncio.Event` for slow
  turns. — DoD: types importable, scripted provider used by later tests.
- [ ] 3. `AnthropicProvider` (`AsyncAnthropic.messages.create`, `anthropic==2.3.0`)
  and `HetznerProvider` (OpenAI-compatible `/chat/completions` over `httpx`),
  each translating neutral items to and from its wire format and reporting
  usage; `capabilities.server_thread = False` for both. (depends on 1, 2) —
  DoD: adapter tests against a scripted HTTP backend (`httpx.MockTransport`
  for Hetzner, the Anthropic client constructed with a mock `http_client`)
  round-trip text, tool calls and tool results; no network in tests.
- [ ] 4. `agent/mcp_client.py`: JSON-RPC client for `<MCTL_API_URL>/mcp`
  (`initialize`, `tools/list`, `tools/call`) with only the run token as
  credential; 401/403 -> denied, other failures -> explicit error. Plus a
  `FakeMcpServer` (httpx `MockTransport`) that records every request and
  enforces tenant binding per token for tests. — DoD: unit tests for denied,
  error, `isError`, non-JSON and success; nothing returns an empty success.
- [ ] 5. `agent/registry.py`: `SUPPORT_READ_TOOLS` allowlist with local input
  schemas, `read_platform_skill`, `escalate` stub, per-task intersection with
  `tools/list`, `dispatch` (unknown name -> local refusal, schema check ->
  local refusal, untrusted-output wrapping, truncation, evidence log). No
  provider-specific code. (depends on 4) — DoD: registry unit tests; the
  unknown-tool test asserts zero requests reached `FakeMcpServer`.
- [ ] 6. `agent/limits.py` (`TaskLimits`, `Budget`, `LimitExceeded`) and
  `agent/cancel.py` (`CancelWatcher` polling the SDK `tasks` status). (depends
  on 1) — DoD: unit tests for the 26th tool call, deadline expiry with an
  injected monotonic clock, cost cap, unknown usage treated as cap reached.
- [ ] 7. `agent/prompt.py` (system prompt with platform policy, four tiers,
  evidence-not-instructions, JSON result instruction, `PROMPT_VERSION`) and
  `agent/result.py` (`SupportResult`, parse, evidence-source check, text and
  data parts). — DoD: tests for valid result, invalid JSON, unknown
  classification, evidence with an unknown source dropped and counted.
- [ ] 8. Schema version 2: `model_transcripts` in `store/schema.py`,
  `CURRENT_VERSION = 2` in `migrate.py`, retention of the table in
  `retention.py`, `agent/transcript.py` load/append with the owner+tenant join
  and elision above `SUPPORT_CONTEXT_MAX_ITEMS`. — DoD: migrate twice is a
  no-op on SQLite and Postgres; retention test deletes expired rows; load for a
  foreign principal or tenant returns nothing.
- [ ] 9. `agent/loop.py` and `agent/executor.py` (`AgentExecutor`): one loop per
  task, working status per turn, limits, cancel guard, one corrective turn for
  an invalid result, terminal-task guard, transcript persistence. (depends on
  2, 5, 6, 7, 8) — DoD: loop tests below pass with the scripted provider.
- [ ] 10. Wire it: `LifecycleExecutor.execute` puts the run token and tenant in
  `call_context.state` for the inner executor and removes them in `finally`;
  `app.build_executor` returns `AgentExecutor` for `agent`; add the run-token
  form to `logging_filter`. (depends on 9) — DoD: existing S1a tests still
  pass; a full-stack test through `/message:send` with the scripted provider
  completes with the result contract in the task.
- [ ] 11. Provider comparison harness `tools/compare_providers.py`, 9 sanitized
  fixtures under `tests/fixtures/diagnostic/` (including planted-instruction
  ones), `RecordedMcpClient`, and the report template
  `docs/reports/s1b-provider-comparison.md`. (depends on 9) — DoD: harness runs
  offline against the scripted provider in CI as a smoke test; the live run
  with both keys produces the report, recording "Production default:
  anthropic" unless the owner decides otherwise.
- [ ] 12. Docs: README configuration table, S1b status and limitations;
  `agent/agent.yaml` description of tools. — DoD: README lists every new
  variable and states no key is needed for development or tests.

## Tests

All tests run with no provider key and no network. Tests T1-T7 are
parametrized over `provider in {anthropic, hetzner}`: the scripted turns are
fed through each real adapter's translation layer against a mocked HTTP
backend, so the registry and loop run identically for both.

- [ ] T1. Cross-tenant: task for tenant A, scripted model calls
  `mctl_get_service_status(team="tenantB", ...)`; `FakeMcpServer` sees only A's
  token and answers 403; the task completes and its result and transcript
  contain no tenant B data.
- [ ] T2. Unknown tools: scripted calls to `kubectl`, `http_request`, `shell`,
  `deploy_service` each return a local refusal; `FakeMcpServer` and any other
  transport record zero requests. Verified to fail when `dispatch`'s allowlist
  check is bypassed (a test that monkeypatches the check off and asserts the
  outbound request then happens, proving the assertion is meaningful).
- [ ] T3. Tool-call limit: a script with 26 tool calls ends `failed` with
  "tool-call limit (25) reached"; exactly 25 calls reached the server.
- [ ] T4. Time limit: a scripted slow turn with an injected clock past 600 s
  ends `failed` with "time limit (10 min) reached".
- [ ] T5. Cost cap: usage above the cap ends `failed` with "cost limit reached".
- [ ] T6. Cancel during a slow tool turn on the same replica and from a second
  app instance (pattern of `tests/test_replicas.py::test_t11...`): the loop
  stops within the turn, the task is `canceled`, `api.revoked` holds the token,
  the execution is finished `Failed`; a later message to the task does not run
  the loop.
- [ ] T7. Context: a context created by user-a in namax66 continues with its
  restored transcript (the scripted provider asserts it received the earlier
  items); the same `contextId` from `tok-other` and from a random id give
  identical errors and no transcript is loaded.
- [ ] T8. Result contract: invalid final JSON gets one corrective turn, then
  fails; invented evidence sources are dropped.
- [ ] T9. Adapter wire tests for both providers (text, tool_use/tool_calls,
  tool results, usage, HTTP error -> "model provider unavailable").
- [ ] T10. Config refusals (task 1) and no secret in logs (caplog check with
  the redaction filter installed).
- [ ] T11. Comparison harness smoke run on the scripted provider over the 9
  fixtures produces a report with every metric column.

## Rollback

- The deployed service stays on `SUPPORT_EXECUTOR=fake` until a separate
  mctl-gitops PR switches it; reverting that values change (or setting
  `SUPPORT_EXECUTOR: fake` again) restores S1a behaviour without an image change.
- Image rollback to `0.1.1` is safe: schema version 2 only adds
  `model_transcripts`, which version 1 ignores; the table can stay or be dropped
  manually later.
- If a provider misbehaves, set `MODEL_PROVIDER=anthropic` (or back) in values;
  no code change. Revoke the provider key at the provider console/project if it
  is suspected leaked.
