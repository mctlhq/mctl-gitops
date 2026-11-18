# Design: issue-1096-spike-devloop-evaluate-claude-code-code

## Current state

Pinned versions: mctl-agents `main` at `2227b47427e82bd2f66a7b2c784042cd76691000`
(2026-11-17). Vendor doc https://code.claude.com/docs/en/code-mode fetched
2026-11-18. Claims credited to the release note (v2.1.323, 2026-11-12) or the
marktechpost article come from the issue and were not independently fetched.

### Runtime harness

- `pyproject.toml` pins `claude-agent-sdk==0.2.174`. Per the comment there and
  in `Dockerfile` (lines 10-16), the wheel bundles the Claude Code CLI, so the
  SDK pin is the CLI pin. In the investigator image,
  `claude_agent_sdk/_cli_version.py` reads `__cli_version__ = "2.1.310"`. That
  is older than the v2.1.323 Code Mode requires.
- Every agent session is a headless SDK session. `orchestrator/options.py`
  builds `ClaudeAgentOptions` for every agent (`build_*_options`, all passed
  through `_scrubbed`), with `permission_mode="acceptEdits"` ("non-interactive
  — meant for cron") and `setting_sources=["project"]`.
  `orchestrator/run_issue_investigator.py` drives the session with
  `ClaudeSDKClient(options=options)` and `client.query(prompt)`. Runs execute in
  Argo pods launched from Temporal (`orchestrator/temporal/activities/argo.py`).
  According to the vendor doc, Code Mode does not work with `-p` or the Agent
  SDK. It is therefore inapplicable to this runtime regardless of version.
- Auth (`orchestrator/auth.py`): `CLAUDE_CODE_OAUTH_TOKEN` is preferred over
  `ANTHROPIC_API_KEY`. Model policy providers (`docs/model-policy-providers.md`,
  `config/model-policy.yaml`) may route sessions to a non-Anthropic `base_url`.
  Code Mode refuses a gateway or custom `ANTHROPIC_BASE_URL`, so provider-routed
  profiles are excluded outright.

### Governance controls, all attached to SDK hooks in `orchestrator/options.py`

- `_command_audit_hooks()` / `_audit_pre_tool_use`: a `PreToolUse` hook on
  `Bash` that prints `AUDIT tool=Bash cmd=... execution_context=...`.
- `_ci_log_guard_hook`: deny patterns over `_normalize_shell_command(command)`.
  The `_GH_GLOBAL_FLAG` commentary shows the repo already treats textual
  shell-command matching as fragile (mctl-agents#423).
- `_PolicyCheckpointHook` (hook on `mcp__.*`): routes every MCP call through
  `orchestrator/policy_checkpoint.py` (ADR 014). It fails closed, decides
  ALLOW / DENY / REQUIRE_APPROVAL, spends approvals once, and records arguments
  only as a digest in a `POLICY_DECISION` line (optionally a durable mctl-api
  decision record, `orchestrator/decision_records.py`).
  `delegated_prefix="mcp__capability__"` hands decisions to the gateway.
- `orchestrator/capability_gateway.py` (ADR 017, mctl-agents#242): exposes
  three tools, `capability_search`, `capability_describe` and
  `capability_invoke`, over one sealed `CapabilitySet`. Discovery narrows and
  never grants, and each invoke goes through its own `PolicyCheckpoint`.
- Identity: `orchestrator/execution_identity.py` (ADR 011, `ExecutionContext`
  with `Actor`, `Scope`, `Correlation`). Evidence:
  `orchestrator/execution_evidence.py` (ADR 018). Redaction:
  `orchestrator/redaction.py` (drop, never mask; 256-char cap). Cost:
  `orchestrator/usage_ledger.py` (ADR 012). Traces: `orchestrator/tracing.py`
  and `tracing_sdk.py` (`docs/observability/execution-traces.md`). Tracing is
  inert unless `OTEL_*` is set. Runtime assurance scenarios: ADR 022/023,
  `orchestrator/runtime_assurance.py`, `orchestrator/assurance_harness.py`,
  fixtures in `tests/fixtures/assurance/` (for example `scenario-fixture.json`,
  `allowlist.json`).

### Existing benchmark precedent

`docs/benchmarks/capability-discovery.md` with `tools/capability_bench.py`
(`schema-bytes`, `compare`) measured eager versus discovery once per mode. The
first-turn reduction was 62%, but end-to-end cost rose 17% and turns went from
30 to 52, with n = 1. Its own conclusion is that a structural first-turn
reduction is not an end-to-end saving (#517). The protocol below reuses this
harness's `ResultMessage` metrics and fixes the n = 1 weakness.

### Interactive operator workflows

No `.claude/` directory, `settings*.json`, operator runbook or interactive
Claude Code configuration exists in the repository (`ls -a .claude`, a file
search for `settings*.json`, and a scan of `docs/runbooks`, `docs/operations`
and `README.md` found none). How owners use interactive Claude Code against
MCTL today is `UNKNOWN`. None of the SDK hooks above run in an interactive CLI
session. Only the server-side mctl-api checks and any user-level hooks the
operator has configured apply there, and the latter are `UNKNOWN`.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/admins/` lists `mctl-agents-worker`,
  `mctl-agents-worker-exec` and `mctl-agents-worker-implement`.
- `services/admins/mctl-agents-worker/values.yaml`: `image.tag: "1.117.0"`. A
  grep for `OTEL` and `TELEMETRY` returned nothing, which is consistent with
  "nothing is exported in production yet" in `execution-traces.md`. This was
  checked only for the worker, not for the `-exec` and `-implement` values.
- The investigator runtime image's bundled CLI is 2.1.310
  (`/app/.venv/.../claude_agent_sdk/_cli_version.py`). Deployed agent pods use
  the same pin via `uv.lock`, so they are inferred to match, not directly
  observed.
- mctl MCP tools were not called. The question needs no tenant or service
  state, and no tenant or hostname is asserted here.
- Vendor doc fetched (see the link above). The release notes and news article
  were not fetched, and claims from them stay `UNKNOWN` unless the vendor doc
  repeats them.

## Proposed solution

This is a documentation-only deliverable: a spike report plus an unexecuted
protocol, kept in the repo's existing spike layout (`docs/spikes/<n>-*.md` plus
a `docs/spikes/<n>/` artefact folder, as in #917 and #918). No runtime code
changes.

Files to produce (after approval of this proposal):

1. `docs/spikes/1096-claude-code-code-mode.md`: status, compatibility matrix,
   no-duplicate map, threat model, governance requirements, recommendation.
   Status line: `STATUS: PROPOSED / BENCHMARK NOT_RUN`.
2. `docs/spikes/1096/protocol.md`: the pre-registered three-task protocol.
3. `docs/spikes/1096/results-template.csv`: one row per (task, mode, rep), every
   metric `NOT_RUN`.
4. `docs/spikes/1096/negative-matrix.md`: negative tests, every cell `NOT_RUN`.
5. `docs/spikes/1096/fixtures/README.md`: fixture manifest (synthetic repo
   snapshot SHA, sanitized CI log bundle, two local fixture MCP servers'
   recorded responses) with content hashes. These are data files only.

### 1. Compatibility matrix (content of the report)

| Dimension | CLI normal tools | CLI Code Mode | MCTL headless SDK / `-p` | mctl discover/describe/invoke (ADR 017) | Cloudflare Portal Code Mode (#63) | API Programmatic Tool Calling |
|---|---|---|---|---|---|---|
| Runtime | interactive terminal | interactive terminal only, native build, >= 2.1.323 | Argo pod, `ClaudeSDKClient`, CLI 2.1.310 | SDK MCP tools inside the headless session | Cloudflare Dynamic Worker behind the portal | Messages API server-side execution |
| Usable by DevLoop today | no (not headless) | **no**, vendor-excluded (`-p`, Agent SDK) | yes | yes (investigator discovery mode) | no, PARK (M8 FAIL) | UNKNOWN, needs its own spike |
| Model eligibility | any | Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.2 | per `config/model-policy.yaml` | same as the session | UNKNOWN | UNKNOWN |
| Hooks | settings hooks per call | `PreToolUse` per child call under the tool's name; a `REPL` hook sees `tool_input.code`; a hook failure or timeout refuses the call | SDK `HookMatcher` hooks (audit, policy checkpoint, CI-log guard, deadline) | gateway-internal `PolicyCheckpoint` per invoke | portal-side; audit failed M8 | none client-side (UNKNOWN) |
| Limits | per tool | 10 min foreground, 2 h background (auto/bypass only) | `exec_budget.py` deadlines, budget | gateway timeouts | UNKNOWN | UNKNOWN |
| Billing | subscription or Console | subscription or Console; not via a gateway, Bedrock, Vertex or Foundry; not ZDR or HIPAA | OAuth token or API key; provider profiles | same as the session | Cloudflare paid | API |
| Audit | transcript | transcript; code visible only via `Ctrl+O`; **OTel export must be off** | `AUDIT` lines, `POLICY_DECISION`, ledger, evidence, traces (inert) | descriptor and decision per invoke | failed | UNKNOWN |
| Security model | rules and hooks | auto-mode classifier reviews code, not runtime-derived arguments | `acceptEdits` plus fail-closed hooks | sealed set; narrows, never grants | n/a | n/a |
| Task fit | any | many related calls, fan-out, filtering | DevLoop stages | MCP tool selection | MCP aggregation | programmatic fan-out |

Genuine overlap: CLI Code Mode and API Programmatic Tool Calling both reduce
round trips for fan-out work. CLI Code Mode and the #63 portal mode both let
code compose tool calls. Unsupported substitutions: Code Mode cannot replace
the headless SDK path, the ADR 017 gateway, or the policy checkpoint.

### 2. Threat model (each risk mapped to a control or a gap)

| Risk | Code Mode behaviour (doc) | MCTL control | Gap / requirement |
|---|---|---|---|
| Runtime-derived arguments | classifier sees the code, not computed values | ADR 014 digests exact args at decision time (SDK only) | in the CLI, rely on per-call `PreToolUse` hooks; the classifier is never a control |
| `cd 'x' && git push` composition | doc example | `_normalize_shell_command` and segment matching (SDK only) | an interactive hook must split compound commands; text rules are bypassable, so use the sandbox for real limits |
| Allowlist vs invocation | `REPL` must be allowed for Code Mode to start | `allowed_tools` and `_PolicyCheckpointHook` grants | allowing `REPL` must not widen the child tools; deny rules still apply per child |
| Hook failure | refused even without `onFailure` | ADR 014 fails closed | consistent; record hook timeouts as denials |
| Cross-tenant principal | UNKNOWN in the doc | ADR 011 `Actor`/`Scope`; mctl-api server-side authz | every child MCP call carries one operator principal; tenant switching inside a script is DENY |
| Parallel / nested children | one script, many calls; a new script drops the earlier one's classifier review (countdown prompt) | none client-side | per-child correlation id: script digest plus ordinal |
| Cancellation / timeout | 10 min / 2 h | `exec_budget.py` (SDK) | a partial script is an incomplete action set and is recorded as such |
| Retry / idempotency | JS may loop | single-use approvals (ADR 014) | read-only only; any retry of a write is out of scope |
| Egress / secrets | JS runs locally with the user's env | `_scrubbed` blanks tokens (SDK only); `redaction.py` | the benchmark runs with no MCTL tokens in env and the sandbox on |
| Attacker tool output | output feeds the next call without model review | treated as untrusted data | negative test N6; output-driven arguments to consequential tools are DENY |
| Audit reproducibility | code in transcript, OTel off | ADR 018 evidence envelope | script digest to child call to decision record chain; no chain means UNKNOWN |

### 3. Governance requirements for any child call reaching MCTL

Per child call there must be an actor and tenant (ADR 011 fields), an argument
digest (`canonical_json` plus `hash_bytes`, as in `policy_checkpoint.py`), an
action-time decision with ADR 014 semantics made by mctl-api or a hook that
calls the same `decide()`, and a durable record. If any of these is unknown,
the call is DENY. The benchmark itself has no consequential calls, so this is a
requirement for any future pilot, not something this spike implements.

### 4. Benchmark protocol (designed, not executed)

- Arms: normal CLI versus Code Mode. Both pin the same native CLI build
  (>= 2.1.323), model (Opus 5.5), prompt, permission mode (default,
  prompt-on-ask; auto mode is a separate optional arm), fresh `CLAUDE_CONFIG_DIR`,
  identity and fixtures. OTel export is off in both arms, and the sandbox is on.
- Tasks: (A) list the call sites of a symbol across a pinned synthetic snapshot
  of this repo; oracle: a precomputed `rg` result set. (B) Classify failing
  checks from a sanitized CI-log fixture bundle; oracle: a labelled JSON. (C)
  Join records from two local fixture MCP servers (recorded responses, no
  network); oracle: an expected join.
- 5 repetitions per task per arm (30 runs) in a randomized interleaved order.
- Metrics: initial and total input/output/cache tokens, turns, tool calls,
  REPL calls, p50/p95 wall time, REPL overhead, CLI-reported cost, oracle
  score, permission denials, and child-correlation completeness, collected from
  the transcript JSONL and hook logs via a `capability_bench.py compare`-style
  parser.
- Vendor claims (fewer round trips, lower tokens) sit in a separate column and
  are never mixed into the baseline.
- Negative matrix (all `NOT_RUN`): N1 deny rule on a child Bash; N2 compound
  `cd && <denied>`; N3 hook timeout leads to refusal; N4 hook crash leads to
  refusal; N5 `REPL` denied means Code Mode does not start; N6 injected fixture
  output tries to steer a write; N7 secret-shaped value in fixture output must
  be dropped from records; N8 a script exceeding 10 min; N9 a second script
  while the first runs (countdown auto-block); N10 an attempted tenant switch in
  task C.

### 5. Recommendation

`FURTHER_RESEARCH`. The evidence supports only an interactive, CLI-only
benchmark. Headless or DevLoop adoption is blocked by the vendor's surface
exclusion, and transfer to the runtime gives nothing the ADR 017 gateway does
not already cover. The next step needs:

- an explicit owner GO;
- an owner-confirmed eligible account;
- a security review of the benchmark profile (hooks, sandbox, no MCTL tokens);
- an estimated cost of roughly 30 runs at about $0.5-2 each (UNKNOWN until a
  pilot rep);
- results reported under #597's ownership, with threat-model findings filed
  against #181/#151 scenario fixtures.

`CLI_ONLY_PILOT` becomes possible only after the benchmark shows a correctness-
preserving saving and every negative test passes. For the runtime the answer
is `REJECT`, unless Anthropic adds Agent SDK support.

## Alternatives

- **Run the benchmark now in this spike.** Dropped: the issue forbids it, and
  it would need a settings change.
- **Fold this into #597's benchmark.** Dropped: #597 owns the Enterprise MCP
  benchmark for the headless runtime, and Code Mode is a different surface.
  Only the reporting is shared.
- **Evaluate API Programmatic Tool Calling instead, as the headless-capable
  analogue.** Recorded as the most plausible runtime-transfer path, but it is a
  different product and needs its own issue; this one stays scoped.
- **Reopen the #63 portal A/B.** Dropped: it is PARK after M8 FAIL.

## Platform impact

- No migrations, runtime changes, image or SDK bumps, or settings changes. Only
  docs and fixtures are added. Backward compatible.
- Resource impact: none until an owner GO. The later benchmark costs about 30
  interactive runs.
- Risk: the report is read as approval to enable Code Mode. Mitigation: the
  status line, explicit `NOT_RUN` cells, and a recommendation that names the
  gate. Optionally the report records the managed-settings value `0` that an
  organization can use to block Code Mode.
- Risk: vendor docs change, since the feature is experimental. Mitigation: pin
  the fetch date and re-fetch at execution time.
