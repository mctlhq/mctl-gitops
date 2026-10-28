# Spike: agent observability signals DevLoop lacks today (gap report and follow-up plan)

## Context
Issue mctlhq/mctl-agents#854, a scout-generated spike, asks which agent observability signals (traces of
model and tool calls, evals) DevLoop should emit and does not today. Related: mctl-agents#830.
The question is partly answered in code already: mctl-agents#195 shipped one OpenTelemetry trace per
DevLoop run. It goes Temporal activity -> Argo workflow -> agent pod -> `invoke_agent` -> `chat` /
`execute_tool` spans (`orchestrator/tracing.py`, `docs/observability/execution-traces.md`). It is
exported in production through the Collector to Tempo, for `DevLoopWorkflow` only (mctl-gitops
`services/admins/mctl-agents-worker*/values.yaml`). So the spike should not propose "add tracing". It
should produce a code-grounded inventory of what that pipeline does not cover, and a prioritised list
of follow-up issues. The main gaps are evaluation signals, agent metrics, coverage outside the three
DevLoop agents, and run-outcome attributes that the usage ledger already sees but spans do not.

This matters because DevLoop runs chain many model and tool calls that are hard to debug, and better
telemetry also supports the budget (ADR 011/012) and safety (ADR 014) contracts.

## User stories
- AS a platform operator I WANT a single document that lists, per signal class, what DevLoop emits today and what it lacks SO THAT I can decide which telemetry follow-ups to fund.
- AS a DevLoop maintainer debugging a failed run I WANT each gap tied to the exact file and symbol where it would be produced SO THAT a follow-up issue can be implemented without re-doing the investigation.
- AS a reviewer of agent quality I WANT a defined vocabulary for evaluation results (context retrieval quality, proposal and PR outcomes) attached to the run's trace SO THAT quality can be correlated with model, profile and cost.
- AS a maintainer I WANT an offline test that pins which agent entry points are traced SO THAT the report's coverage table cannot silently drift from the code.

## Acceptance criteria (EARS)
- WHEN the spike is complete THE SYSTEM SHALL contain `docs/spikes/854-agent-observability-gaps.md` with a `STATUS:` line carrying exactly one recommendation token from: `ADOPT_FOLLOW_UPS`, `ADOPT_SUBSET`, `RESEARCH_ONLY`, `REJECT`.
- WHEN the report lists a signal THE SYSTEM SHALL classify it as `emitted`, `emitted-elsewhere` (e.g. usage ledger or log line only) or `missing`, and SHALL cite the producing or would-be-producing file and symbol.
- THE SYSTEM SHALL cover at least these signal classes in the report: (a) model-call spans, (b) tool-call spans, (c) run outcome attributes (stop reason, terminal reason, turn count), (d) agent RED metrics, (e) evaluation results (context retrieval quality per ADR 015, final-output and lifecycle outcomes per #60), (f) budget, rate-limit and policy signals, (g) coverage of agent entry points outside DevLoop, (h) loop-level timeline (approval and human-input waits).
- WHEN the report proposes a new attribute, event or metric name THE SYSTEM SHALL mark it **proposed**, state whether an upstream OpenTelemetry GenAI semantic-convention name exists, and state that it needs a mctl-docs catalog reservation (`docs/reference/telemetry-attributes.md`) before it ships.
- WHILE any proposed signal is described THE SYSTEM SHALL keep within the redaction rules in `docs/observability/execution-traces.md` ("Redaction rules"): no prompts, completions, tool arguments or results, issue bodies, argv, or monetary amounts on metrics.
- WHEN the report recommends follow-ups THE SYSTEM SHALL list each one with a title, target repo, priority (P1/P2/P3), dependencies and a one-paragraph scope that is ready to file as an issue.
- THE SYSTEM SHALL add `tests/test_tracing_coverage.py`. It statically lists which `orchestrator/run_*.py` modules call `tracing.agent_run`, and fails if that set differs from the coverage table embedded in the report.
- IF the report states a fact about deployed state (exporter enabled, workflow-type scope, image version) THEN THE SYSTEM SHALL name the gitops path or tool call it was read from.
- THE SYSTEM SHALL NOT change any runtime behaviour, span, attribute or metric emitted by `orchestrator/` in this proposal.

## Out of scope
- Implementing any of the new signals (eval events, agent metrics, extra span attributes, tracing for further runners). Each one is a follow-up issue named in the report.
- Implementing final-output evaluation (#60) itself, or changing the context evaluator (`orchestrator/context_eval.py`, ADR 015).
- Choosing or changing the trace backend, Collector config or Grafana dashboards (mctl-gitops).
- Recording prompts, completions or tool payloads in any form. There is deliberately no opt-in for this.
- Filing the follow-up issues on GitHub. The report contains them ready to file. The owner files them.

## Open questions
- The contents of mctl-agents#830 ("Related") were not readable from this run. The report must link it, and re-scope any follow-up that #830 already covers.
- Whether evaluation results should be span events on the existing run trace (proposed default) or a separate eval store. The trace for a run ends when its Temporal run ends, but PR merge or revert outcomes arrive days later, possibly after `continue_as_new`, which starts a new trace. The proposed default is a late, linked span keyed on `mctl.workflow.id`. Confirm this in review.
- The exact upstream OpenTelemetry GenAI name and stability for evaluation results (`gen_ai.evaluation.*`) must be verified against the semconv version mctl-docs pins. The report records whatever it finds and does not assume it.
- Whether agent metrics should be scoped like traces (`MCTL_TRACE_WORKFLOW_TYPES`) or emitted for every workflow type. Metrics carry no ids, so the proposed default is every type.
