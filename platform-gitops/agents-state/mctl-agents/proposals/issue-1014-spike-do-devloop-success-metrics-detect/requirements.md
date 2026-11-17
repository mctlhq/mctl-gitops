# Spike #1014: do DevLoop success metrics detect regressions that pass-rate scoring misses?

## Context

Issue mctlhq/mctl-agents#1014 (scout-generated) asks whether the signals MCTL uses to judge DevLoop
changes and model swaps would catch an agent regression that a pass-rate number hides. The cited article
(thenewstack.io "monitoring production AI agents") lists seven breakage modes. That page returned HTTP 403
to this run, so its list was not observed. This spike therefore builds its own breakage-mode taxonomy from
MCTL's own evidence and records the article mapping as an open question.

It matters because today's verdicts on model and runtime changes are pass/fail oracles: the bench cells in
`docs/spikes/791-hetzner-inference.md` and `docs/spikes/825-qwen38-effort-rebench.md` report `pass` per
cell, `tools/model_smoke.py --eval` reports per-workload accuracy, and the lifecycle outcome in mctl-gitops
`agents-state/<service>/proposals/*/.status.yaml` is essentially `merged` / `rejected` / `needs-triage`.
Two facts read during this investigation suggest pass-rate cannot attribute or localize a regression
today: every one of the 108 `execution:` blocks in `agents-state/mctl-agents/proposals/*/.status.yaml`
has `version: ''`, and only 1 of 180 proposals records `review_attempts` or `ci_blockers`. The spike
must test that suspicion with evidence, not assert it.

## User stories

- AS the platform owner I WANT to know which regression modes our current DevLoop success signals would
  and would not detect SO THAT I can trust (or stop trusting) pass-rate verdicts on model swaps and
  DevLoop changes.
- AS the maintainer of a model-swap or runtime bench (#791, #825, #917) I WANT a reusable list of
  secondary metrics, with where each is already produced, SO THAT the next bench reports them next to
  pass-rate.
- AS a reviewer of a follow-up I WANT each proven gap filed against an existing owner (#854's G1 to G7,
  #918's oracle classes, the usage ledger) SO THAT no parallel capability is built.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL include a duplicate map that records, for
  mctl-agents#918, mctl-agents#848, mctl-agents#854 and mctlhq/.github#313, whether it was read or
  not observed and which breakage modes it already owns.
- WHEN the spike defines its breakage-mode taxonomy THE SYSTEM SHALL tie each mode to a concrete MCTL
  signal source (file and symbol, or gitops field) or record it as `missing`.
- WHEN the offline harness `tools/spike_1014_regression_metrics.py --results` runs THE SYSTEM SHALL
  write `docs/spikes/1014/results.json` from committed inputs only (no network and no model calls).
- WHEN the harness compares a baseline arm with a candidate arm THE SYSTEM SHALL report pass-rate,
  success, cost (tokens), latency (wall clock and turns) and reliability (errors, 429s, timeouts,
  policy denials) separately for each arm.
- IF a metric's inputs were not captured for an arm THEN THE SYSTEM SHALL report that metric as
  `unknown` and SHALL NOT report it as 0.
- WHEN the harness applies a perturbation for a breakage mode THE SYSTEM SHALL record for that mode
  whether pass-rate changed and whether each candidate secondary metric changed beyond its stated
  threshold, giving a per-mode verdict of `DETECTED_BY_PASS_RATE`, `DETECTED_ONLY_BY_SECONDARY`,
  `UNDETECTED` or `UNKNOWN`.
- WHEN perturbations are hand-built controls THE SYSTEM SHALL mark them `origin: control`, apart from
  `origin: real` records, and SHALL report the metrics for the two origins separately.
- WHILE the spike runs THE SYSTEM SHALL change no runtime path: no DevLoop, Temporal, CWFT, gitops, policy,
  approval or release-binding file is edited, and no metric is used as a gate.
- WHEN the report is complete THE SYSTEM SHALL end with one recommendation for the "Regression-detection
  metric audit" outcome, using a decision token from `ADOPT_FOLLOW_UPS`, `ADOPT_SUBSET`,
  `RESEARCH_ONLY` or `REJECT`. The owner records the decision.
- WHEN a gap is proven THE SYSTEM SHALL draft a follow-up naming its existing owner (issue or module), the
  signal, and its dependency, without filing new epics.

## Out of scope

- Implementing any new metric, span, meter, gate or dashboard (that is follow-up work after the decision).
- Wiring evaluation results into promotion or release gates (ADR 015 and the #854 rule: evaluation
  signals never authorize).
- New epics, runtimes or LLM-as-judge scoring (mctl-agents#60 owns that).
- Live production runs, paid model calls or access to Tempo, Loki or mctl-api usage data beyond what is
  already committed.
- Reproducing the article's vendor claims.

## Open questions

- The article's seven breakage modes were not observed (HTTP 403). The spike uses an MCTL-derived
  taxonomy. Should a reviewer with access map the article's list onto it, and is a mode missing?
- mctlhq/.github#313 and mctl-agents#848 bodies were not read from this run (no GitHub access). The
  duplicate map marks them `not-observed` until the implementer or reviewer checks them.
- The mctl-api usage summary (`mctl_get_usage_summary`) was refused for this run's scope (403
  `agent_scope_denied`), so live cost and latency per DevLoop stage are not part of the baseline. Should
  the implementer use a committed export of it, if the owner provides one?
- Thresholds for "changed beyond threshold" (for example +25% tokens, +1 review round) are provisional
  and stated in the report. The owner may tighten them.
- Why is `execution.version` empty in every `.status.yaml`? Is it a producer bug or by design while the
  registry pins live in mctl-api agent executions? The spike reports the attribution gap either way.
