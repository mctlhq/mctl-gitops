# Tasks: issue-597-spike-enterprise-mcp-benchmark-context-e

- [ ] 1. **Write the task-set v1 oracle fixtures.** Add `tools/bench_tasks/tc1-roadmap.yaml`, `tc2-triage.yaml`, `tc3-agent-ops.yaml`, `tc4-cross-upstream.yaml` and `neg-consequential.yaml`, each with the keys `prompt`, `expected_capabilities`, `argument_constraints`, `answer_facts`, `consequential` and `pinned_inputs`. All prompts are read-only. NEG names `mctl_deploy_service` as its excluded capability.
  - DoD: `load_task` / `validate_task` in `tools/capability_bench.py` load all five. They reject unknown keys and an empty `expected_capabilities`.
- [ ] 2. **Add the run-record schema** (depends on 1). Add `load_run_record` / `validate_run_record` with the fields `run_id`, `mode`, `task_id`, `task_set_version`, `model`, `profile_version`, `catalog_digest`, `result_messages`, `tool_calls[{name, capability_id, kind, arguments_hash, is_retry}]`, `invocation_traces`, `first_turn_cache_creation_tokens`, `wall_clock_ms`, `final_answer_digest` and `oracle_facts_found`.
  - DoD: records with `arguments`, `result`, `answer_text` or `message_text` keys are rejected, and so are unknown `kind` values.
- [ ] 3. **Add pure `cell_metrics(records, task)`** (depends on 2).
  - Metrics: n; first-turn tokens separate from totals, the totals reusing `_totals_for_transcript`; turns; search, describe, invoke and direct counts; retries; p50/p95 latency, with p95 only when n >= 5 and `below-minimum-n` otherwise; success rate; `permission_preserved`; `audit_complete`.
  - Audit matching uses `POLICY_DECISION` lines (eager) and `CAPABILITY_INVOCATION` lines (discovery).
  - DoD: the function is pure, with no I/O.
- [ ] 4. **Add the `aggregate` subcommand** (depends on 3): `aggregate RUNS_DIR --tasks DIR [--not-measurable MODE=REASON ...] [--schema-bytes FILE]`.
  - It renders per-task x per-mode tables, using `NOT_RUN` for empty cells and `not measurable: <reason>` for declared modes.
  - It adds a "Structural vs end-to-end" table against the 61,213 / 23,392 baseline, with a translated / not-translated verdict line.
  - Optionally add a `record` subcommand that converts a local raw capture into a validated record.
  - DoD: `compare` output is byte-identical to today's.
- [ ] 5. **Update `docs/benchmarks/capability-discovery.md` in place** (depends on 4).
  - Sections: Baseline (n=1) kept; Task set v1; Bounded experiment plan with operator pins and an empty "Approved by / date" line; Capture recipe; Mode availability matrix (7 rows, with `UNKNOWN` for unverified facts); Correlation and enforcement gate (#63 M8 as a hard stop); Results pre-filled `NOT_RUN`, with TC4 under discovery marked `not measurable: provider not in _CAPABILITY_ENDPOINTS`; Adjunct (non-comparable) for #1096; Decision rule plus `PENDING`.
  - DoD: no new competing benchmark document; `docs/capability-pilot-status.md` links to the updated section.
- [ ] 6. **Operator step, not the implementer** (depends on 5 and on the experiment plan's approval line being filled). Run 5 interleaved repetitions per measurable (task, mode) cell, plus NEG per mode. Establish with evidence whether the Portal `minimize_tools` and `search_and_execute` arms can run on an isolated test portal; otherwise mark them `not measurable` with the provider limitation. Run `aggregate` and paste the tables.
  - DoD: every cell holds measured values with n, `not measurable: <reason>`, or `NOT_RUN`.
- [ ] 7. **Operator step: decision** (depends on 6). Apply the pre-registered rule and record exactly one of `ADOPT_MCTL_NATIVE` / `ADOPT_PORTAL_MODE` / `HYBRID` / `DEFER`, with rollout guardrails and follow-up issues: mctlhq/.github#165, plus provider registration if mctl-native is chosen. Post the decision on #597, link it from mctlhq/.github#35, and add #597 as a sub-issue of #35 to clear the `HierarchyMissingParent` drift.
  - DoD: the comment URL is recorded in the doc's Decision section.

## Tests

- [ ] T1. The existing `tests/test_capability_bench.py` passes unchanged, so `compare` / `compare_report` stay backward compatible.
- [ ] T2. `validate_task` rejects unknown keys and an empty `expected_capabilities`, and accepts all five shipped fixtures.
- [ ] T3. `validate_run_record` rejects each payload key (`arguments`, `result`, `answer_text`, `message_text`) and unknown `kind` values.
- [ ] T4. `cell_metrics` over 5 fixture records:
  - computes p50/p95 and the success rate correctly;
  - keeps first-turn tokens separate from totals;
  - counts search, describe and invoke calls and retries.
- [ ] T5. `cell_metrics` over 3 records reports n=3, omits p95 and flags `below-minimum-n`.
- [ ] T6. A record invoking or seeing a capability outside expected and eligible, or a NEG run where the excluded capability appears, gives `permission_preserved=false`.
- [ ] T7. An invoke with no matching trace, or with a trace whose policy result is `absent` or that lacks an execution context id, gives `audit_complete=false`.
- [ ] T8. `aggregate` renders `NOT_RUN` for empty cells and `not measurable: <reason>` for declared modes, never `0`, and prints the structural vs end-to-end table.
- [ ] T9. The new code imports neither `claude_agent_sdk` nor `mcp` at module scope, so the pure tests run without network, matching the existing T14 convention.

## Rollback

Everything is additive and offline: fixtures under `tools/bench_tasks/`, pure functions and subcommands in `tools/capability_bench.py`, and a documentation update. Reverting the PR restores the prior state. No runtime, profile, Portal or deployment state is touched. If the operator enabled any Portal arm in task 6, it was on an isolated test portal, and the experiment plan's isolation/rollback step disables it. Production `code_mode: off` is never modified.
