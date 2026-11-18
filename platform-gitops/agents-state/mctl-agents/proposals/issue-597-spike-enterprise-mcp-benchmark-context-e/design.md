# Design: issue-597-spike-enterprise-mcp-benchmark-context-e

## Current state

**Exposure modes in code**

- `orchestrator/run_issue_investigator.py:183,202` selects `ISSUE_INVESTIGATOR_CAPABILITY_MODE` from `("eager", "discovery")`, with `eager` as the default.
  - In `eager`, the CLI connects `mctl_mcp_config(always_load=True)` (`orchestrator/options.py:91`) to `https://api.mctl.ai/mcp`. It loads every advertised `mcp__mctl__*` schema into the first turn, and the wildcard only filters permissions.
  - In `discovery` (lines ~2400-2470), the run requires `MCTL_TOKEN` and the resolved plan's capability discovery. It serves the three gateway tools from `CapabilityGateway.sdk_tools()`.
- `orchestrator/capability_gateway.py`:
  - `CapabilityGateway.build()` discovers providers once, seals a `CapabilitySet` and emits a `set_sealed` trace through `_emit_trace` (line 734).
  - `search` / `describe` / `invoke` serve only from the sealed set.
  - Every invoke passes a `PolicyCheckpoint`: `PolicyDecidePolicyCheckpoint` (line 776), or `AbsentPolicyCheckpoint` when none is configured.
  - Every invoke emits an `invocation` trace of `InvocationRecord.to_dict()` (`_trace`, line 1301). `InvocationRecord` (`orchestrator/capability.py:1150`) is hash-only: `arguments_hash` and `result_hash`, never payloads. It also records `policy_checkpoint` (`allowed` / `denied` / `absent`), `outcome`, `reason_code` and `duration_ms`.
- The eager path has a separate PreToolUse audit hook (`orchestrator/options.py:567` `_audit_pre_tool_use`, registered at 602/617). It sends execution-identity headers (`X-Mctl-Execution-Context`, `X-Mctl-Trace-Id`, `options.py:88`).
- Provider endpoints: `orchestrator/resolver.py:135` `_CAPABILITY_ENDPOINTS = {"mctl-api-mcp": MCTL_MCP_URL}`. The gateway can reach only mctl-api today. It cannot reach `tg.mctl.ai` or any other upstream.

**Benchmark tooling and evidence**

- `tools/capability_bench.py` has two commands:
  - `schema-bytes` is a live listing that compares eager input-schema bytes with the three gateway schemas.
  - `compare EAGER.json DISCOVERY.json` sums `ResultMessage` usage through `UsageRecorder._plan` / `_commit`, without delivery.

  `compare_report` hard-codes `sample_size: 1`. The tool takes exactly one transcript per mode, counts no tool calls, scores no success, computes no percentiles and checks no permissions or audit. It is unit-tested in `tests/test_capability_bench.py` (`test_compare_report_states_the_sample_size` and others).
- `docs/benchmarks/capability-discovery.md` records the 2026-09-26 run: n=1 per mode, first turn 61,213 against 23,392 tokens, end-to-end 30 against 52 turns, $5.24 against $6.10, and no `capability_invoke`. Its "How to reproduce" section captures `ResultMessage`s by wrapping `usage_ledger.UsageRecorder.observe`.
- ADR 017 (`docs/adr/017-capability-discovery-and-gateway-contract.md`) is the exposure contract. ADR 020 is commerce, not relevant here.

**Deployed state checked**

- `mctl_get_service_status(team=labs, service=mctl-telegram)`: ArgoCD `labs-mctl-telegram` is Healthy/Synced, image `0.139.5`, host `tg.mctl.ai`, port 8080, has a database. This confirms that the Telegram upstream named in the issue exists in tenant `labs`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: `PUBLIC_BASE_URL` / `OAUTH_ISSUER_URL` = `https://tg.mctl.ai`, and `/mcp` is guarded by an `ALLOWED_ORIGINS` allowlist.
- `grep mcp.mctl.ai` over `platform-gitops/`: no `services/*/values.yaml` hit. The only hits are in prior proposals (`agents-state/.github/proposals/issue-195-...` and `issue-292-...`), which describe `mcp.mctl.ai` as the Cloudflare MCP Portal audience. The Portal is not a gitops-managed service, so its current `code_mode` / `minimize_tools` setting could **not be observed** from this run. That gap is recorded under Open questions, and the setting is not assumed absent.
- `services/` lists the tenants `admins`, `karabu`, `labs`, `namax66` and `redloop`. No tenant or service was invented.

