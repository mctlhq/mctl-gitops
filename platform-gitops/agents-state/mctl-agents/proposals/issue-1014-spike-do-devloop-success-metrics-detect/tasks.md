# Tasks: issue-1014-spike-do-devloop-success-metrics-detect

- [ ] 1. Write the duplicate map in `docs/spikes/1014-regression-metrics.md` (`STATUS: DRAFT`) covering
  #918, #854 (#871 to #873), #848, mctlhq/.github#313, #60 and ADR 015/019/021, each marked read or
  not-observed. DoD: every related item has a row, and every breakage mode names its existing owner
  or `none`.
- [ ] 2. Write the M1 to M8 and A0 taxonomy table, with the producer file and symbol or gitops field for
  each mode and an "article mapping: not observed" note. (depends on 1) DoD: no mode lacks a source
  or a `missing` state.
- [ ] 3. Extract `docs/spikes/1014/status-corpus.yaml` from mctl-gitops
  `agents-state/mctl-agents/proposals/*/.status.yaml`, keeping only these fields: status,
  execution.agent and version, attempt timestamps, completion.authoritative outcome, stop_reason and
  verification counts, review_attempts, ci_blockers, merged_at. Record the mctl-gitops commit SHA it
  was taken from. DoD: every record passes `orchestrator.redaction.contains_credential`.
- [ ] 4. Implement `tools/spike_1014_regression_metrics.py` with `--results`, reading the #791, #796 and
  #825 records and the status corpus. Compute per-arm pass-rate, success, tokens, turns, wall clock,
  tool calls and error, 429, timeout and policy-denial counts, using `unknown` for missing inputs.
  (depends on 3) DoD: deterministic output in `docs/spikes/1014/results.json`, with no network and
  no model calls.
- [ ] 5. Add perturbation controls for M1 to M8 (`origin: control`) and the per-mode detection verdicts
  `DETECTED_BY_PASS_RATE`, `DETECTED_ONLY_BY_SECONDARY`, `UNDETECTED` and `UNKNOWN`, with the
  provisional thresholds stated in the output. (depends on 4) DoD: each mode has one verdict, and
  real and control results are reported separately.
- [ ] 6. Write the experiment and metrics section of the report: baseline vs candidate for success,
  cost, latency and reliability; the A0 attribution count; the M4 and M5 field coverage; caveats on
  n and on controls. (depends on 5) DoD: every number is traceable to `results.json`, and every
  unknown is labelled unknown.
- [ ] 7. Write the recommendation (one token from ADOPT_FOLLOW_UPS, ADOPT_SUBSET, RESEARCH_ONLY or
  REJECT, with the owner decision left blank) and draft follow-ups only for gaps that were proven,
  each under an existing owner. (depends on 6) DoD: no new epic or runtime is proposed, and each
  follow-up names its owner, signal and dependency.

## Tests

- [ ] T1. `tests/test_spike_1014_regression_metrics.py`: running the harness twice on the committed
  inputs gives byte-identical `results.json`.
- [ ] T2. A metric whose input field is absent is reported as `"unknown"`, never `0`.
- [ ] T3. A pass-preserving perturbation (for example tokens x1.5) yields `DETECTED_ONLY_BY_SECONDARY`.
  A control that flips an oracle result yields `DETECTED_BY_PASS_RATE`. M6 with no input yields
  `UNKNOWN`.
- [ ] T4. Every record in `docs/spikes/1014/status-corpus.yaml` passes `contains_credential`, and only
  allowlisted keys are present.
- [ ] T5. Non-authorization: no module under `orchestrator/` imports `tools.spike_1014_regression_metrics`.

## Rollback

Docs, an offline tool and a test only. Revert the PR. No runtime, gitops or data migration is involved.
