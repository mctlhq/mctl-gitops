# Spike #918: which DevLoop finding classes have a deterministic oracle, and should only those be promoted after independent validation?

## Context

Issue mctl-agents#918 takes one pattern from Google PageBreak (InfoQ, 2026-10) and asks whether it fits
DevLoop. The pattern is to separate model-generated hypotheses from findings that an independent
deterministic oracle reproduced. It is not "LLM output is invalid until a validator exists". DevLoop
produces findings from several places, and they mix two kinds of claim:
- Mechanically testable claims: a failing test, a schema violation, a stale premise about issue state, an
  affected dependency version.
- Judgement claims: an architecture concern, a governance inconsistency, an ambiguous requirement.
The places that produce findings:
- The issue-investigator's proposal triplets.
- The shepherd's parsed P1/P2 review findings (`orchestrator/run_shepherd.py` `CodexFinding`).
- Failing CI checks (`orchestrator/ci_checks.py` `CheckBlocker`).
- Implementer refusal notes.
- Incident-responder proposals.
- SecurityFinding occurrences (ADR 024).

Some validated-vs-candidate machinery already exists. ADR 022 (`orchestrator/runtime_assurance.py`)
promotes an `AssuranceFinding` from `candidate` to `confirmed` only through a replay. ADR 024 resolves
SecurityFindings only through a verification bound to the exact revision. ADR 018 grades evidence as
`observed > derived > asserted`, and `orchestrator/sdd/verify.py` returns `pass | fail | unknown`.
Investigator and reviewer findings have no comparable distinction. The spike has five jobs:
- Classify finding classes by oracle quality.
- Run a bounded before/after experiment on real findings with the smallest independent validators.
- Measure the effect.
- Name the classes that must never be hidden behind a deterministic gate.
- Recommend exactly one of `NO_GENERIC_GATE`, `VALIDATE_SELECTED_FINDING_CLASSES` or
  `ADD_VALIDATED_FINDING_CONTRACT`.

It changes no runtime behaviour.

## User stories

- AS a DevLoop owner I WANT a taxonomy of finding classes with an oracle rating each SO THAT I know where
  deterministic validation is possible and where it is not.
- AS a proposal reviewer I WANT mechanically checkable claims labelled `VALIDATED_FINDING` or
  `HYPOTHESIS` / `UNVALIDATED_FINDING` SO THAT I spend review effort on what is actually unproven.
- AS a platform maintainer I WANT the spike to reuse the ADR 018 / 022 / 024 vocabularies SO THAT
  DevLoop does not gain a second finding lifecycle.
- AS a security reviewer I WANT a guarantee that no validator runs exploit payloads or touches third-party
  targets SO THAT validation never becomes an attack.

## Acceptance criteria (EARS)

- WHEN the spike report `docs/spikes/918-finding-oracle-classes.md` is published THE SYSTEM SHALL
  contain exactly one `STATUS:` line whose value is `DRAFT` or one of `NO_GENERIC_GATE`,
  `VALIDATE_SELECTED_FINDING_CLASSES` or `ADD_VALIDATED_FINDING_CONTRACT`.
- WHEN the report lists the finding taxonomy THE SYSTEM SHALL rate each of the eight issue classes
  (runtime/test failure, static invariant/schema, security with safe local oracle, dependency/version
  affectedness, stale factual premise, architecture/design, governance/ownership, incomplete requirement /
  ambiguous product decision) as exactly one of `DETERMINISTIC`, `BOUNDED_BUT_NONDETERMINISTIC` or
  `NO_SAFE_ORACLE`. Each rating SHALL be backed by:
  - the existing module or contract that would serve as the oracle, or `none`;
  - the evidence the oracle consumes.
- WHEN the experiment samples findings THE SYSTEM SHALL use a bounded corpus of at most 60 real findings
  drawn from committed mctl-gitops `agents-state/*/proposals/*` triplets and `.status.yaml` notes, shepherd
  P1/P2 review comments and CI check blockers. Each finding SHALL carry a human-assigned class and, where
  known, a ground-truth label (`true_positive`, `noise`, `unlabelled`).
- WHEN a validator runs on a finding THE SYSTEM SHALL consume only bounded evidence pinned to an exact
  revision, artifact digest or state capture time, never the model's conclusion text.
- WHEN a validator reproduces a claim THE SYSTEM SHALL record `VALIDATED_FINDING` together with the
  revision, digest or capture time it checked.
