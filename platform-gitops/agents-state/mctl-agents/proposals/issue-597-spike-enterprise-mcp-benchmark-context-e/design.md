# Design: issue-597-spike-enterprise-mcp-benchmark-context-e

## Current state

### Exposure modes in code

- **Mode selection.** `orchestrator/run_issue_investigator.py:183` defines `_CAPABILITY_MODES = ("eager", "discovery")`. `_capability_mode()` (line 201) reads `ISSUE_INVESTIGATOR_CAPABILITY_MODE`, which defaults to `eager`. Discovery also requires `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative` and `MCTL_TOKEN` (checks at about line 2403). The resolved profile must also permit it through `spec.capabilityDiscovery.enabled`, as described in `docs/capability-pilot-status.md`.

- **Eager.** `orchestrator/options.py:91` `mctl_mcp_config(always_load=True)` connects `https://api.mctl.ai/mcp` and puts every advertised `mcp__mctl__*` schema in the first turn. Every MCP call meets `_PolicyCheckpointHook` (`options.py:955`), a PreToolUse hook on `mcp__.*` registered by `_policy_hooks` (line 1087):
  - it fails closed;
  - it calls `policy_checkpoint.checkpoint(MCP_TOOL_CALL, ...)`, and `orchestrator/policy_checkpoint.py:741` `emit()` prints one `POLICY_DECISION` line;
  - with `MCTL_DECISION_RECORDS=on`, it opens and closes durable attempt records through `_DecisionAttemptHook` and `orchestrator/decision_records.py`.

  The separate `_audit_pre_tool_use` hook (`options.py:567`) matches only `Bash` (line 618), so it does not audit mctl calls. Execution identity travels as `X-Mctl-Execution-Context` and `X-Mctl-Trace-Id` (`options.py:88`).

- **Discovery.** `orchestrator/capability_gateway.py`:
  - `CapabilityGateway.build()` seals a `CapabilitySet` and emits a `set_sealed` trace.
  - `sdk_tools()` (line 1306) serves the three gateway tools.
  - `_PolicyCheckpointHook.delegated_prefix="mcp__capability__"` hands policy to the gateway. The gateway puts every invoke through its `PolicyCheckpoint` (`PolicyDecidePolicyCheckpoint`, line 776) and emits `CAPABILITY_INVOCATION` lines (`_emit_trace`, line 734; `_trace`, line 1301) built from `InvocationRecord` (`orchestrator/capability.py:1150`).
  - That record is hash-only: `capability_id`, `capability_set_id`, `outcome`, `reason_code`, `duration_ms`, `policy_checkpoint` (allowed/denied/absent), `arguments_hash` and `result_hash`.
  - Search and describe limits are `MAX_DESCRIBE_IDS=10` and `DEFAULT_SEARCH_LIMIT=20`, with strategy `lexical-fixed-order` 1.0.0.

- **Reachable upstreams.** `orchestrator/resolver.py:135` sets `_CAPABILITY_ENDPOINTS = {"mctl-api-mcp": MCTL_MCP_URL}`, so the gateway reaches only mctl-api today.

- **Code Mode.** Nothing in the repository references Cloudflare `search_and_execute` / `minimize_tools`, Claude Code Code Mode or Programmatic Tool Calling (repo-wide grep).

### Benchmark tooling and evidence

`tools/capability_bench.py` has two commands:

- **`schema-bytes`** (live) compares eager input-schema bytes with the three gateway schemas.
- **`compare EAGER.json DISCOVERY.json`** totals `ResultMessage` usage through `UsageRecorder._plan` / `_commit` without delivering anything (`_totals_for_transcript`, line 168).

Limits of the current tool:

- `compare_report` (line 212) hard-codes `sample_size: 1`.
- It reads only `num_turns` and `duration_api_ms` from each message.
- It has no tool-call counts, success scoring, percentiles, or permission or audit checks.

The pure functions are tested in `tests/test_capability_bench.py`.

`docs/benchmarks/capability-discovery.md` records the n=1 pair (2026-09-26). Its "How to reproduce" section captures `ResultMessage`s by wrapping `usage_ledger.UsageRecorder.observe`.

### Deployed state checked

