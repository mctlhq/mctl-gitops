# Tasks: issue-266-feat-context-evals-measure-retrieval-qua

- [ ] 1. Write `docs/adr/012-context-evaluation-contract.md` recording the
      normative decisions: context evaluation is separate from final-output
      evaluation (#60) and joins on `temporal_workflow_id` + `eval_id`; the
      `content_hash` rule and its `created_at` + `cost.assembly_latency_ms`
      exclusions; the closed label and outcome vocabularies; why token cost is
      an estimate and why `ContextBudget` is not extended (ADR 009 sec. 6);
      the payload-free rule; and the honest statement that `target-repo`
      precision is source-granular until ADR 009 follow-up (e) lands.
      Cross-link it from `docs/adr/009-context-snapshot-contract.md`'s
      follow-up table and from `docs/agent-inventory.yaml`, matching how ADR
      009 is cross-linked today.
      — DoD: ADR merged in the house style (Status/Date/Context/Alternatives/
      Non-goals/Platform impact), states which decisions may not be reopened,
      and contradicts nothing in ADR 007/009/011.

- [ ] 2. Add `orchestrator/context_eval.py` with the document contract
      (depends on 1) — `API_VERSION = "context.mctl.ai/v1alpha1"`,
      `KIND = "ContextEvaluation"`, `SUPPORTED_API_VERSIONS`,
      `ContextEvaluationError`, and frozen dataclasses `SourceLabel`,
      `MissingEvidence`, `LabelSet`, `RetrievalQuality`, `ContextCost`,
      `SourceContribution`, `ContextEvaluation`, `ContextOutcomeLink`, each
      with `to_dict`/`from_dict` that reject unknown keys. Import `hash_bytes`,
      `canonical_json`, `ExecutionCorrelation` and `ContextStrategy` from
      `orchestrator.context_snapshot`; define no second hash rule.
      — DoD: module is stdlib-only, `ruff check .` and `mypy .` clean,
      `from_dict` fails loudly on an unsupported `api_version`/`kind` and on
      any unknown top-level or nested key.

- [ ] 3. Implement `seal_evaluation()` and `eval_id` derivation (depends on 2)
      — hash the canonical JSON of every field except `content_hash`,
      `eval_id`, `created_at` and `cost.assembly_latency_ms`; derive
      `eval_id = "ce-" + content_hash[7:23]`, mirroring
      `context_snapshot.seal` (`orchestrator/context_snapshot.py:932-933`).
      Add `recompute_evaluation_hash()` for fixture verification, mirroring
      `context_snapshot.recompute_content_hash` (`:952`).
      — DoD: sealing identical inputs at two `created_at` values and two
      latency values yields one `eval_id`; changing any other field changes it.

- [ ] 4. Implement the metric computation `evaluate(snapshot, metrics, *,
      labelset=None, now)` (depends on 3) — `selected_precision`,
      `useful_recall`, `stale_rate`, `duplicate_rate`, `noise_rate`,
      `conflict_rate`, `missing_evidence_count`, per-kind
      `SourceContribution`, and `ContextCost` with
      `estimate_tokens(byte_count)` under `ESTIMATOR_NAME = "bytes-div-4"` /
      `ESTIMATOR_VERSION = "1.0.0"`. Derive staleness and duplication from
      `ContextSource.freshness.staleness` and `selection.reason_code`
      (`"stale"`, `"duplicate-content"`) rather than re-deriving them.
      — DoD: `labelset=None` yields `labelled=False` with
      `selected_precision`/`useful_recall` `None` and every other metric
      populated; a zero denominator yields `None`, never a silent `0.0`;
      `ContextBudget` gains no field.

- [ ] 5. Add `to_log_dict()` to `ContextEvaluation` and `ContextOutcomeLink`
      (depends on 4) — ids, hashes, counts, rates, durations and
      estimator/labelset identifiers only, mirroring
      `ContextSnapshot.to_log_dict` (`orchestrator/context_snapshot.py:824`).
      — DoD: no `locator`, `selector`, label rationale free text or source body
      can appear in the returned dict for any input.

- [ ] 6. Extract `run_pipeline(candidates, config, now) -> (sources, budget,
      PipelineCounters)` out of `context_assembly.assemble()`
      (`orchestrator/context_assembly.py:656`) and call it from both
      `assemble()` and the new harness (depends on 2). Pure refactor: the
      stale sweep, `deduplicate`, `truncate_to_per_source_limit` and
      `apply_budget` keep their current order and semantics.
      — DoD: the full existing `tests/test_context_assembly.py` suite passes
      unchanged, and `tests/test_context_snapshot.py:184`'s byte-for-byte
      golden `content_hash` assertion still holds.

- [ ] 7. Add `orchestrator/context_eval_cases.py`, the fixture loader and
      offline harness (depends on 6) — parse `case.json` into
      `CandidateSource` values, parse `labels.json` into a `LabelSet` with its
      own `content_hash`, run `run_pipeline`, `seal()` with a fixture
      `ExecutionCorrelation`, and `evaluate()`.
      — DoD: stdlib-only, performs no network call and reads nothing outside
      `tests/fixtures/context/eval/`; running one case twice produces identical
      `snapshot_id`, `eval_id` and metrics.

- [ ] 8. Author the six curated cases under
      `tests/fixtures/context/eval/cases/` (depends on 7):
      `logs-relevant-and-irrelevant` (`loki-logs`, mixed relevance),
      `deployment-stale-vs-current` (one source aged past its
      `max_age_seconds` so `classify_freshness` marks it `stale`),
      `github-issue-and-pr-evidence` (`github-issue`,
      `github-issue-comment`, `github-pr`),
      `conflicting-and-duplicate-evidence` (a byte-identical pair that
      `deduplicate` must collapse, plus two contradicting sources labelled
      `conflicting`), `missing-evidence` (`expected_missing` entries no
      candidate satisfies, so `useful_recall < 1`), and
      `budget-truncation-cost` (oversized source exercising
      `truncate_to_per_source_limit` and `apply_budget`).
      — DoD: every `kind` validates against `context_snapshot.SOURCE_KINDS`;
      all bodies are short, obviously synthetic strings with no copied
      production log, issue text or credential; the six cases cover every
      bullet of the issue's "Evaluation fixtures" list.

- [ ] 9. Add `tools/run_context_eval.py` (depends on 8), following
      `tools/record_workflow_history.py`'s convention — run all cases, print a
      JSON report plus a per-case table, support `--case <id>` and
      `--update-baseline`, and state in the report that `target-repo` is
      scored at source granularity.
      — DoD: `python -m tools.run_context_eval` exits 0 and prints a report;
      `--update-baseline` rewrites `tests/fixtures/context/eval/baseline.json`
      deterministically (sorted keys) and is the only way that file changes.

- [ ] 10. Generate and commit `tests/fixtures/context/eval/baseline.json`
      (depends on 9) — per case: `snapshot_id`, snapshot `content_hash`,
      `eval_id`, evaluation `content_hash`, and every metric except
      `assembly_latency_ms`.
      — DoD: file is byte-stable across two consecutive
      `--update-baseline` runs on different machines.

- [ ] 11. Implement `derive_outcome_link(status_yaml_path)` (depends on 4) —
      read the `context:` block `run_issue_investigator.write_status_yaml`
      already commits (`orchestrator/run_issue_investigator.py:1058-1063`) and
      the file's `status`, and return a sealed `ContextOutcomeLink`. Validate
      `outcome` against the closed union of `.status.yaml` statuses and
      `orchestrator/pr_adoption.py:643`'s `TERMINAL_STATUSES`.
      — DoD: returns `None` (never raises) for a `.status.yaml` with no
      `context:` block; rejects an out-of-vocabulary `status`; writes nothing.

- [ ] 12. Emit the production telemetry line (depends on 5) — in
      `run_issue_investigator._assemble_context`, inside the existing `try`,
      after the `[context] context_assembly=` print
      (`orchestrator/run_issue_investigator.py:1650`), call
      `context_eval.evaluate(..., labelset=None)` and print
      `[context] context_eval={...}` with sorted keys. No new env var; the line
      rides the existing `ISSUE_INVESTIGATOR_CONTEXT_MODE` gate.
      — DoD: `off` mode emits nothing; `shadow` mode swallows any evaluation
      exception and continues the investigation (existing policy at
      `:1640-1645`); `on` mode propagates; the line prefix is stable and
      single-line so Promtail's metrics stage can scrape it, matching
      `orchestrator/lifecycle/shadow.py:121`.

- [ ] 13. Update `README.md` and `docs/agent-inventory.yaml` (depends on 12) —
      document the two `[context]` log lines, the harness invocation, and how
      to refresh the baseline.
      — DoD: `uv run pytest tests/test_agent_inventory.py
      tests/test_diagram_facts.py` passes.

## Tests

- [ ] T1. `tests/test_context_eval.py::test_metric_math` — table-driven
      precision/recall/stale/duplicate/noise/conflict cases including empty
      source lists, all-included, all-excluded, and zero denominators yielding
      `None`.
- [ ] T2. `test_seal_is_deterministic_across_created_at_and_latency` — two
      seals differing only in `created_at` and `cost.assembly_latency_ms`
      produce one `eval_id` and one `content_hash`; any other field change
      produces a different one. Mirrors
      `tests/test_context_snapshot.py:152,161`.
- [ ] T3. `test_eval_id_is_derived_from_content_hash` — `ce-` prefix and the
      `[7:23]` slice, mirroring `tests/test_context_snapshot.py:174`.
- [ ] T4. `test_baseline_is_reproduced_for_every_case` — parametrized over all
      six cases, exact equality against `baseline.json` for every metric
      except `assembly_latency_ms`. This is the regression gate.
- [ ] T5. `test_regression_is_detected` — mutate `AssemblyConfig`
      (`max_bytes` and `max_sources`) and the `freshness_table` in-test and
      assert the computed metrics diverge from the baseline, proving the gate
      actually catches a ranking/filtering/config change rather than passing
      vacuously.
- [ ] T6. `test_no_locator_selector_or_payload_leaks_into_eval_telemetry` —
      plant a marker string in a case body, locator and selector; assert it
      appears in no `to_log_dict()` and in no serialized evaluation. Mirrors
      `tests/test_context_assembly.py:288`.
- [ ] T7. `test_module_import_is_stdlib_only` for `context_eval.py` and
      `context_eval_cases.py`, copied from
      `tests/test_context_assembly.py:532`.
- [ ] T8. `test_module_source_has_no_authorization_vocabulary` and
      `test_module_has_no_output_grading_vocabulary` — grep the module source
      for allow/deny/permit/grant and for `answer`/`response_quality`/
      `output_score`/`rubric`/`judge`, enforcing both the ADR 009 sec. 5
      boundary and the #60 boundary. Mirrors
      `tests/test_context_assembly.py:560,572`.
- [ ] T9. `test_from_dict_rejects_unknown_keys_and_api_version` at top level
      and in every nested block, mirroring
      `tests/test_context_snapshot.py:205-233`.
- [ ] T10. `test_context_budget_field_set_is_unchanged` — assert
      `ContextBudget`'s fields are exactly `max_sources`, `max_bytes`,
      `max_bytes_per_source`, `used_sources`, `used_bytes`, `truncated`, so no
      token- or context-window-named field is ever added, per ADR 009 sec. 6.
- [ ] T11. `test_labelset_hash_changes_when_a_label_changes` and
      `test_evaluation_records_the_labelset_hash` — a metric can never be
      silently compared across label revisions.
- [ ] T12. `test_missing_evidence_lowers_recall` — the `missing-evidence` case
      reports `useful_recall < 1.0` and a non-zero `missing_evidence_count`.
- [ ] T13. `test_unlabelled_production_path` — `evaluate(..., labelset=None)`
      yields `labelled=False`, `selected_precision is None`,
      `useful_recall is None`, and populated stale/duplicate/cost/contribution
      blocks.
- [ ] T14. `test_derive_outcome_link_reads_status_yaml` — round-trips a
      `.status.yaml` carrying a `context:` block; returns `None` without a
      block; rejects an out-of-vocabulary status.
- [ ] T15. `test_assemble_behaviour_is_unchanged_by_the_refactor` — the full
      existing `tests/test_context_assembly.py` and
      `tests/test_context_snapshot.py` suites pass untouched after task 6,
      including the byte-for-byte golden-fixture hash.
- [ ] T16. `test_investigator_emits_both_context_lines` — with
      `ISSUE_INVESTIGATOR_CONTEXT_MODE=shadow`, capsys shows exactly one
      `[context] context_assembly=` and one `[context] context_eval=` line,
      each valid single-line JSON; with `off`, neither appears.
- [ ] T17. `test_shadow_mode_survives_an_evaluation_failure` — monkeypatch
      `context_eval.evaluate` to raise; assert the investigation continues and
      a warning is printed in `shadow`, and that `on` propagates.

## Rollback

The change is additive and gated, so rollback is cheap at three levels.

1. **Operational, no deploy.** The production surface is one stdout line
   emitted only when `ISSUE_INVESTIGATOR_CONTEXT_MODE` is not `off`. That flag
   already defaults to `off` (`orchestrator/run_issue_investigator.py:139`,
   `.env.example:62`), so setting it back to `off` — or simply not having set
   it — removes the entire runtime footprint without touching code. No new env
   var is introduced, so there is no second switch to remember.

2. **Revert the emission only.** Drop the two added lines in
   `_assemble_context` (task 12). `orchestrator/context_eval.py`,
   the harness, the fixtures and the CI gate keep working as offline
   developer tooling with zero production reach — the same posture
   `orchestrator/context_snapshot.py` itself held between #264 and #265.

3. **Revert the whole change.** `git revert` the merge. Because tasks 2-5 and
   7-11 only add new files, and the single edit to existing production code is
   task 6's `run_pipeline` extraction plus task 12's two lines, a revert
   restores `context_assembly.py` and `run_issue_investigator.py` to their
   current form. Nothing persisted needs cleanup: no mctl-api row, no GitOps
   schema change, no migration, no new secret. Already-emitted
   `[context] context_eval=` log lines age out of Loki under existing
   retention; any Promtail metrics stage added for the new prefix is
   configuration in a different repo and is removed independently.

The highest-risk item is task 6, the `run_pipeline` extraction, because it is
the only edit to already-shipping logic. It is guarded by T15 and by the
byte-for-byte golden `content_hash` assertion at
`tests/test_context_snapshot.py:184`: if the refactor changed selection
behaviour at all, that hash would move and CI would fail before merge. If it
proves contentious in review, tasks 7-10 can fall back to duplicating the
pipeline order in the harness — worse (the harness would then test a copy
rather than the production path) but strictly non-invasive, and it lets
everything else ship while task 6 is settled separately.
