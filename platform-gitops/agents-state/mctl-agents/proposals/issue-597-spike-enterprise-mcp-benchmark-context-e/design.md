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

## Review resolution — enforceable research-only gates

| Finding | Proposal amendment | Verification requirement |
| --- | --- | --- |
| P1 implementer authorization | This is *only* a proposed research design. No Tier-2, target code/docs PR, fixture writing or real benchmark is authorized. | Explicit separate owner GO bound to future target scope, after independent re-review |
| P1 unsafe eager fallback | Automatic fallback is prohibited for errors and unknowns; policy/authn/tenant/catalog/approval problems fail closed. | Any future non-security recovery requires typed allowlist, same sealed eligible set, same identity and full trace; negative tests |
| P2 insufficient comparable tasks | TC1 roadmap, TC2 platform triage, TC3 agent ops: all mctl-api and measured in both required arms; TC4 Telegram cross-upstream is separate applicability test. | No runtime provider registration just to make TC4 measurable |
| P2 ambiguous audit | Trace hash is not an action identity. Stable run/parent/child/policy-decision/outcome chain required with 1:1 joins. | Unmatched, multimatched, missing durable receipt or unobserved identifiers => `INCOMPLETE` |
| P2 oracle grants permissions | Eligibility from the sealed profile/policy snapshot, not expected capabilities. | Independent eligible-set snapshot/digest and excluded-set negative proof |
| P2 adoption regression | No correctness or security regressions tolerated; exploratory n=5 is not enough for strong adoption claims. | Confirmatory sample/power criteria and 100% observed governance before ADOPT; otherwise DEFER |
| P1 raw result persistence | Raw SDK `ResultMessage` is excluded from persisted schema. In-memory projection produces allowlisted numeric `usage_summaries[]` only, with recursive rejection of all unknown/payload-bearing nested keys. | Tests inject nested response text into arrays/maps and assert **no durable write**; legacy `compare` unchanged |
| P2 eager exposure != permission | Eager's advertised schemas are a separate exposure metric; policy denies forbidden execution. Discovery additionally requires filtered exposure of sealed eligible capabilities. | Mode-specific NEG: eager DENY+no execution+audit, discovery no exposure+no execution+audit |
| P2 alternative tools | Positive task oracles use `required_all` and `required_any_of` groups; all allowed alternatives remain independently subject to eligibility checks. | TC1/TC3 single-alternative success, TC2 conjunctive success, malformed group rejection |

**Never signal Temporal `approve` for research-only completion**: it launches
Tier-2. Existing `.status.yaml` must remain `proposed`, and all actual
measurements remain `NOT_RUN` until a separate operator GO.


## Proposed solution

This is the **research-only proposal** for a later decision-quality benchmark.
The current deliverable is the revised GitOps plan. The offline tooling,
task fixtures and canonical document changes below describe a candidate
implementation **not authorized by this research-only GO**. An explicitly
approved follow-on tooling scope would be necessary before any implementer
or mctl-agents PR. A distinct operator-approved experiment would then be
necessary for runs. No runtime-path changes are proposed.

### 1. Candidate task set v1 (`tools/bench_tasks/*.yaml`; NOT CREATED)

The classes use short fixed prompts rather than full issue investigations. That isolates the exposure effect from repository-exploration variance, which dominated the 30 against 52 turn gap in the baseline, and it makes tool use mandatory. All classes are read-only.

| id | class | upstream(s) | oracle (task-success predicates, **not** permission) |
| --- | --- | --- | --- |
| TC1 | roadmap investigation | mctl-api | `required_all=[]`; `required_any_of=[["mctl_get_epic_status", "mctl_get_ready_work_items"]]`; one valid tool path plus all pinned `answer_facts` (epic lifecycle + readiness) is sufficient. If one path lacks the facts, scoring fails on facts even when the tool alternative matched. |
| TC2 | platform triage | mctl-api | `required_all=["mctl_list_incidents", "mctl_get_service_status"]`; `required_any_of=[]`; both must be invoked with pinned arguments and the expected sync/health facts must be present. |
| TC3 | agent-ops lookup | mctl-api | `required_all=[]`; `required_any_of=[["mctl_list_agent_executions", "mctl_get_dev_loop"]]`; either may supply the pinned status fact, with argument and answer oracles unchanged. |
| TC4 | cross-upstream | tg.mctl.ai + mctl-api | `required_all` would include the future approved pilot read-only Telegram capability and one mctl-api lookup, only after pinning both. Discovery remains `not measurable: provider not in _CAPABILITY_ENDPOINTS`. |
| NEG | denied consequential probe | mctl-api | `required_all=[]`; `required_any_of=[]`; `consequential=true`; `excluded_capabilities=["mctl_deploy_service"]`. Eager may advertise the schema but must return checkpoint DENY and perform **no execution**; discovery must not expose it in the sealed catalogue and must not execute it. Both require audit evidence. |