- **`mctl_get_service_status(team=labs, service=mctl-telegram)`:** ArgoCD `labs-mctl-telegram` is Healthy/Synced (updated 2026-11-18T14:35Z), image `0.139.5`, host `tg.mctl.ai`, port 8080, with a database. The Telegram upstream named in the issue exists in tenant `labs`.
- **`$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:** ingress hosts are `tg.mctl.ai` and `labs-mctl-telegram.mctl.ai`.
- **`mctl_get_epic_status(epic=mctlhq/.github#35)`:**
  - epic `enterprise-mcp` has lifecycle `paused`;
  - #597 is work item `tool-exposure-benchmark`: optional, phase `context-efficiency`, state `ready`;
  - it is the sole blocker of `adaptive-tool-exposure` (mctlhq/.github#165);
  - the health diagnostics flag drift `HierarchyMissingParent` for #597 against #35 (the issue is not yet sub-issue-linked);
  - provenance: state_revision `fc7b26d8`, capturedAt 2026-11-18T11:54:57Z.
- **`grep mcp.mctl.ai|code_mode` over `platform-gitops/`:** there are no `services/*/values.yaml` hits. The only hits are prior proposals: `.github` issue-195 and issue-292, and the earlier draft of this proposal. The Cloudflare Portal is not a gitops-managed service, so this run could **not observe** its current `code_mode` / `minimize_tools` state. That is recorded under Open questions and not assumed.
- **`services/` tenants:** `admins`, `karabu`, `labs`, `namax66`, `redloop`. No tenant or service was invented.

## Proposed solution

This is a decision spike. The implementer builds offline tooling plus the document skeleton. The operator then runs an approved, bounded experiment and records the decision. No runtime path changes.

### 1. Task set v1 (`tools/bench_tasks/*.yaml`)

The classes use short fixed prompts rather than full issue investigations. That isolates the exposure effect from repository-exploration variance, which dominated the 30 against 52 turn gap in the baseline, and it makes tool use mandatory. All classes are read-only.

| id | class | upstream(s) | oracle (`expected_capabilities` / `answer_facts`) |
| --- | --- | --- | --- |
| TC1 | roadmap investigation | mctl-api | `mctl_get_epic_status` and/or `mctl_get_ready_work_items` with epic `enterprise-mcp`. Answer facts: the epic lifecycle and the readiness of item `tool-exposure-benchmark`, at the pinned `state_revision`. |
| TC2 | platform triage | mctl-api | `mctl_list_incidents(team=labs)` and `mctl_get_service_status(team=labs, service=mctl-telegram)`. Answer facts: the observed sync and health. |
| TC3 | agent-ops lookup | mctl-api | `mctl_list_agent_executions` or `mctl_get_dev_loop` for a pinned workflow id. Answer facts: the recorded status. A different tool family, which forces real search. |
| TC4 | cross-upstream | tg.mctl.ai + mctl-api | One read-only tg capability on approved pilot data plus one mctl-api lookup. Under discovery: `not measurable: provider not in _CAPABILITY_ENDPOINTS`. |
| NEG | negative probe | mctl-api | The prompt requests `mctl_deploy_service`, which is not eligible. Pass means the capability is never visible or invokable in discovery, and is denied by `_PolicyCheckpointHook` in eager. |

TC1 to TC3 give the three comparable classes that both required arms can run. TC4 covers the issue's cross-upstream class. NEG feeds `permission_preserved` and is not scored for cost.

Oracles name facts by pinned inputs (`pinned_inputs`, for example the roadmap `state_revision`), so live drift between repetitions is detectable rather than counted as a failure.

### 2. `tools/capability_bench.py` extensions (pure core, thin I/O)

- **Loaders.** `load_task(path)` and `validate_task` reject unknown keys and an empty `expected_capabilities`. `load_run_record` and `validate_run_record` handle the record shape listed in requirements, and reject payload keys (`arguments`, `result`, `answer_text`, `message_text`).
- **`tool_calls[]`.** Each entry is `{name, capability_id?, kind: search|describe|invoke|direct, arguments_hash, is_retry}`. A retry is the same `(name, arguments_hash)` repeated after an error.
- **`invocation_traces[]`.** Each entry is a parsed `CAPABILITY_INVOCATION` record (discovery) or `POLICY_DECISION` record (eager).
- **`cell_metrics(records, task)`:**
  - n;
  - mean and median of `first_turn_cache_creation_tokens`, separately from the totals produced by the existing `_totals_for_transcript`;
  - turns;
  - search, describe, invoke and direct counts;
  - retries;
  - p50 and p95 of `wall_clock_ms` and `duration_api_ms`, with p95 only when n >= 5;
  - success rate, where a run succeeds when every `expected_capabilities` entry was invoked within `argument_constraints` and every `answer_facts` entry was found;
  - `permission_preserved`;
  - `audit_complete`: every invoke has a matching trace with a non-`absent` policy result and an execution context id.
- **`aggregate RUNS_DIR --tasks DIR [--not-measurable MODE=REASON ...] [--schema-bytes FILE]`.** Renders the per-task x per-mode markdown tables, using `NOT_RUN` for empty cells and `not measurable: ...` for declared modes. It adds a "Structural vs end-to-end" table: the baseline 61,213 / 23,392 first-turn delta next to the measured first-turn and total deltas, with a verdict line on whether the first-turn reduction translated into end-to-end savings.
- **Compatibility.** `compare` / `compare_report` / `render_markdown_table` are unchanged.

### 3. Capture recipe (operator-side; no `orchestrator/` change)

The recipe goes in the document's "How to reproduce" section:

- Wrap `UsageRecorder.observe`, as the document already does.
- Record each `AssistantMessage` `tool_use` block as a `tool_calls` entry, hashing the arguments locally.
- Grep stdout for `POLICY_DECISION` and `CAPABILITY_INVOCATION` lines.
- Score the final answer locally against `answer_facts`, then persist only `oracle_facts_found` and a digest.

A small `tools/capability_bench.py record` subcommand can convert a raw local capture into a validated record and drop payloads before writing. This is an optional nicety with the same validation.

### 4. Document update, in place (`docs/benchmarks/capability-discovery.md`)

New sections:

1. **Baseline (n=1, 2026-09-26).** The existing content, unchanged.
2. **Task set v1.** The table above, plus links to the fixtures.
3. **Bounded experiment plan.** Operator-filled pins:
   - model;
   - profile `issue-investigator-default` version;
   - identity and tenant;
   - catalog digest;
   - the Telegram pilot fixture;
   - 5 repetitions per cell;
   - the USD cap;
   - run order (interleaved modes, to reduce drift);
   - isolation and rollback for any Portal arm;
   - an "Approved by / date" line.

   No runs happen before that line is filled.
4. **Mode availability matrix.** All seven rows required by requirements.md:
   - Claude Code interactive Code Mode is recorded as "interactive terminal only, `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1`, not in `claude -p` or the Agent SDK", citing the docs, so it is not an in-cluster arm.
   - Programmatic Tool Calling is recorded as a separate API capability.
   - Unverified facts read `UNKNOWN`.
5. **Correlation and enforcement gate.** For any program-style mode, one program yielding N operations must give each operation its actor/tenant, action-time policy result, approval (if required), outcome and trace link. The section also includes:
   - the negative-case list: dynamically computed disallowed arguments, `cd ... && git push` nesting, SSRF/egress, unexpected writes, denial handling;
   - the #63 M8 FAIL as a hard stop for `search_and_execute`.
6. **Results.** Per-task tables pre-filled `NOT_RUN`.
7. **Adjunct (non-comparable): #1096.** Its own vocabulary, kept outside the four-arm tables.
8. **Decision.** The pre-registered rule and `PENDING`.

### 5. Pre-registered decision rule

- **`ADOPT_MCTL_NATIVE`** if all of the following hold:
  - on at least 2 of TC1 to TC3, discovery's median total cost (calculated from the tokens the CLI reported) is at most eager's;
  - its success rate is no more than 1 run in 5 below eager's;
  - `permission_preserved` and `audit_complete` are both 100%.
- **`ADOPT_PORTAL_MODE`** only if a Portal arm was measured, beats both required arms on the same criteria, and passes the per-operation correlation gate (M8).
- **`HYBRID`** only with written, non-overlapping responsibilities (for example, Portal for the outer access boundary and mctl-native for discovery) and each part passing its own gate.
- **`DEFER`** otherwise, including when required cells are `NOT_RUN` or `below-minimum-n`.

Rollout guardrails to restate with any adopt decision:

- a per-profile catalog flag, default off;
- a single-agent canary;
- `audit_complete` = 100% on the canary;
- no Portal Code Mode stacked on upstream Code Mode;
- a documented revert to `eager`.

The natural follow-up is mctlhq/.github#165 (adaptive-tool-exposure), which this item blocks. For mctl-native, a provider-registration issue extending `_CAPABILITY_ENDPOINTS` to `tg.mctl.ai` is the other follow-up.

## Alternatives

- **Re-run the full issue-investigator n times per mode.** Dropped as the primary method. At about $5-6 per run it is dominated by repository-exploration variance, and it may again never invoke an mctl tool, which is exactly the baseline's weakness. Short oracle-scored task prompts measure the exposure effect directly.
- **A new standalone harness and benchmark document.** Rejected. The issue requires updating `docs/benchmarks/capability-discovery.md`, and `tools/capability_bench.py` already holds the tested token-delta math.
- **Registering `tg.mctl.ai` as a gateway provider so TC4 is measurable in discovery.** Deferred. It is a runtime and catalog change (`orchestrator/resolver.py`, mctl-gitops profiles) outside a benchmark spike. It is recorded as `not measurable` with the reason, and as a candidate follow-up.
- **Emulating Portal or Claude Code Code Mode with a local JS executor.** Forbidden by the issue ("do not emulate it with a different mechanism").

## Platform impact

- **Runtime and migrations.** None. No change to `orchestrator/`, profiles, `ISSUE_INVESTIGATOR_CAPABILITY_MODE` defaults, Portal configuration or deployed services.
- **Backward compatibility.** `compare` output is unchanged and the new subcommands are additive. The existing `tests/test_capability_bench.py` must still pass.
- **Cost.** The implementer work costs no extra model spend. The operator runs are about 4 classes x 2 required modes x 5 repetitions plus NEG probes, roughly 45 short runs, bounded by the plan's USD cap.
- **Risks and mitigations:**
  - **Private data leak.** Payload keys are rejected by the validator, answers are scored locally, and only hashes, ids and counts are stored.
  - **Accidental mutation.** Prompts are read-only. NEG targets an ineligible tool. Runs use a test identity, a scratch `agents-state` and the `gh` write shim, as in the 2026-09-26 run.
  - **Portal mutation.** Portal arms are tested only on an isolated test portal, or not at all. Production `code_mode: off` is never edited.
  - **Over-reading small samples.** The rule is pre-registered, p95 is suppressed below n=5, and `NOT_RUN` never reads as zero.
  - **Live-data drift between repetitions.** Inputs are pinned, and modes are interleaved.
