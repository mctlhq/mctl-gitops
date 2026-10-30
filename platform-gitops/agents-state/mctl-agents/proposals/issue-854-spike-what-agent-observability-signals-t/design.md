# Design: issue-854-spike-what-agent-observability-signals-t

## Current state

What DevLoop emits today, read from the clone:

- **Trace facade.** `orchestrator/tracing.py` (stdlib-only, inert unless `OTEL_EXPORTER_OTLP_*` is set),
  `orchestrator/tracing_sdk.py` (SDK pipeline plus `GuardedExporter`/`redact_attributes`, a key
  allowlist, denylist and credential-shape value check), `orchestrator/temporal/tracing.py` (worker
  interceptors). Design and attribute table: `docs/observability/execution-traces.md`.
- **Model and tool spans already exist.** `tracing.AgentRunObserver` turns the Claude Agent SDK
  message stream into `invoke_agent <agent>` -> `chat <model>` (one per model message, latency =
  model time) and `execute_tool <name>` (status `ok|error|incomplete`, `mcp.method.name` for
  `mcp__*`), with sub-agent turns nested under their Task tool. Token usage (input, output, cache
  read/creation) is set per `chat` and summed on `invoke_agent` (`_usage_counts`, `_result`).
- **Other trace content.** `command_span`/`classify_command` (gh/git spans with
  `mctl.github.operation`/`mctl.github.mutation`), `record_artifact` (`mctl.artifact.write` events),
  `record_policy_decision` (`mctl.policy.decision` events from `orchestrator/policy_checkpoint.py`),
  log correlation (`install_log_correlation`, the pod anchor line), and the deterministic
  virtual root `workflow_trace_ids(workflow_id, run_id)` that `dev_loop.py` (~line 5024) uses to report
  the trace id.
- **Which runners are traced.** Grepping `orchestrator/run_*.py` for `tracing.` / `agent_run`:
  only `run_issue_investigator.py`, `run_implementer.py` and `run_shepherd.py`
  (`tracing.agent_run("shepherd", SHEPHERD_MODEL)`, line ~2847) wrap an agent run. `run_incident_responder.py`,
  `run_scout.py`, `run_mentor.py`, `run_service_agent.py`, `run_security_verifier.py`,
  `run_authoring_canary.py` and `run_context_eval.py` have no tracing calls.
- **Metrics.** The only OpenTelemetry metrics are commerce ones (`orchestrator/commerce_metrics.py`,
  `metrics.get_meter("mctl.commerce")`: `mctl.commerce.invocations`, `.invocation.duration`,
  `.outcome_unknown`). There is no agent-run, token or tool-error metric.
- **Run outcome is in the ledger, not the span.** `orchestrator/usage_ledger.py` `UsageRecorder`
  (~lines 621-647) records `num_turns`, `stop_reason` and `terminal_reason` from `ResultMessage`. The
  `invoke_agent` span records only usage counters and `error.type`
  (`AgentRunObserver._result`).
- **Evals.** `orchestrator/context_eval.py` (ADR 015) scores retrieval quality of a sealed
  `ContextSnapshot`. It is off by default (`ISSUE_INVESTIGATOR_CONTEXT_EVAL`,
  `run_issue_investigator.py` ~2823), produces records rather than spans, and is explicitly
  independent of final-output scoring, mctl-agents#60, which has no producer in this repo. Context
  strategy fields are log-line only (`CONTEXT_STRATEGY_RELEASE`/`_COMPARE` in
  `orchestrator/context_assembly.py`; the execution-traces doc says wiring them into spans is
  outstanding). Lifecycle outcomes (proposal accepted/rejected, review-fix rounds, merged, reverted)
  live in `.status.yaml` and the DevLoop workflow state. None of them is attached to the trace.