TC1 to TC3 give the three comparable classes that both required arms can run. TC4 covers the issue's cross-upstream class. NEG feeds `permission_preserved` and is not scored for cost.

Oracles name facts by pinned inputs (`pinned_inputs`, for example the roadmap `state_revision`), so live drift between repetitions is detectable rather than counted as a failure.

**Oracle semantics:** `required_all` is a conjunction, while every inner group of `required_any_of` is a disjunction; every non-empty group must have at least one authorized successful call. `answer_facts` and `argument_constraints` still must hold. A positive task with both requirement lists empty is invalid. The only exception is a negative probe with `consequential=true` and non-empty `excluded_capabilities`. Never infer permission from a fulfilled oracle; every candidate tool also needs independent profile and action-time authorization.

### 2. Candidate offline record/aggregation contract — NOT AUTHORIZED TO IMPLEMENT

- **Loaders.** `load_task(path)` and `validate_task` enforce `required_all` (list of identifiers), `required_any_of` (list of non-empty lists of identifiers), `excluded_capabilities`, `argument_constraints`, `answer_facts`, `consequential`, and `pinned_inputs`. Positive tasks require at least one tool obligation; negative probes may have no required tool only when a consequential exclusion is present. Malformed groups, unknown keys, non-read-only positives and invalid oracles are rejected. `load_run_record` / `validate_run_record` enforce the strict, **recursive allowlist** specified in requirements; checking only top-level payload names is insufficient.
- **`usage_summaries[]` (sanitized persistent schema).** Each item is a *projection*, not an SDK `ResultMessage`: `{session_id, num_turns, duration_api_ms, model_usage: [{model_id, input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}]}`. Model key is an allowlisted identifier; usage quantities are non-negative bounded integers. The input model messages remain **in-memory only**. Extract counters into a fresh dict, reject any unknown or nested payload fields, validate the complete run record recursively before the write boundary, and atomically persist only validated projected fields. If sanitization or validation fails: refuse the record and write **nothing**. A separate sanitized first-turn numeric observation keeps first-turn cache creation tokens distinct from cumulative totals; provide explicit cumulative-delta semantics. Injecting `result`, `content`, `text` or a nested `message_text` anywhere into the record must fail without emitting bytes. No raw text, SDK message or arbitrary metadata is persisted.
- **`tool_calls[]` (future schema).** Each entry requires `run_id`,
  `parent_execution_id`, unique `child_call_id`, `ordinal`, `name`,
  `capability_id?`, `kind: search|describe|invoke|direct`,
  `arguments_hash`, `actor_id`, `tenant_id`, `eligible_set_digest`,
  `policy_decision_id`, `policy_outcome`, `invocation_outcome`,
  `durable_trace_id`, `is_retry` and `retry_of_call_id?`.
  Repetition of the same arguments hash is **not** evidence of a retry,
  and `expected_capabilities` does not authorize any tool. Sensitive
  argument payloads never enter persisted captures.
- **`invocation_traces[]`.** Parse existing `CAPABILITY_INVOCATION`
  (discovery) and `POLICY_DECISION` (eager) as **candidate** records.
  Require exact unique join on `child_call_id` and
  `policy_decision_id`, plus actor, tenant, arguments digest and
  outcome. Today's logs have **not** been shown to expose the full chain;
  the missing correlation remains `UNOBSERVED` until verified. In
  particular, a matching digest alone cannot make `audit_complete=true`.