## Proposed solution

This is a decision spike. The implementer's deliverable is offline tooling, an experiment plan and the benchmark document with `NOT_RUN` cells. Live repetitions and the final recommendation are operator steps under an approved plan. No runtime path changes.

### 1. Benchmark task set (in the doc, versioned)

The task set is added as a new section of `docs/benchmarks/capability-discovery.md`, versioned `task-set v1`. Each class uses a short, fixed prompt rather than a full issue investigation, which keeps the cost per run low and makes tool use mandatory:

- **TC1 roadmap investigation (mctl-api).** "Report the status and ready items of epic `enterprise-mcp`." Oracle: invokes `mctl_get_epic_status` and/or `mctl_get_ready_work_items` with `epic` resolving to the enterprise-mcp epic, and the answer names the publication `capturedAt`. Read-only.
- **TC2 platform triage (mctl-api, a second tool family).** "Summarise active incidents for tenant `labs` and the health of service `mctl-telegram`." Oracle: invokes `mctl_list_incidents(team=labs)` and `mctl_get_service_status(team=labs, service=mctl-telegram)`, and the answer contains the observed sync and health. Read-only.
- **TC3 Telegram / cross-upstream.** A read-only research query against `tg.mctl.ai` pilot data, plus one mctl-api lookup. Oracle: at least one tg capability and one mctl capability are invoked, and the answer cites the expected fixture fact. Under mctl-native discovery this class is `not measurable (provider tg not registered in _CAPABILITY_ENDPOINTS)` unless the operator plan says otherwise.
- **Negative probes** (one per mode, not scored for cost). The prompt asks for a consequential tool that is not eligible, such as `mctl_deploy_service`. Oracle: the tool is never visible or invokable in discovery, and is refused by the policy/permission layer in eager. This feeds `permission_preserved`.

Each oracle is stored as a YAML fixture, `tools/bench_tasks/<id>.yaml`, holding `prompt`, `expected_capabilities`, `argument_constraints`, `answer_facts` and `consequential`. TC1 and TC2 are fully mctl-api, so the three-class minimum stays comparable across both required arms.

### 2. Extend `tools/capability_bench.py` (offline, pure)

The existing two-mode `compare` is generalised without breaking it:

- **New `capture` format.** A run record is a JSON object with these fields:
  - `run_id`, `mode`, `task_id`, `model`, `profile_version`, `catalog_digest`;
  - `result_messages`, the existing `ResultMessage` shape;
  - `tool_calls`: a list of `{name, capability_id?, kind: discovery|describe|invoke|direct, arguments_hash, is_retry}`, captured from `AssistantMessage` tool_use blocks. Arguments are hashed and never stored;
  - `invocation_traces`: the gateway `invocation` trace dicts, or eager PreToolUse audit entries;
  - `first_turn_cache_creation_tokens`;
  - `wall_clock_ms`;
  - `final_answer_digest`, plus `oracle_facts_found`, which the operator-side scorer computes locally so the answer text itself is not stored.
- **New `aggregate RUNS_DIR --tasks tools/bench_tasks`.** It groups records by `(task, mode)` and computes per cell:
  - n;
  - mean and median of initial and total tokens, separately;
  - turns;
  - discovery, describe, invoke and retry counts;
  - p50/p95 `wall_clock_ms` and `duration_api_ms`, with p95 only when n >= 5;
  - oracle success rate;
  - `permission_preserved`: false if any invoked or visible capability is outside `expected_capabilities ∪ eligible set`;
  - `audit_complete`: every consequential invoke has a matching trace with a `policy_checkpoint` other than `absent`, plus actor/tenant correlation.
- **Cell rendering.** A cell with no records renders `NOT_RUN`. A mode listed in `--not-measurable mode=reason` renders `not measurable: <reason>`.
- **Structural delta.** `aggregate` reads the existing `schema-bytes` output and the 61,213 / 23,392 baseline, and reports the first-turn delta next to the end-to-end delta.
- **Compatibility.** `compare_report` keeps its signature and output, so the existing tests pass. The new code reuses `_totals_for_transcript`.
- **Pure core.** Every new function is pure. I/O stays in thin `_cmd_*` wrappers, matching the file's existing convention.

### 3. Capture hook (operator-side, no runtime change)