- **Budget signals.** `orchestrator/exec_budget.py` has no tracing calls. Budget denials appear on
  the trace only when they go through the policy checkpoint as a `mctl.policy.decision` event.
  Provider 429s and retries are not span attributes (the spike 791 records track `http_429` and
  `retries` offline, `docs/spikes/791/...records-candidate.jsonl`).
- **Spike convention.** Reports live at `docs/spikes/<n>-<slug>.md` with a `STATUS: <TOKEN>` line
  and an allowed-token list (e.g. `docs/spikes/796-rea-investigation-evidence.md`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-exec/values.yaml`: image tag `1.107.0`,
  `otel.enabled: true` (comment: spans go to the permanent Tempo in `tracing` through the
  Collector), `MCTL_TRACE_WORKFLOW_TYPES: DevLoopWorkflow`, `MCTL_TRACE_ARGO_PARAM: "true"`.
- `.../mctl-agents-worker-implement/values.yaml` and `.../mctl-agents-worker/values.yaml`: the
  same `MCTL_TRACE_WORKFLOW_TYPES`/`MCTL_TRACE_ARGO_PARAM`, and an `otel:` block.
- I did not read the CWFT pod env (`MCTL_TRACE_REQUIRE_PARENT`, `TRACEPARENT` mapping), the Collector
  redaction fix (mctl-gitops#1332) or live Tempo contents. No mctl MCP call was made. Whether pod
  spans and integer token counters arrive in Tempo is **not observed** (see Open questions).

## Proposed solution

A doc-first spike with one guard test. No runtime change.

1. **`docs/spikes/854-agent-observability-gaps.md`** with `STATUS:` (allowed tokens
   `ADOPT_FOLLOW_UPS`, `ADOPT_SUBSET`, `RESEARCH_ONLY`, `REJECT`; recommended token `ADOPT_SUBSET`,
   unless the live check in task 2 changes the picture). Sections:
   - *Baseline*: what #195 already emits, which links to `execution-traces.md` rather than repeating it.
   - *Gap matrix*: one row per signal, with columns signal / class (a-h from requirements) /
     state (`emitted`, `emitted-elsewhere`, `missing`) / producer file+symbol / proposed name /
     upstream semconv name or "none" / priority. Expected rows, from the current-state reading:
     - G1 P1 **Evaluation results on the trace**: a `mctl.eval.result` span event (proposed;
       aligned to upstream `gen_ai.evaluation.*` if it exists at the pinned semconv version) with
       `mctl.eval.name` (closed vocabulary: `context.retrieval`, `proposal.decision`,
       `pr.review_rounds`, `pr.outcome`, `ci.result`), `mctl.eval.score` (number) and/or
       `mctl.eval.label` (closed vocabulary). Producers: `context_eval.evaluate` caller in
       `run_issue_investigator.py`; DevLoop approval and shepherd/merge activities for lifecycle
       outcomes. Late outcomes (merge, revert) are emitted as a span in a new trace linked by
       `mctl.workflow.id`, because the original run's trace may already have closed.
     - G2 P1 **Run outcome attributes on `invoke_agent`**: `mctl.agent.stop_reason`,
       `mctl.agent.terminal_reason` (bounded closed strings) and `mctl.agent.turns` (int). These
       copy what `UsageRecorder` already reads, set in `AgentRunObserver._result`. Upstream
       `gen_ai.response.finish_reasons` is noted where it applies.
     - G3 P1 **Agent RED metrics**: a `mctl.agents` meter beside `commerce_metrics.py`:
       `mctl.agent.invocations` (counter: agent, outcome, model), `mctl.agent.invocation.duration`
       (histogram), `mctl.agent.tool.calls` (counter: agent, tool-name bucketed to a closed list,
       status), `mctl.agent.tokens` (counter: agent, model, token type). It uses the same closed-attribute and
       no-ids/no-amounts rule as commerce metrics. The rationale is that traces are scoped to DevLoop and
       sampled, while alerts and dashboards need aggregates.
     - G4 P2 **Budget and provider-pressure signals**: exec-budget threshold/denial events,
       `http_429`/retry counts on `chat` spans.
     - G5 P2 **Coverage outside DevLoop**: wrap `tracing.agent_run` in incident-responder, scout,
       mentor, service-agent and security-verifier, and widen `MCTL_TRACE_WORKFLOW_TYPES` per type
       in gitops.
     - G6 P2 **Context strategy fields on spans**: move the `mctl.context.*` log-only fields onto the pod
       root span (an outstanding item already named in `execution-traces.md`).
     - G7 P3 **Loop timeline**: approval-wait and human-input-wait durations as events
       on the DevLoop's activities. This must stay replay-safe: activity-side only, as `traceparent` already is.
   - *Redaction check*: for every proposed name, confirm it passes `tracing_sdk.key_allowed`
     (no denylisted suffix such as `_result`/`_input`). Note any name that would need an allowlist
     change. For example, `mctl.eval.result` ends in `result`, which the guard drops, so the event
     *name* is fine but no attribute may use that suffix.
   - *Follow-up issues*: one block per gap with title, repo (mctl-agents, mctl-docs for catalog
     reservations, mctl-gitops for scope/dashboards), priority, dependencies and scope, ready to file.
   - *Coverage registry*: a fenced block listing every `orchestrator/run_*.py` module with
     `runner`, `agent_call` (yes/no) and `traced` (yes/no), consumed by the test below. Listing only
     the traced modules is not enough: a new untraced runner would then be absent from both sides
     and the guard would stay green.
2. **Live confirmation (read-only, best-effort).** The implementer reads the CWFT env and, if
   reachable, one recent DevLoop trace. The report records what was observed, or states "not
   observed". A gap is never inferred from an unread source.
3. **`tests/test_tracing_coverage.py`.** It globs `orchestrator/run_*.py` and parses the registry
   block from the report. It asserts that (i) the set of registry rows equals the set of runner
   modules on disk, so an unregistered runner fails CI; (ii) each row's `traced` value matches an
   `ast` check for a `tracing.agent_run` call in that module; (iii) each row with `agent_call: yes`
   and `traced: no` is referenced by a gap ID in the matrix. `agent_call` is reviewed by hand, and
   the test records the symbols it treats as an agent invocation so the implementer can tighten it
   later. Stdlib only, no network.

## Alternatives
- **Implement the P1 signals directly in this issue.** Dropped: the issue is a spike, and the eval
  vocabulary and metric names need a mctl-docs catalog reservation first (the convention in
  `execution-traces.md`). Shipping names before reservation would contradict that rule.
- **Separate eval store or ledger instead of trace events.** Kept as an open question, not the default.
  The usage ledger (ADR 012) is the precedent for durable records, but evaluation's debugging value
  comes from correlating with the spans of the same run. Trace events plus a link to the
  durable record give both.
- **Adopt a third-party agent-observability SDK (e.g. OpenLLMetry or vendor auto-instrumentation).**
  Dropped: it would emit prompt and completion content by default and bypass the stdlib-only, inert-by-default
  facade and the export guard that #195 was built around.

## Platform impact
- No runtime change, no migration, no backward-compatibility concern. One new doc and one new test.
- Risk: the report drifts from the code. Mitigation: the coverage test, plus every row cites a file and symbol.
- Risk: proposed names collide with the mctl-docs catalog or the upstream semconv. Mitigation: every
  name is marked **proposed**, and the follow-up list puts the catalog reservation first.
- Risk: evaluation signals could later be read as authorization inputs. Mitigation: the report restates
  ADR 015's non-authorization rule for all eval signals.

## Open questions
- mctl-agents#830 was not readable here. Overlapping follow-ups must be merged into it.
- Live export of pod spans and Collector token-counter handling (mctl-gitops#1332) were not observed
  from this run. Task 2 confirms them.
- Placement of late lifecycle outcomes (linked span vs separate store) and metric scoping (all
  workflow types vs DevLoop only). Defaults are as stated above.