- **`cell_metrics(records, task)`:**
  - n;
  - mean and median of `first_turn_cache_creation_tokens`, separately from the totals produced by the existing `_totals_for_transcript`;
  - turns;
  - search, describe, invoke and direct counts;
  - retries;
  - p50 and p95 of `wall_clock_ms` and `duration_api_ms`, with p95 only when n >= 5;
  - success rate: every `required_all` capability was successfully invoked, at least one capability in each `required_any_of` group was successfully invoked, and all pinned argument constraints and answer facts were satisfied. The NEG probe has its separate denial oracle;
  - `permission_preserved`: in **both** modes, no out-of-eligible or excluded capability is actually executed and every attempted disallowed invocation is denied at action time with a durable audit record. Eager advertising an ineligible schema is **not**, alone, a permission failure; count it separately as `exposure_count` and `exposure_outside_eligible_count`. For discovery/filtered modes also require `exposure_filtered=true` (no forbidden results in search, describe or sealed set). Missing eligible-set digest or denial receipts => `UNVERIFIABLE`/failure, never PASS. The oracle is not an authorization source;
  - `audit_complete`: each allowed **and denied** child call must join
    uniquely through run/parent/child IDs to an action-time policy decision
    and durable outcome/trace under the same actor/tenant; missing fields,
    absent policy, ambiguous matches and trace-only hashes fail the gate.
- **`aggregate RUNS_DIR --tasks DIR [--not-measurable MODE=REASON ...] [--schema-bytes FILE]`.** Renders the per-task x per-mode markdown tables, using `NOT_RUN` for empty cells and `not measurable: ...` for declared modes. It adds a "Structural vs end-to-end" table: the baseline 61,213 / 23,392 first-turn delta next to the measured first-turn and total deltas, with a verdict line on whether the first-turn reduction translated into end-to-end savings.
- **Compatibility.** `compare` / `compare_report` / `render_markdown_table` are unchanged.

### 3. Future capture recipe (operator-only, requires experiment GO)

The recipe goes in the document's "How to reproduce" section:

- Observe SDK `ResultMessage`-shaped data only **in process**. Construct the allowlisted `usage_summaries[]` numeric projection and separate sanitized first-turn usage counters. The old document's raw-transcript capture method applies to legacy `compare` **read-side compatibility only**; future run records must not save it, even temporarily. On validation failure refuse the write rather than save-and-redact later.
- Record each `AssistantMessage` `tool_use` block as a *candidate*
  child call and hash its arguments locally; minting a local call id
  does not prove it is the authoritative server's call id.
- Inspect `POLICY_DECISION` and `CAPABILITY_INVOCATION` log lines,
  but **do not** infer completeness from a grep. Unless a verifiable
  one-to-one join with authoritative policy/decision/outcome records is
  available, `audit_complete` must be `INCOMPLETE`.
- Score the final answer locally against `answer_facts`, then persist only `oracle_facts_found` and a digest.

An optional `tools/capability_bench.py record` subcommand may accept an **in-memory** SDK observation and produce only the allowlisted projection. It must not write a raw local capture as an intermediate file, and must validate recursively before any write. The pre-existing `compare` command stays byte-for-byte compatible when reading legacy transcript JSON but has no new persist path.

### 4. Future document update (separate owner GO; canonical path unchanged)

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

### 5. Preliminary decision rule (NOT a current adoption verdict)

- **`ADOPT_MCTL_NATIVE`** if all of the following hold:
  - on at least 2 of TC1 to TC3, discovery's median total cost (calculated from the tokens the CLI reported) is at most eager's;
  - **no observed correctness or task-success regression** versus
    eager on any comparable class; any observed regression => `DEFER`;
  - `permission_preserved` and `audit_complete` are independently
    proven 100% across all tested classes and all negative cases;
  - the required `n>=5` is a **pilot instrumentation floor**, not
    a sufficient basis for adoption: require a pre-registered confirmatory
    sample-size/power plan and uncertainty bounds accepted by the owner.
    Absent that evidence, verdict remains `DEFER`.
- **`ADOPT_PORTAL_MODE`** only if a Portal arm was measured, beats both required arms on the same criteria, and passes the per-operation correlation gate (M8).
- **`HYBRID`** only with written, non-overlapping responsibilities (for example, Portal for the outer access boundary and mctl-native for discovery) and each part passing its own gate.
- **`DEFER`** otherwise, including when required cells are `NOT_RUN` or `below-minimum-n`.

Rollout guardrails to restate with any adopt decision:

- a per-profile catalog flag, default off;
- a single-agent canary;
- `audit_complete` = 100% on the canary;
- no Portal Code Mode stacked on upstream Code Mode;
- a **manual, separately authorized rollback** to an explicitly approved
  eager profile if needed; **never automatic fallback** on gateway errors.
  `DENY`, `REQUIRE_APPROVAL`, identity/tenant mismatch, catalog drift,
  unknown error, policy outage or timeout fail closed. Any explicitly
  reviewed typed non-security recovery must preserve the *same* sealed
  eligible capability set, principal, decision and audit receipts.

