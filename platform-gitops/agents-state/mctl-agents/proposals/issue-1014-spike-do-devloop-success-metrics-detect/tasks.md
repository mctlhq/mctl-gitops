# Tasks: issue-1014-spike-do-devloop-success-metrics-detect (narrowed)

Proposal only. None of these tasks is approved for implementation; start only after separate explicit owner
approval. No uv, install, regeneration or test run is part of the documentation task that produced this file.

- [ ] 1. Verify sources and overlap. Re-read `tests/test_context_eval.py`, `orchestrator/context_eval.py`
  constants and `tests/fixtures/context_eval/baseline.json` at current `main`; confirm the `_header`
  nesting; re-check open PRs for `context_eval` overlap; record exact paths and fields.
  DoD: paths, symbols and header nesting written down; any mismatch with the design is raised before coding.
- [ ] 2. Implement one shared comparison function in `tests/test_context_eval.py` that checks the header
  against `EVALUATOR_NAME`, `EVALUATOR_VERSION`, `METRICS_CONTRACT_VERSION`, symmetric membership of cases,
  strategies and metrics (ignoring only `_header` at case level), explicit `None` vs absent, and exact `!=`
  for shared values. Route `test_baseline_matches` through it. (depends on 1)
  DoD: no tolerance introduced; failures are sorted named paths; the baseline file is not modified.
- [ ] 3. Describe the update procedure (existing `--regenerate` command as documentation, reason, owner
  review of the `baseline.json` diff including `_header`, no regeneration to turn a red run green).
  (depends on 1) DoD: note placed in the allowlisted location.
- [ ] 4. Run existing local checks listed below and report results honestly. (depends on 2, 3)

## Tests (real fixture format, no new corpus)

- [ ] T1. Matching baseline and records pass.
- [ ] T2. A metric removed from a copy of the baseline is reported as `missing in baseline`; a metric
  removed from the actual side is reported as `missing in actual` (extra metric refused).
- [ ] T3. A baseline case or strategy with no current record, and a current case or strategy absent from
  the baseline, are each refused with a named path.
- [ ] T4. Incompatible evaluator: wrong `evaluator_name`, wrong `evaluator_version`, wrong
  `metrics_contract_version`, missing field and missing `_header` each refuse.
- [ ] T5. A numeric difference (as in the existing `02-stale-source` / `stale_rate` case) still refuses, and
  a nested `coverage_by_kind` difference refuses; there is no tolerance.
- [ ] T6. Explicit `None` on one side vs absent on the other is refused.
- [ ] T7. `test_baseline_drift_is_detected_and_named` is rewritten to call the shared function instead of
  copying the loop.

Regressions mutate in-memory copies (`copy.deepcopy`) of the real baseline; the file is never edited.

## Independent mutations (done on a temporary commit, then restored with `git restore`)

- [ ] M1. Make the shared function one-sided again (iterate only baseline metrics). T2 and T3 must go red.
- [ ] M2. Disable the header check. T4 must go red.
  Each mutation is committed-first, edited, run, restored and confirmed clean with `git status`.

## Local checks (existing)

The module's own tests, for example `uv run pytest tests/test_context_eval.py`, plus whatever repository
lint already applies to `tests/`. Report any check that could not be run. Do not regenerate the baseline.

## Rollback

Tests and a note only. Revert the PR. No runtime, GitOps, data or deployment state changes.
