# Design: issue-1014-spike-do-devloop-success-metrics-detect (narrowed)

Proposal only; no implementation approval. This is the operator-selected narrow follow-up of 2026-11-17.
It supersedes the earlier broad experiment (offline harness, M1-M8/A0, perturbation controls, status corpus),
which was never executed. The PR #1082 research is reused as provenance only; it is open and unmerged.

## Current state (repository source, mctl-agents `main` 4d7efd3555eafbb4af969687e029c5b5b9863b14)

Not deployed or live state.

- Baseline: `tests/fixtures/context_eval/baseline.json`. Verified in the full file: a TOP-LEVEL key `_header`
  containing `evaluator_name: "issue-investigator-context-eval"`, `evaluator_version: "1.0.0"`,
  `metrics_contract_version: "adr-015/1"`, written by `_regenerate`. All other
  top-level keys are case ids (for example `01-all-fresh-labelled`), each mapping strategy name
  (for example `deterministic-fixed-order`) to a metrics object. Metrics include scalars
  (`f1`, `stale_rate`, `context_bytes`, ...), a list `missing_expected`, and a nested list of objects
  `coverage_by_kind` (`bytes`, `candidates`, `included`, `kind`). A record without metrics is stored as
  `{"verdict": ...}`.
- Constants in `orchestrator/context_eval.py`: `EVALUATOR_NAME`, `EVALUATOR_VERSION`,
  `METRICS_CONTRACT_VERSION`. They already populate `_header` and are the existing identity contract. They
  are not the strategy or catalog content hashes.
- Comparison today, `tests/test_context_eval.py::test_baseline_matches`:

  ```python
  for case_id, by_strategy in records.items():
      for strategy, record in by_strategy.items():
          actual = record.metrics.to_dict()
          expected = baseline[case_id][strategy]
          for metric, expected_value in expected.items():
              if actual.get(metric) != expected_value:
                  failures.append(...)
  ```

  Exact `!=`, including nested values; no tolerance. Loops follow actual records and baseline metrics, so:
  extra actual metrics, baseline-only cases or strategies and metrics deleted from the baseline are not
  reported; a case missing from the baseline is a bare `KeyError`; `actual.get` conflates `None` and absent;
  `_header` is never read.
- `test_baseline_drift_is_detected_and_named` re-implements the same expected-only loop on a mutated copy
  (sets `02-stale-source` `stale_rate` to `999.0` and expects one named failure). It therefore tests a copy
  of the logic, not the shared path.
- Existing neighbours: `test_fixture_harness_ignores_context_env_vars`,
  `test_every_case_runs_under_both_strategies`, `test_harness_uses_the_real_run_pipeline`. Other tests in the
  module use `pytest.approx` or exact checks for their own purposes; that is separate.
- Existing update procedure (module docstring; documentation only, not run in this task):
  `uv run python -m tests.test_context_eval --regenerate [case_id ...]`, a `# pragma: no cover` maintenance
  entry point `_regenerate` behind `if __name__ == "__main__":`. It rewrites `_header`, regenerates the named
  (or all) cases and preserves untouched cases. The docstring says only for deliberate changes, never to turn
  a red run green; it is never a fixture or CI step.
- Open PRs: a sweep of 23 open mctl-agents PRs found no file touching `context_eval` or
  `fixtures/context_eval`. Bounded observation, not a guarantee.

## Proposed change (not approved)

Smallest sufficient, test-local; no runtime `context_eval` change, no new identity fields.

1. **One shared comparison function** in `tests/test_context_eval.py` (name proposed:
   `_baseline_differences(baseline, records) -> list[str]`). Both `test_baseline_matches` and the drift
   tests call it, so regressions exercise the real path rather than a second copy.
   - Header: `baseline.get("_header")` must exist and its three fields must equal `ce.EVALUATOR_NAME`,
     `ce.EVALUATOR_VERSION`, `ce.METRICS_CONTRACT_VERSION`. Otherwise emit named differences such as
     `_header/evaluator_version: baseline='0.9' current='1.0.0'` or `_header: missing`.
   - Membership: let `baseline_cases = {k for k in baseline if k != "_header"}`. Report case ids present on
     only one side; for shared cases report strategies on only one side; for shared strategies report metric
     names on only one side. Use sentinel membership (`key in mapping`), not `.get`, so explicit `None`
     differs from absent.
   - Values: for metrics present on both sides keep exact `!=` (no tolerance, nested values included). A
     record without metrics is compared through its `{"verdict": ...}` form as `_regenerate` stores it.
   - Output: sorted, named paths `case/strategy/metric` with side.
2. **Do not rewrite or read the baseline for repair.** No auto-regeneration; failure messages point to the
   existing deliberate procedure.
3. **Update-procedure note** (short, in the module docstring of `tests/test_context_eval.py`): regeneration only for deliberate changes, with a written reason; the diff of
   `baseline.json` including `_header` is reviewed by the owner; a changed `evaluator_version` or
   `metrics_contract_version` is a reviewed bump of the constants plus a regenerated baseline, never
   a silent upgrade; the existing baseline is **not** regenerated to get a green run.

### Allowlist for the later implementation

Exact minimal allowlist: `tests/test_context_eval.py` only (shared test-local helper, tests, and the update
procedure in the module docstring).

- Not allowed: `orchestrator/**`, `baseline.json`, other fixtures, CI, workflows, and any other path. A
  separate helper module or a runbook is not authorized; it needs a separate scope decision.

Drift preflight: re-read the latest source (`baseline.json`, the test module, the constants) before
implementing. If it differs from this document, report it before coding. No new schema is needed.

## Alternatives

- **Add numeric tolerances.** Dropped: the current comparator is exact and the owner said not to change it.
- **New second comparator or harness.** Dropped: duplicates the existing check; the owner ruled out new
  harnesses.
- **Add new identity fields to the baseline.** Dropped: the three existing fields and constants suffice.
- **Auto-refresh the baseline after a mismatch.** Dropped: greenwashing.
- **The earlier broad regression-metrics experiment.** Superseded by this narrowing, not performed.

## Platform impact

- No runtime, GitOps, CWFT, policy or deployment change. Tests and an update note only.
- Risk: the stricter check may expose existing silent drift (extra metrics, header mismatch) on the first
  run. That would be a finding to review, not something to fix by editing the baseline in the same change
  without the owner's reasoned approval.
- Not claimed: no measured result, no detection rate, no live telemetry. Tokens are not monetary cost.
