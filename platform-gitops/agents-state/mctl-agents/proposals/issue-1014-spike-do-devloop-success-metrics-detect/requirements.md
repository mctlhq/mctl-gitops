# Spike #1014 (narrowed): make the existing context-eval baseline comparison symmetric and identity-aware

## Status of this document

- Proposal only. It is **not** an implementation approval. Implementation needs a separate explicit owner
  approval; `.status.yaml` and the existing parked workflow are untouched.
- **Operator-selected narrow follow-up (2026-11-17).** The owner narrowed the original spike to one small
  fix of the existing baseline comparison. This revision supersedes the earlier broad plan (offline
  harness `tools/spike_1014_regression_metrics.py`, M1-M8/A0 taxonomy, perturbation controls, status
  corpus, `results.json`). That plan was a proposal and was never executed; nothing in it was observed or
  measured, and it is not carried forward.

## Provenance

- Issue mctlhq/mctl-agents#1014 (scout-generated): do DevLoop success metrics detect regressions that
  pass-rate misses. Research: mctl-agents PR #1082 (`docs/spikes/devloop-regression-metrics.md`), **open and
  unmerged** at `a610c7265ea2383ce2d006b13f525bf1a66cc425`. It is research, not executable evidence.
- Source facts below were read from mctl-agents `main` at `4d7efd3555eafbb4af969687e029c5b5b9863b14`
  through a read-only connector. They are repository-source observations, not deployed or live state.
- A bounded sweep of 23 open mctl-agents PRs found none touching `context_eval` or
  `tests/fixtures/context_eval`. That is not proof that no parallel branch exists; re-check before
  implementing.

## Problem (observed in source)

The existing drift check `test_baseline_matches` in `tests/test_context_eval.py` compares
`tests/fixtures/context_eval/baseline.json` with current records using expected-only iteration:

- the outer loops follow the **current records**, so a baseline case or strategy that no longer exists is
  never noticed, and a new case or strategy missing from the baseline raises a `KeyError` rather than a named
  failure;
- the inner loop iterates the **baseline's** metrics, so a metric the code newly emits (extra actual metric)
  or a metric deleted from the baseline escapes;
- `actual.get(metric)` collapses an explicit `None` and an absent key;
- the baseline `_header` (`evaluator_name`, `evaluator_version`, `metrics_contract_version`) is written by
  the maintenance entry point but never checked by any test.

Comparison is exact Python `!=`, including nested values (for example `coverage_by_kind`). There is **no
numeric tolerance** in this comparator and none is to be introduced.

## User stories

- AS the owner of the context-eval fixture I WANT drift in either direction (missing or extra case,
  strategy or metric) to fail with a named path SO THAT a green run really means the baseline and the
  current output agree.
- AS a reviewer I WANT a baseline written by a different evaluator name, version or metrics contract to be
  refused SO THAT numbers from incompatible evaluators are never compared silently.
- AS the owner I WANT baseline updates to stay an explicit, reviewed action SO THAT a red run is never
  turned green by regeneration.

## Acceptance criteria (EARS)

- WHEN the baseline and the current records are compared THE SYSTEM SHALL check membership symmetrically
  at three levels: case ids, strategies per case, and metric names per strategy, ignoring only the
  `_header` key at the case level. Each difference SHALL be reported as a named path
  (`case/strategy/metric`) with its side (`missing in baseline` or `missing in actual`).
- WHEN a metric is present with value `None` on one side and absent on the other THE SYSTEM SHALL report a
  difference; absent SHALL NOT equal `None`, and unknown values SHALL NOT be replaced by zeros.
- WHEN a metric is present on both sides THE SYSTEM SHALL keep the current exact `!=` comparison. No
  tolerance is added or changed.
- WHEN the baseline `_header` is compared THE SYSTEM SHALL require `evaluator_name`, `evaluator_version` and
  `metrics_contract_version` to equal the existing `EVALUATOR_NAME`, `EVALUATOR_VERSION` and
  `METRICS_CONTRACT_VERSION` constants of `orchestrator/context_eval.py`. A missing `_header`, a missing
  field or an unequal value SHALL fail with a named message. There is no fallback and no silent upgrade.
- WHEN the check fails THE SYSTEM SHALL NOT rewrite the baseline. Updating it remains the existing
  deliberate `--regenerate` action, with a written reason and owner review.
- WHILE this proposal is executed THE SYSTEM SHALL change only the existing test module, optionally one
  small test-local helper, and a short update-procedure note. No runtime `context_eval` change is needed
  and none is proposed; no new evaluator identity fields or schema are added.

## Out of scope

- M1-M8/A0 taxonomy, a new harness or tool, a historical status corpus, new signals, live telemetry,
  models, rollout and promotion gates.
- Tolerances, a second comparator, changes to `evaluate()` or to strategy or catalog content hashes
  (these are not evaluator identity).
- Updating the existing baseline file in order to get a green test.
- Any claim about live or deployed behaviour. GitOps configuration does not prove live state, and tokens
  are not monetary cost.

## Open questions

- The baseline file shows the three identity fields as a header. Source says `_regenerate` writes them
  under the top-level key `_header`. The implementer must confirm the exact nesting in the file before
  writing the check.
- Where the shared comparison lives: a test-local helper in `tests/test_context_eval.py` is the preferred
  minimum. The owner may prefer a separate helper module.
- Re-check open mctl-agents PRs for `context_eval` overlap immediately before implementation.