The doc's "How to reproduce" is extended with a capture recipe. It wraps `UsageRecorder.observe`, as the current doc already instructs, records tool_use blocks and gateway `_emit_trace` lines from stdout, and writes the run record. `orchestrator/` is not changed.

### 4. Experiment plan and research matrix (docs)

- **Bounded experiment plan.** A new section of `docs/benchmarks/capability-discovery.md` states the pins:
  - model `claude-opus-5` (or a cheaper pinned model, stated);
  - profile `issue-investigator-default` version;
  - identity/tenant;
  - catalog digest;
  - repetitions (5 per cell);
  - USD cap;
  - modes;
  - the isolation and rollback steps for any Portal test mode;
  - explicit operator approval.

  The sequence is plan first, approval second, runs third.
- **Mode applicability matrix.** Rows are eager, mctl-native, Portal `minimize_tools` and Portal `search_and_execute`, plus the research-extension rows: Claude Code interactive Code Mode, Agent SDK / `claude -p` headless, and Anthropic Programmatic Tool Calling. Columns are environment, tool surface, identity/policy check, sandbox, audit, rollback, limitations and evidence link. Unverified facts read `UNKNOWN`. The #63 M8 FAIL is cited as a hard gate on `search_and_execute`.
- **Adjunct section.** A separate "Adjunct (non-comparable)" section is reserved for the companion #1096 interactive experiment, with its own vocabulary.

### 5. Decision section

A "Decision" section keeps the placeholder `PENDING: requires measured cells` until the operator fills it after the runs. Its decision rule is written down in advance so the verdict is not post-hoc:

- **ADOPT_MCTL_NATIVE** if all of the following hold:
  - discovery's median total cost is at most eager's on at least 2 of 3 classes;
  - the success rate is not lower by more than one run out of 5;
  - permission and audit both pass.
- **ADOPT_PORTAL_MODE** only if a Portal mode beats both arms and passes the M8 per-call audit gate.
- **HYBRID** only with stated, non-overlapping responsibilities.
- **DEFER** otherwise.

The guardrails for any later rollout are:

- a per-profile flag, default off;
- a canary of one agent;
- automatic fallback to eager on gateway error;
- no rollout without `audit_complete` = 100%.

The follow-up issue(s) are named when the decision is posted.

## Alternatives

- **Re-run the full issue-investigator n times per mode, as in the 2026-09-26 run.** Dropped as the primary design. It costs about $5-6 per run, it is dominated by repository-exploration variance (the 30 against 52 turn gap was not gateway cost), and it still may not invoke tools. Short task prompts with an oracle isolate the exposure effect.
- **New standalone benchmark harness and document.** Dropped. The issue requires updating `docs/benchmarks/capability-discovery.md`, and `tools/capability_bench.py` already has the token-delta math, verified by `tests/test_capability_bench.py`.
- **Register `tg.mctl.ai` as a gateway provider so TC3 is measurable in discovery.** Dropped from this spike. It is a runtime change to `orchestrator/resolver.py` and the profile catalog, beyond a benchmark spike. It is recorded as `not measurable` with the reason, and becomes a candidate follow-up if the decision favours mctl-native.
- **Emulate Portal Code Mode with a local JS executor.** Forbidden by the issue ("do not emulate it with a different mechanism").

## Platform impact

- **Migrations and runtime.** None. No change to `orchestrator/`, profiles, Portal configuration or deployed services. `ISSUE_INVESTIGATOR_CAPABILITY_MODE` stays `eager` by default.
- **Backward compatibility.** `capability_bench.py compare` keeps its output, and the new subcommands are additive.
- **Cost.** The implementer's PR has no model cost beyond its own run. The operator's measured runs are bounded by the approved USD cap: about 30 short runs, plus negative probes.
- **Risks and mitigations:**
  - **Private data in telemetry.** Run records store hashes, ids and counts only. The scorer evaluates the answer text locally and persists only `oracle_facts_found` plus a digest.
  - **Accidental consequential calls.** Task prompts are read-only. Negative probes target tools that are ineligible or refused, and run in a test identity with a scratch `agents-state` and the `gh` write shim used in the 2026-09-26 run.
  - **Portal mutation.** Portal modes are tested only on an isolated test portal or not at all. The current production `code_mode: off` is never edited.
  - **Over-reading small samples.** n and p95 are suppressed below 5, and the decision rule is fixed before the runs.
