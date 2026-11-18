# Benchmark context-efficient MCP tool exposure on real mcp.mctl.ai workloads (decision spike)

## Review disposition and boundaries (2026-11-18)

**CHANGES REQUESTED / RESEARCH INTAKE ONLY.** The revised GitOps
`requirements.md`, `design.md` and `tasks.md` comprise the authorized
research-only proposal. A normal Temporal approval is **not** authorization
to proceed with research: it accepts the proposal and starts Tier 2.
Therefore do not signal `approve` or run the implementer. The tools/fixtures,
test additions, benchmark document PR and any measured execution are all
**candidate future slices** that require separately explicit owner GO.
This amendment of the *proposal text* does not authorize code/PR work in
`mctl-agents`, Portal mutation or data access.

Review corrections:
- P1 scope: no implementation, documentation PR, or benchmark run under the
  current research-only gate.
- P1 fallback: **no automatic eager fallback** from discovery errors.
  Authentication, policy, missing/unknown identity, catalog mismatch,
  timeout, deny, require-approval and any unknown reason must fail closed.
  A separately approved, typed non-security recovery may not enlarge the
  sealed capability set, bypass audit or change actor/tenant.
- P2 comparability: TC1, TC2 and TC3 use distinct mctl-api tool families in
  both required arms; TC4 cross-upstream is separate and potentially
  `not measurable` in discovery.
- P2 trace join: require stable run/parent/child-call and policy-decision
  identifiers plus actor, tenant, outcome and durable receipt, not only
  `arguments_hash`. Evidence missing => `INCOMPLETE`, never PASS.
- P2 authorization: the eligible set is independently resolved from
  profile, tenant and policy; an oracle's `expected_capabilities` proves
  **task correctness only**, never permission.
- P2 adoption: no observed security/correctness regression is permissible.
  Five runs per cell are exploratory, and not a statistically powered
  adoption decision; insufficient confirmatory evidence => `DEFER`.
- Follow-up P1 telemetry minimization: persist allowlisted numeric SDK
  usage projections, NEVER raw `ResultMessage` objects. Reject unknown and
  payload-bearing fields recursively, including inside nested arrays.
- Follow-up P2 NEG mode semantics: eager can advertise a disallowed tool
  but must deny it at the action-time checkpoint; discovery additionally
  must not expose it through its filtered catalogue.
- Follow-up P2 oracle alternatives: `required_all` plus
  `required_any_of` groups replace ambiguous `expected_capabilities`
  conjunctions. Alternatives satisfy a group, never grant authorization.


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

This research-only proposal specifies a candidate future set of versioned
task oracles, run-record schema, offline aggregation tool, a bounded
experiment plan and matrices for the canonical benchmark document.
**None of the target-repository changes is currently authorized.**
Every unmeasured cell must read `NOT_RUN`. Real repetitions and the
posted decision are later operator steps with a separate scoped GO.

## User stories

