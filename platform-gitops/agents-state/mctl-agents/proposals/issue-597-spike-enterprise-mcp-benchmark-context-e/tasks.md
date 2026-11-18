# Tasks: issue-597-spike-enterprise-mcp-benchmark-context-e

- [ ] 1. **Write the task-set oracles.** Add `tools/bench_tasks/tc1-roadmap.yaml`, `tc2-triage.yaml`, `tc3-tg-cross.yaml` and `neg-consequential.yaml`, with the fields `prompt`, `expected_capabilities`, `argument_constraints`, `answer_facts` and `consequential`. All prompts must be read-only.
  - DoD: the four fixtures exist, and a loader in `tools/capability_bench.py` validates them. Unknown keys and an empty `expected_capabilities` are rejected.
- [ ] 2. **Define the run-record format** (depends on 1). Add a pure `load_run_record` / `validate_run_record` in `tools/capability_bench.py`.
  - Fields: `run_id`, `mode`, `task_id`, `model`, `profile_version`, `catalog_digest`, `result_messages`, `tool_calls[{name, capability_id, kind, arguments_hash, is_retry}]`, `invocation_traces`, `first_turn_cache_creation_tokens`, `wall_clock_ms`, `final_answer_digest` and `oracle_facts_found`.
  - DoD: payload-bearing keys such as `arguments`, `result` and `answer_text` are rejected.
- [ ] 3. **Add pure per-cell metrics** (depends on 2): `cell_metrics(records, task)`.
  - Metrics: n; initial and total tokens, separately, reusing `_totals_for_transcript`; turns; discovery, describe, invoke and retry counts; p50/p95 latency, with p95 only when n >= 5; oracle success rate; `permission_preserved`; `audit_complete`.
  - DoD: the function is pure, with no I/O.
- [ ] 4. **Add the `aggregate` subcommand** (depends on 3): `aggregate RUNS_DIR --tasks DIR [--not-measurable mode=reason ...] [--schema-bytes FILE]`.
  - It renders the per-mode x per-task markdown tables, using `NOT_RUN` for empty cells and `not measurable: <reason>`.
  - It adds a structural first-turn delta against the 61,213 / 23,392 baseline, next to the end-to-end delta.
  - DoD: `compare` output is unchanged.
- [ ] 5. **Update `docs/benchmarks/capability-discovery.md` in place** (depends on 4).
  - Keep the 2026-09-26 section as the "Baseline (n=1)".
  - Add these sections: task set v1, bounded experiment plan (pins, repetitions, USD cap, isolation/rollback, operator-approval line), capture recipe, results tables pre-filled `NOT_RUN`, mode applicability matrix including the research-extension rows (unverified facts = `UNKNOWN`, #63 M8 as a hard gate), a non-comparable Adjunct section for #1096, and Decision with the pre-registered rule and `PENDING`.
  - DoD: no new competing benchmark document exists.
- [ ] 6. **Operator step, not the implementer** (depends on 5 and operator approval of the plan). Execute 5 repetitions per measurable `(task, mode)` cell. Determine whether the Portal `minimize_tools` and `search_and_execute` arms can be isolated, and mark them `not measurable` with evidence if they cannot. Run `aggregate` and fill in the doc.
  - DoD: every cell holds measured values, `not measurable` or `NOT_RUN`, with n stated.
- [ ] 7. **Operator step: decision** (depends on 6). Apply the pre-registered rule and record exactly one of `ADOPT_MCTL_NATIVE` / `ADOPT_PORTAL_MODE` / `HYBRID` / `DEFER`, with rollout guardrails and the follow-up issue(s). Post it on #597 and link it from mctlhq/.github#35.
  - DoD: the comment URL is recorded in the doc.

## Tests

- [ ] T1. The existing `tests/test_capability_bench.py` tests pass unchanged, which confirms `compare` and `compare_report` are backward compatible.
- [ ] T2. `validate_run_record` rejects records carrying `arguments`, `result` or `answer_text`, and rejects unknown `kind` values.
- [ ] T3. `cell_metrics` with 5 fixture records:
  - computes p50/p95 and the success rate correctly;
  - keeps initial tokens separate from total tokens;
  - counts discovery, describe and invoke calls and retries.
- [ ] T4. `cell_metrics` with 3 records reports n=3 and omits p95.
- [ ] T5. A record that invokes a capability outside `expected_capabilities` or the eligible set gives `permission_preserved=false`.
- [ ] T6. A consequential invoke whose trace has `policy_checkpoint: absent`, or no matching trace at all, gives `audit_complete=false`.
- [ ] T7. `aggregate` renders `NOT_RUN` for an empty cell and `not measurable: <reason>` for a flagged mode, never `0`.
- [ ] T8. The task-fixture loader rejects unknown keys and empty oracles.

## Rollback

The change is additive and offline: new fixtures under `tools/bench_tasks/`, new pure functions and a subcommand in `tools/capability_bench.py`, and a documentation update. Reverting the PR restores the previous state. No runtime, profile, Portal or deployment state is touched, so there is nothing to roll back operationally. If an operator's Portal test mode was enabled under task 6, its isolation/rollback step in the experiment plan disables it, and production `code_mode: off` is never modified.
