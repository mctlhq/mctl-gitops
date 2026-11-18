# Spike: benchmark context-efficient MCP tool exposure on real workloads that invoke tools

## Context

Issue mctlhq/mctl-agents#597 asks for a benchmark good enough to base a decision on. It compares the ways an mctl agent can be shown MCP tools: the current eager exposure, the mctl-native `CapabilityGateway` (#242, ADR 017), and, where they can be tested safely, the Cloudflare Portal context optimisation (`minimize_tools`) and `search_and_execute` / Code Mode. The only evidence today is `docs/benchmarks/capability-discovery.md`. It covers one run per mode, on one issue, and neither run invoked an mctl tool. It shows a structural first-turn reduction (61,213 to 23,392 tokens, -62%), but end to end the discovery run cost more ($6.10 against $5.24, 52 turns against 30). #517 therefore leaves end-to-end benefit unproven.

The 2026-11-18 research extension adds three things. The first is a capability/availability matrix that separates Claude Code interactive Code Mode, Anthropic Programmatic Tool Calling, the Cloudflare Portal and the mctl-native gateway. The second is an optional adjunct experiment that is not comparable with the four arms. The third is a hard audit-correlation gate: the parked Portal result (mctlhq/.github#63, M8 FAIL) stays a hard stop. The spike must not change production exposure. Measured runs happen only under a separately approved, bounded experiment plan, and any cell that was not run says `NOT_RUN`. The spike ends with exactly one recommendation for Enterprise MCP: `ADOPT_MCTL_NATIVE`, `ADOPT_PORTAL_MODE`, `HYBRID` or `DEFER`.

## User stories

- AS the Enterprise MCP roadmap owner I WANT a repeated, oracle-scored comparison of the exposure modes on tasks that actually call MCP tools SO THAT the choice of exposure path rests on end-to-end cost and success, not on first-turn prompt size.
- AS a platform operator I WANT the benchmark harness to run offline from captured transcripts, with a bounded experiment plan I approve before any live run SO THAT the spike cannot spend money or touch production without my sign-off.
- AS a security/governance owner I WANT permission preservation and audit/trace completeness checked for every invoked consequential capability SO THAT a cheaper mode cannot win while weakening policy or auditability.
- AS a reviewer I WANT modes that cannot be measured recorded as `not measurable`, with the concrete limitation, SO THAT no mode is stood in for by a different mechanism.

## Acceptance criteria (EARS)

- WHEN the spike is delivered THE SYSTEM SHALL update `docs/benchmarks/capability-discovery.md` in place. It SHALL NOT add a competing benchmark artifact, and it SHALL keep the 2026-09-26 n=1 section as the recorded baseline.
- WHEN the benchmark task set is defined THE SYSTEM SHALL list at least three task classes. In each, the agent must invoke at least one MCP capability, and each class SHALL have a machine-checkable success oracle: the expected capability ids, the required argument constraints and the expected answer facts.
- WHEN `tools/capability_bench.py` aggregates runs THE SYSTEM SHALL accept N transcripts per `(task, mode)` cell and report n per cell. It SHALL report the following for each cell:
  - initial tool-schema/context tokens, kept separate from total input, output, cache-read and cache-creation tokens;
  - model turns;
  - discovery, describe and invoke call counts;
  - retries;
  - wall-clock and `duration_api_ms` (each with its semantics documented);
  - p50/p95 latency when n >= 5;
  - oracle success rate.
- WHEN a cell has fewer than 5 repetitions THE SYSTEM SHALL print the actual n and the documented constraint that justifies it, and it SHALL omit p95 for that cell.
- WHEN a mode cannot be enabled in an isolated, reversible way THE SYSTEM SHALL record every cell of that mode as `not measurable`, with the product or provider limitation and evidence. It SHALL NOT emulate that mode with another mechanism.
- WHEN a cell was designed but not executed THE SYSTEM SHALL render it as `NOT_RUN`, never as zero or blank.
- WHEN a run invokes a capability outside the task's eligible set, or a capability excluded from the sealed `CapabilitySet` becomes visible or callable, THE SYSTEM SHALL mark the run `permission_preserved=false` and report it in the permission-preservation row.
- WHEN a consequential capability is invoked THE SYSTEM SHALL check that a policy checkpoint result, the actor/tenant correlation and a durable trace record exist for that exact invocation. A missing link marks the run's audit completeness `incomplete`.
- WHILE capturing benchmark telemetry THE SYSTEM SHALL store only hashes, counts and capability ids. It SHALL NOT store tool arguments, tool results or private message bodies, matching the `InvocationRecord` hash-only rule in `orchestrator/capability.py`.
- WHILE the spike is in progress THE SYSTEM SHALL leave the following unchanged:
  - the production default `ISSUE_INVESTIGATOR_CAPABILITY_MODE=eager`;
  - the Portal `code_mode: off` configuration;
  - every MCP server's business logic.
- IF the Cloudflare `search_and_execute` arm cannot show that one execute call maps to N upstream calls with a per-call actor, policy result and trace link (the #63 M8 criterion) THEN THE SYSTEM SHALL record the arm as failing the governance gate, and it SHALL NOT recommend `ADOPT_PORTAL_MODE` for it.
- WHEN the report is finalised THE SYSTEM SHALL state the structural first-turn delta against the existing -62% baseline, and SHALL say explicitly whether that delta translated into end-to-end savings.
- WHEN the report is finalised THE SYSTEM SHALL end with exactly one of `ADOPT_MCTL_NATIVE`, `ADOPT_PORTAL_MODE`, `HYBRID` or `DEFER`, together with the production rollout guardrails and the exact follow-up issue(s). The recommendation SHALL be posted on #597 and linked from mctlhq/.github#35.
- WHEN the research-extension matrix is produced THE SYSTEM SHALL tabulate interactive Claude Code CLI, Agent SDK / `claude -p` headless, Cloudflare Portal, the mctl-native gateway and Anthropic Programmatic Tool Calling. The columns SHALL be: environment, tool surface, identity/policy check, sandbox, audit, rollback, limitations and evidence. Facts that were not verified SHALL read `UNKNOWN`.
- IF the optional Claude Code Code Mode adjunct is reported THEN THE SYSTEM SHALL report it in a separate, non-comparable section with its own recommendation (`CLI_ONLY_PILOT` / `FURTHER_RESEARCH` / `DEFER` / `REJECT`). It SHALL NOT count as a benchmark arm.

## Out of scope

- Production enablement of Cloudflare Code Mode, `minimize_tools`, or capability discovery as the default mode.
- Any change to Portal configuration, feature flags or MCP server business logic. This includes adding `tg.mctl.ai` as a gateway provider endpoint in `orchestrator/resolver.py`.
- Replacing policy checkpoints or identity with discovery, or treating discovery as authorization.
- Running live benchmark executions as part of the implementer's PR. Live runs are an operator step under an approved plan.
- Implementing Claude Code Code Mode support in the SDK or runtime, and reopening #63.
- Claiming cost savings from first-turn reduction alone.

## Open questions

- **Cross-upstream and Telegram tasks under mctl-native discovery.** `orchestrator/resolver.py:135` `_CAPABILITY_ENDPOINTS` knows only `mctl-api-mcp`. The gateway therefore cannot reach `tg.mctl.ai` today, and adding it is a runtime change. Working assumption: the Telegram and cross-upstream classes are measured where possible: eager runs through a test-only `mcp_servers` entry, and Portal modes through the Portal. Gateway cells for those classes are `not measurable (provider not registered)`. A third task class that is mctl-api-only, with two distinct tool families, keeps the three-class minimum comparable across both required arms.
- **Who runs the measured repetitions, and the budget cap.** At about $5-6 per investigator run, 3 tasks x 2 modes x 5 repetitions costs roughly $150-$180. The proposal assumes an operator-approved plan with an explicit USD cap, and uses lightweight task prompts rather than full issue investigations to cut cost.
- **Testable Cloudflare modes.** Whether the current Portal exposes `minimize_tools` and an isolated `search_and_execute` test portal could not be observed from this run, because `mcp.mctl.ai` is not a gitops-managed service. The experiment plan must establish this, and record `not measurable` if neither can be isolated.
- **Read-only pilot data for Telegram.** Which tenant or identity holds read-only Telegram pilot data is not stated. The experiment plan must name it, or the class is `NOT_RUN`.
- **Scope of the implementer's PR.** The research extension forbids code-writing agents and PRs for the Claude Code companion research. This proposal assumes that forbids runtime and SDK changes only. Offline benchmark tooling in `tools/` and the documentation update are taken to be the deliverables the original #597 asks for. The reviewer should confirm this.