- AS an Enterprise MCP decision owner I WANT end-to-end cost, success, permission and audit results per exposure mode, on tasks that really call MCP tools, SO THAT the exposure decision does not rest on first-turn prompt size alone.
- AS a platform operator I WANT a pinned, bounded, pre-approved experiment plan with a USD cap SO THAT the measured runs are reproducible and cannot mutate production portal or runtime configuration.
- AS a security/governance owner (mctlhq/.github#181, #151) I WANT permission preservation and per-operation audit correlation verified from recorded traces, not assumed, SO THAT no mode is adopted that weakens mctl policy checkpoints or identity.
- AS a reviewer of the companion Code Mode research (#1096) I WANT the different "code mode" mechanisms kept apart in an availability matrix SO THAT an interactive-CLI-only feature is never counted as an in-cluster benchmark arm.

## Acceptance criteria (EARS)

**Task oracles**

- WHEN the benchmark task set is defined THE SYSTEM SHALL contain at least three read-only positive task classes which invoke MCP capabilities. Versioned oracle fixtures (`tools/bench_tasks/*.yaml`) carry `prompt`, `required_all`, `required_any_of`, `excluded_capabilities`, `argument_constraints`, `answer_facts`, `consequential`, and `pinned_inputs`.
- `required_all` is a list of tools every successful positive run must call; `required_any_of` is a list of non-empty alternative groups, where **at least one** tool in **each** group must be called. The positive task SHALL specify at least one mandatory requirement in the union of `required_all` and `required_any_of`. Each chosen invocation must meet its pinned `argument_constraints` and every `answer_facts` predicate must hold.
- A negative probe may have both required lists empty ONLY when `consequential=true` and `excluded_capabilities` is non-empty. It succeeds only when the excluded tool is not executed and the mode-specific deny/exposure requirements hold; a denied attempt is **not** a successful invocation.
- IF a fixture contains an unknown field, a malformed/empty alternative group, no positive call obligation, no excluded negative capability, an unsatisfiable oracle, or a non-read-only *positive* instruction THEN THE SYSTEM SHALL reject it. Task oracle fields do not set the authorization-eligible capability set.

**Run records**

- WHEN a benchmark run record is loaded THE SYSTEM SHALL validate that it carries these fields:
  - `run_id`, `mode`, `task_id`, `task_set_version`;
  - `model`, `profile_version`, `catalog_digest`;
  - `usage_summaries`, `tool_calls`, `invocation_traces`;
  - `first_turn_cache_creation_tokens`, `wall_clock_ms`;
  - `final_answer_digest`, `oracle_facts_found`.
- `usage_summaries[]` SHALL contain only an explicit numeric usage projection: `session_id` (opaque), `num_turns`, `duration_api_ms` and `model_usage[]` entries with `model_id`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens`. A projection may contain cumulative per-model counters, with a documented delta calculation; the first-turn counter is obtained through a separate sanitized numeric observation. **No SDK `ResultMessage`, `AssistantMessage`, messages, model output, tool result, nested raw SDK object, or raw transcript shall be persisted.**
- BEFORE ANY durable write THE SYSTEM SHALL project allowlisted counters and identifiers from in-memory SDK objects, then validate the complete record **recursively** with strict allowed keys, scalar types, and bounded identifier formats. Unknown or payload-bearing keys anywhere (including `result`, `arguments`, `answer_text`, `message_text`, `content`, `text` inside an array, map, or `usage_summaries`) SHALL fail closed without writing. Data in `tool_calls` and `invocation_traces` is likewise schema allowlisted and payload-free. Negative tests SHALL prove nested SDK response text is never persisted.
- The existing `compare` CLI accepts legacy transcripts **at read time only**; it MUST stay backward compatible. Any future `aggregate`/record path consumes the sanitized projection only and shall never serialize its legacy raw input.

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

- WHEN measuring `permission_preserved`, THE SYSTEM SHALL use the independently resolved eligible set for the pinned identity/tenant/profile/catalog, not task oracle fields. A tool that executes without an action-time ALLOW in that eligible set, or an excluded negative capability that executes, SHALL yield `permission_preserved=false`. A disallowed **attempt** that the checkpoint denies is not an execution and can pass the authorization test when audited.
- Eager mode advertises the full MCP schema by design; broad **visibility alone** SHALL NOT be scored as an invocation-policy violation. Report its exposed-schema count separately as `exposure_count`/`exposure_outside_eligible_count`. Its NEG oracle requires an explicit action-time **DENY**, no side effect and complete audit of the denied attempt.
- Discovery/filtered modes additionally SHALL enforce `exposure_filtered=true`: excluded tools must not appear in the search/describe/resolved eligible capability set, and no excluded call can execute. Exposure-policy failure is distinct from invocation authorization failure.
- `required_all`/`required_any_of` SHALL score task correctness only and SHALL NEVER grant authority. Missing or unverifiable eligible-set evidence yields `UNVERIFIABLE`, never a PASS; missing policy decisions or failed deny evidence fail closed.
- IF an invocation or denial lacks a unique and exact action-time audit join
THEN THE SYSTEM SHALL set `audit_complete=false`. The required chain is
`run_id -> parent_execution_id / parent_script_id -> child_call_id ->
policy_decision_id -> invocation/outcome -> durable_trace_id`, with
sealed actor/tenant, canonical argument digest, policy outcome and final
outcome on each child. Eager `POLICY_DECISION` and discovery
`CAPABILITY_INVOCATION` log lines are **candidate evidence sources**, not
proof that the full chain already exists. Repeated identical hashes must
still yield distinct child IDs. Missing, ambiguous or multiplied joins are
`INCOMPLETE` even when tokens and correctness look good.

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

**Research-only addendum:** running or changing the offline benchmark harness,
writing fixture/test/benchmark documentation PRs, accepting the GitOps
proposal, enabling the implementer, or auto-falling-back across an
authorization boundary require separate authorization. Only drafting/reviewing
the proposal text is within current scope.


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
