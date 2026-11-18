# Benchmark context-efficient MCP tool exposure on real mcp.mctl.ai workloads (decision spike)

## Context

mctlhq/mctl-agents#242 added the mctl-native `CapabilityGateway` (`orchestrator/capability_gateway.py`). With it, a run sees three gateway tools (`capability_search`, `capability_describe`, `capability_invoke`) instead of every `mcp__mctl__*` schema.

The only recorded measurement is `docs/benchmarks/capability-discovery.md` (2026-09-26):

- one run per mode;
- a structural first-turn drop from 61,213 to 23,392 tokens (-62%);
- no end-to-end saving: 30 against 52 turns, $5.24 against $6.10;
- neither run invoked an mctl tool.

#517 therefore leaves end-to-end cost effectiveness unproven. Issue #597 asks for a decision-quality benchmark, and it is the `tool-exposure-benchmark` work item of the `enterprise-mcp` epic (mctlhq/.github#35). The benchmark covers representative tasks that must actually invoke MCP tools, repeated at least 5 times per (task x mode). It compares four modes on context, cost, success, latency, permission preservation and audit completeness:

1. eager/explicit exposure;
2. mctl-native discovery;
3. Cloudflare `minimize_tools`;
4. Cloudflare `search_and_execute` (Code Mode).

It ends in exactly one recommendation: `ADOPT_MCTL_NATIVE`, `ADOPT_PORTAL_MODE`, `HYBRID` or `DEFER`.

The 2026-11-18 research extension adds three things:

- an availability/capability matrix that separates the different "code mode" mechanisms: Cloudflare Portal `search_and_execute`, Claude Code interactive Code Mode, and Anthropic API Programmatic Tool Calling;
- a non-comparable adjunct slot for the companion experiment, mctlhq/mctl-agents#1096;
- a per-operation correlation and enforcement gate.

The research must neither reopen nor mutate the Cloudflare portal, which mctlhq/.github#63 PARKed on an M8 audit-correlation failure. It must not run live probes without a separately approved experiment plan.

This proposal delivers the parts an implementer can build safely and offline:

- versioned task oracles;
- run-record capture and aggregation tooling in `tools/capability_bench.py`;
- a pre-registered decision rule;
- the bounded experiment plan and matrices, written into the existing benchmark document.

Every unmeasured cell says `NOT_RUN`. The measured runs and the posted decision are operator steps, gated on approval of that plan.

## User stories

