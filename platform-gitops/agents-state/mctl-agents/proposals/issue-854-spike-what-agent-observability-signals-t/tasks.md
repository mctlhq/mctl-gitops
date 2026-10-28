# Tasks: issue-854-spike-what-agent-observability-signals-t

- [ ] 1. Re-verify the baseline inventory against the code: `orchestrator/tracing.py` (`AgentRunObserver`, `command_span`, `record_artifact`, `record_policy_decision`), `orchestrator/commerce_metrics.py`, `orchestrator/usage_ledger.py` (`UsageRecorder` turn/stop fields), `orchestrator/context_eval.py`, `orchestrator/exec_budget.py`, and every `orchestrator/run_*.py` for `tracing.agent_run`. DoD: a scratch list of emitted / emitted-elsewhere / missing signals, each with file and symbol.
- [ ] 2. (depends on 1) Read-only deployed check: worker values (`services/admins/mctl-agents-worker*/values.yaml`), the investigate/implement CWFT env, and, if reachable, one organic DevLoop trace in Tempo. DoD: each fact recorded with its source, or explicitly "not observed".
- [ ] 3. (depends on 1, 2) Write `docs/spikes/854-agent-observability-gaps.md`: `STATUS:` line with an allowed token, baseline, gap matrix G1-G7 covering classes (a)-(h), redaction check of every proposed name against `tracing_sdk.key_allowed`, and a link to mctl-agents#830 and #60. DoD: every row has state, producer, proposed name marked **proposed**, upstream semconv name or "none", and priority.
- [ ] 4. (depends on 3) Add the follow-up issue section: one ready-to-file block per gap (title, repo, priority, dependencies, scope), with mctl-docs catalog reservation listed before any emitting change. DoD: at least the P1 gaps (eval events, run-outcome attributes, agent metrics) have complete blocks.
- [ ] 5. (depends on 3) Add the coverage block to the report, and add `tests/test_tracing_coverage.py`, which uses `ast` to find `run_*.py` modules calling `tracing.agent_run` and asserts the set equals the block. DoD: the test passes locally and fails if a module is added to or removed from either side.
- [ ] 6. (depends on 3-5) Link the report from `docs/observability/execution-traces.md` (one line under "Follow-ups outside this repo" or a new "Known gaps" pointer). DoD: the link resolves, and no other content of that doc is changed.

## Tests
- [ ] T1. `tests/test_tracing_coverage.py` passes with the current tree (expected traced set: `run_issue_investigator`, `run_implementer`, `run_shepherd`).
- [ ] T2. Negative check of T1: temporarily removing a module name from the report's coverage block makes the test fail with a message naming the module.
- [ ] T3. The existing suite stays green (`tests/test_tracing.py`, `tests/test_tracing_agents.py`, `tests/test_tracing_temporal.py`). No runtime code was changed.
- [ ] T4. Manual review: every proposed attribute or event name in the report is checked against `tracing_sdk.key_allowed` in a REPL, and the result is recorded in the report.

## Rollback
Revert the PR. It adds one doc, one test and one link line, and changes no runtime behaviour or deployed configuration, so a revert has no operational effect.