The natural follow-up is mctlhq/.github#165 (adaptive-tool-exposure), which this item blocks. For mctl-native, a provider-registration issue extending `_CAPABILITY_ENDPOINTS` to `tg.mctl.ai` is the other follow-up.

### Authorization, correlation and negative-test design

The permitted tool set for each candidate run must be derived from the
versioned execution profile, sealed capability catalogue, tenant and
action-time policy, and represented by an independent
`eligible_set_digest`. An oracle's expected tools are solely a
correctness target. The capture schema must join
`run_id -> parent_execution_id -> child_call_id -> policy_decision_id
-> invocation_outcome -> durable_trace_id` with exact actor, tenant,
arguments digest and policy outcome. A new ID is required for a repeated
call with identical arguments; `retry_of_call_id` identifies real retries.
No join based on `arguments_hash` alone is acceptable. Existing eager
and gateway logs are **sources to verify**, not evidence that this join
already passes. Missing join fields -> `INCOMPLETE`, and cannot be ADOPT.

NEG acceptance must be **mode-sensitive**. Eager may advertise `mctl_deploy_service` among all schemas but must deny an attempted invocation and never execute it; record broad exposure separately. Discovery must not expose that capability through the sealed set or search/describe and must also deny/no-op any forbidden attempt. Neither an attempted denied eager call nor raw visible eager schema alone is proof of unauthorized execution. In both modes any absence of a policy receipt or any unauthorized execution is failure.

For every potential fallback or repair, test `DENY`, `REQUIRE_APPROVAL`,
missing identity, foreign tenant, catalogue mismatch, absent checkpoint,
timeout and unknown errors. All of these must fail closed with no
fallback-to-eager. An explicitly approved non-security recovery is
allowed only if it preserves the exact eligible set and all checks.
Negative-case fixture uses no real production mutation or private data.
All actual negative-case outcomes remain `NOT_RUN`.


## Alternatives

- **Re-run the full issue-investigator n times per mode.** Dropped as the primary method. At about $5-6 per run it is dominated by repository-exploration variance, and it may again never invoke an mctl tool, which is exactly the baseline's weakness. Short oracle-scored task prompts measure the exposure effect directly.
- **A new standalone harness and benchmark document.** Rejected. The issue requires updating `docs/benchmarks/capability-discovery.md`, and `tools/capability_bench.py` already holds the tested token-delta math.
- **Registering `tg.mctl.ai` as a gateway provider so TC4 is measurable in discovery.** Deferred. It is a runtime and catalog change (`orchestrator/resolver.py`, mctl-gitops profiles) outside a benchmark spike. It is recorded as `not measurable` with the reason, and as a candidate follow-up.
- **Emulating Portal or Claude Code Code Mode with a local JS executor.** Forbidden by the issue ("do not emulate it with a different mechanism").

## Platform impact

- **Runtime and migrations.** None. No change to `orchestrator/`, profiles, `ISSUE_INVESTIGATOR_CAPABILITY_MODE` defaults, Portal configuration or deployed services.
- **Backward compatibility.** `compare` output is unchanged and the new subcommands are additive. The existing `tests/test_capability_bench.py` must still pass.
- **Cost.** No tooling or benchmark runs are authorized in this
  research-only phase. The separately approved operator experiment
  would require at least 4 classes x 2 modes x 5 repetitions plus
  NEG probes (roughly 40 or more task runs), with a hard USD cap.
  Cost remains an estimate until a measured pilot is permitted.
- **Risks and mitigations:**
  - **Private data leak.** Raw SDK result objects cannot be persisted in run records; a strict recursive allowlist rejects unknown keys (including nested `result`, `text` and `content`) before the write boundary. Only projected usage counters, opaque IDs, digests and durations are stored. Local oracles score answers in memory.
  - **Accidental mutation.** Prompts are read-only. NEG targets an ineligible tool. Runs use a test identity, a scratch `agents-state` and the `gh` write shim, as in the 2026-09-26 run.
  - **Portal mutation.** Portal arms are tested only on an isolated test portal, or not at all. Production `code_mode: off` is never edited.
  - **Over-reading small samples.** The rule is pre-registered, p95 is suppressed below n=5, and `NOT_RUN` never reads as zero.
  - **Live-data drift between repetitions.** Inputs are pinned, and modes are interleaved.