- AS an Enterprise MCP decision owner I WANT end-to-end cost, success, permission and audit results per exposure mode, on tasks that really call MCP tools, SO THAT the exposure decision does not rest on first-turn prompt size alone.
- AS a platform operator I WANT a pinned, bounded, pre-approved experiment plan with a USD cap SO THAT the measured runs are reproducible and cannot mutate production portal or runtime configuration.
- AS a security/governance owner (mctlhq/.github#181, #151) I WANT permission preservation and per-operation audit correlation verified from recorded traces, not assumed, SO THAT no mode is adopted that weakens mctl policy checkpoints or identity.
- AS a reviewer of the companion Code Mode research (#1096) I WANT the different "code mode" mechanisms kept apart in an availability matrix SO THAT an interactive-CLI-only feature is never counted as an in-cluster benchmark arm.

## Acceptance criteria (EARS)

**Task oracles**

- WHEN the benchmark task set is defined THE SYSTEM SHALL contain at least three read-only task classes that must invoke MCP capabilities. Each class is stored as a versioned oracle fixture (`tools/bench_tasks/*.yaml`) with these fields: `prompt`, `expected_capabilities`, `argument_constraints`, `answer_facts`, `consequential` and `pinned_inputs`.
- IF a task oracle fixture has unknown keys, an empty `expected_capabilities`, or a prompt that names a non-read-only capability outside a negative probe THEN THE SYSTEM SHALL reject it at load time.

**Run records**

- WHEN a benchmark run record is loaded THE SYSTEM SHALL validate that it carries these fields:
  - `run_id`, `mode`, `task_id`, `task_set_version`;
  - `model`, `profile_version`, `catalog_digest`;
  - `result_messages`, `tool_calls`, `invocation_traces`;
  - `first_turn_cache_creation_tokens`, `wall_clock_ms`;
  - `final_answer_digest`, `oracle_facts_found`.
- IF a run record contains a payload-bearing key (`arguments`, `result`, `answer_text`, `message_text`) THEN THE SYSTEM SHALL reject the record. Only hashes, ids, counts and durations are persisted, so no private message body enters benchmark telemetry.

**Per-cell metrics**

- WHEN records for one (task, mode) cell are aggregated THE SYSTEM SHALL report:
  - n;
  - initial (first-turn) context tokens separately from total input, output, cache-read and cache-creation tokens;
  - turns;
  - discovery, describe, invoke and retry call counts;
  - the oracle success rate;
  - `permission_preserved`;
  - `audit_complete`;
  - provider caveats.
- WHILE a cell has fewer than 5 records THE SYSTEM SHALL report n and p50 latency, omit p95, and mark the cell `below-minimum-n`.
- IF a cell has no records THEN THE SYSTEM SHALL render `NOT_RUN`. IF a mode is declared not measurable THEN THE SYSTEM SHALL render `not measurable: <reason>`. Neither case SHALL ever render as zero.

**Permission and audit checks**

- IF any recorded tool call or invocation trace names a capability outside the task's `expected_capabilities` united with the run's eligible set, or a negative probe's excluded capability becomes visible or invokable, THEN THE SYSTEM SHALL set `permission_preserved=false` for that cell.
- IF any invoked capability lacks a matching audit record THEN THE SYSTEM SHALL set `audit_complete=false`. The matching record is:
  - in eager mode, a `POLICY_DECISION` line from `orchestrator/policy_checkpoint.py` `emit()`;
  - in discovery mode, a `CAPABILITY_INVOCATION` line from `orchestrator/capability_gateway.py` `_emit_trace`.

  The matching record SHALL carry a non-`absent` policy result and the run's execution context id.

**Compatibility and comparison**

- WHEN `tools/capability_bench.py compare` is invoked with two transcripts THE SYSTEM SHALL produce the same output as today (backward compatible).
- WHEN the aggregate report is rendered THE SYSTEM SHALL show the structural first-turn delta against the recorded 61,213 / 23,392 baseline next to the measured end-to-end delta, and state explicitly whether the first-turn delta translated into end-to-end savings.

**Benchmark document**

- WHEN the benchmark document is updated THE SYSTEM SHALL update `docs/benchmarks/capability-discovery.md` in place. The 2026-09-26 run is kept as "Baseline (n=1)", and no competing benchmark artifact is created.
- WHEN the document is updated THE SYSTEM SHALL include a mode availability matrix. Rows: eager, mctl-native discovery, Portal `minimize_tools`, Portal `search_and_execute`, Claude Code interactive Code Mode, Agent SDK / `claude -p` headless, and Anthropic API Programmatic Tool Calling. Columns: environment, tool surface, identity/policy check, sandbox, audit, rollback, limitations and evidence. Unverified facts are marked `UNKNOWN`.
- WHILE mctlhq/.github#63 remains PARK on its M8 failure THE SYSTEM SHALL treat Portal `search_and_execute` as hard-gated: not measurable unless per-operation trace correlation is demonstrated in an isolated test portal. The #63 bytes-on-wire proxy SHALL NOT be described as model-token savings.
- WHEN the document is updated THE SYSTEM SHALL contain a separate "Adjunct (non-comparable)" section for the #1096 interactive Claude Code experiment. That section uses its own vocabulary (`CLI_ONLY_PILOT` / `FURTHER_RESEARCH` / `DEFER` / `REJECT`), and its results SHALL NOT enter the four-arm comparison tables.

**Decision**

- WHEN the document is updated THE SYSTEM SHALL contain a pre-registered decision rule and a Decision section reading `PENDING: requires measured cells` until the operator records exactly one of `ADOPT_MCTL_NATIVE` / `ADOPT_PORTAL_MODE` / `HYBRID` / `DEFER`. The recorded decision states rollout guardrails and the follow-up issue(s).

**Safety boundaries**

- WHILE this spike is in progress THE SYSTEM SHALL leave these unchanged:
  - `ISSUE_INVESTIGATOR_CAPABILITY_MODE`, which defaults to `eager`;
  - the profile catalog;
  - `orchestrator/` runtime code;
  - the Cloudflare portal configuration (`code_mode: off`);
  - every deployed service.
- IF an experiment plan has not been approved by an operator THEN THE SYSTEM SHALL NOT execute measured model runs or live probes, and every results cell SHALL read `NOT_RUN`.

## Out of scope

- Production enablement of Cloudflare Code Mode, `minimize_tools`, Claude Code Code Mode, or mctl-native discovery as a default.
- Registering `tg.mctl.ai` (or any non-mctl-api upstream) as a gateway provider in `orchestrator/resolver.py` `_CAPABILITY_ENDPOINTS`.
- Changing MCP server business logic, policy checkpoints or identity.
- Emulating an unmeasurable mode with a different mechanism, for example a local JS executor.
- Implementing the #1096 interactive experiment itself.
- Executing the measured runs or posting the decision. These are operator steps (tasks 6-7) after plan approval, not implementer work.
- Claiming cost savings from first-turn prompt reduction alone.

## Open questions

- Is the Cloudflare MCP Portal (`mcp.mctl.ai`) able to expose `minimize_tools` and `search_and_execute` on an isolated test portal without touching the production portal? Its configuration is not in `platform-gitops/services/`, so this run could not observe it. Until evidence exists, both Portal arms default to `not measurable` with the reason recorded.
- TC3, the Telegram / cross-upstream class, cannot run under mctl-native discovery today, because the gateway only knows `mctl-api-mcp` (`orchestrator/resolver.py:135`). Two options:
  - accept `not measurable` for that cell;
  - define a third mctl-api-only class so that both required arms have three comparable classes.

  This proposal does both: TC1 to TC3 for the comparison, plus TC4 as a cross-upstream cell that may be `not measurable` under discovery.
- Which read-only Telegram pilot fixture, identity and tenant are approved for TC4? The issue says "read-only pilot data" without naming it. The experiment plan leaves it as an operator-filled pin.
- Which model and USD cap should the plan use? The 2026-09-26 run used `claude-opus-5` at $8 per full investigation. Short task prompts should cost far less, but the cap is an operator decision.
- Does mctl-api record server-side audit entries for read-only MCP calls in eager mode? If it does not, `audit_complete` relies on the client-side `POLICY_DECISION` lines and, when `MCTL_DECISION_RECORDS=on`, on the decision-attempt records. The plan should state which source counts.
- The `enterprise-mcp` epic currently has lifecycle `paused`. Whether the operator runs the experiment while the epic is paused is a priority call (the issue says P2 / BACKLOG). It does not block the offline tooling.