- IF a validator does not reproduce a claim THEN THE SYSTEM SHALL record `NOT_REPRODUCED` and keep the
  original hypothesis visible. It SHALL record `FALSE` only when the report states why the oracle is
  complete enough to prove falsity for that class.
- IF no oracle exists for a finding's class, or the evidence read fails, is partial or times out, THEN THE
  SYSTEM SHALL record `HYPOTHESIS` (no oracle) or `UNKNOWN` (oracle inconclusive). It SHALL NOT treat
  either as evidence that the finding is false.
- WHILE any finding is evaluated THE SYSTEM SHALL keep `NOT_REPRODUCED`, `UNKNOWN` and `FALSE` distinct in
  every record, table and metric.
- WHILE the experiment runs THE SYSTEM SHALL execute no exploit payload, contact no third-party or
  production target, and grant no approval, merge or authorization from any validation result.
- WHEN measurements are reported THE SYSTEM SHALL include, per the issue:
  - precision and false-positive rate for validator-eligible classes;
  - validator coverage;
  - false negatives introduced by gating;
  - the `NOT_REPRODUCED` / inconclusive rate;
  - reviewer effort and time-to-decision with and without validation state;
  - added latency and compute or model cost;
  - the number of findings that stay hypotheses by design.
  A metric that could not be measured SHALL be marked `not-measured` with a reason, never zero.
- WHEN the report names classes that must not be gated THE SYSTEM SHALL list at least architecture/design,
  governance judgement, and incomplete requirement / ambiguous product decision. It SHALL route the last of
  these to the ADR 013 human-input contract, not to a validator.
- WHEN the report proposes a status/evidence contract THE SYSTEM SHALL express it as a mapping onto
  existing vocabularies. These are ADR 018 `AUTHORITIES` and evidence ids, ADR 022 `candidate`,
  `confirmed` and `rejected` (`not_reproducible` / `false_positive`), ADR 024 verification results, and
  `SpecVerdict`. It SHALL propose a new record only if the experiment shows a gap that none of them
  covers.
- WHEN the recommendation is written THE SYSTEM SHALL create follow-ups only for gaps the experiment
  proved, each with owner repository, control and rollback.
- WHEN `tests/test_spike_918_report.py` runs THE SYSTEM SHALL fail on any of these:
  - a malformed STATUS line;
  - a missing taxonomy class or oracle rating;
  - a validator outcome outside the closed set;
  - a corpus larger than 60 entries;
  - a `FALSE` without a completeness note;
  - a token-shaped string.

## Out of scope

- Wiring any validator into the investigator, shepherd, implementer, Temporal workflows or CWFTs.
- Requiring a deterministic validator for every investigator observation, or a generic verification
  framework.
- Treating architecture or product judgement as mechanically provable.
- Changing ADR 018, 022 or 024 contracts, mctl-api SecurityFinding routes, or anything in mctl-gitops.
- Running exploit payloads, scanning third-party or production targets, or re-running paid model
  investigations to build the corpus.
- Recording the decision. The owner records `decision.verdict` in the SpikeDefinition manifest; the PR
  uses `Refs #918`, never `Closes`.

## Open questions

- mctlhq/.github#222 (the deterministic affectedness pattern) is in another repository and was not read
  during investigation. Task 1 reads it. If it already defines an affectedness oracle record, the
  dependency/version class reuses it instead of the spike harness's lockfile check.
- Ground-truth labels for review findings are sparse. Merged and rejected proposals give coarse labels,
  but a P1 that was "fixed" is not proof that the finding was correct. The report treats such labels as
  `unlabelled` unless a human labels them. Precision may therefore be reported on a small subset only.
- Reviewer effort and time-to-decision cannot be measured live without a human study. The spike estimates
  them from PR and comment timestamps on the sampled findings and marks the figure as an estimate.
- The governance/ownership class splits into a mechanical part (the lifecycle ownership store or a
  CODEOWNERS read) and a judgement part. The proposal rates the class `BOUNDED_BUT_NONDETERMINISTIC`
  for the mechanical part and `NO_SAFE_ORACLE` for the judgement part. The owner may prefer to split it
  into two rows.
- The provisional lean is `VALIDATE_SELECTED_FINDING_CLASSES`, because the existing contracts already
  express the four validation states. The experiment may overturn it. If it shows that investigator and
  review findings have no record that can carry a revision-bound verdict, `ADD_VALIDATED_FINDING_CONTRACT`
  becomes the answer.
