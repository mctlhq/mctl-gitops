# Tasks: issue-918-spike-which-devloop-finding-classes-shou

- [ ] 1. Read the reuse sources:
  - mctlhq/.github#222 (the deterministic affectedness pattern) and mctl-agents#875 / #848;
  - `docs/adr/018-execution-evidence-envelope-contract.md`, `docs/adr/022-runtime-assurance-contract.md`
    and `docs/adr/024-security-finding-remediation-runner.md`;
  - `orchestrator/sdd/verify.py`, `orchestrator/ci_checks.py`, `orchestrator/source_issue.py`,
    `orchestrator/spike_issue.py`, and `CodexFinding` in `orchestrator/run_shepherd.py`.

  Record what was read, and what was not. — DoD: the report's `## Sources and limits` section lists each
  source as `read` or `not-observed`. Every existing-oracle cell cites a path and a symbol.
- [ ] 2. (depends on 1) Write the taxonomy and oracle-map table in
  `docs/spikes/918-finding-oracle-classes.md`, starting with `STATUS: DRAFT`. Each of the 8 classes gets:
  - `oracle`;
  - `existing_oracle`;
  - `evidence_consumed`;
  - `binding`;
  - `falsity_provable`;
  - `gate_allowed`.

  — DoD: all 8 issue classes are present, and each has exactly one rating from
  `DETERMINISTIC | BOUNDED_BUT_NONDETERMINISTIC | NO_SAFE_ORACLE`.
- [ ] 3. (depends on 2) Build `docs/spikes/918/corpus.yaml` with at most 60 real findings from:
  - mctl-gitops `agents-state/*/proposals/*`: merged, rejected and needs-triage triplets, plus
    `.status.yaml` `notes`;
  - shepherd P1/P2 comments on recent mctl-agents PRs;
  - CI blockers.

  Each entry needs `class`, `ground_truth` and `label_basis`. Claims are bounded to 300 characters and
  redacted. Capture the evidence once into `docs/spikes/918/evidence/*.json` with `captured_at` and the
  SHA. — DoD: every class has at least 3 findings where available, or a stated shortfall. No
  token-shaped strings.
- [ ] 4. (depends on 2) Implement `tools/spike_918_finding_oracles.py` with one validator per
  DETERMINISTIC class:
  - test/check rerun result at SHA;
  - schema/invariant via existing parsers;
  - lockfile affectedness;
  - stale premise from issue/PR state and file/symbol existence at SHA.

  Validators consume structured claim fields plus captured evidence, never conclusion text. Outcomes are
  `VALIDATED_FINDING | NOT_REPRODUCED | FALSE | UNKNOWN | HYPOTHESIS`. There is no network in fixture
  mode and no exploit execution. — DoD: the tool runs offline over the corpus and emits one JSON line per
  finding, including the binding it checked.
- [ ] 5. (depends on 3, 4) Run the before/after comparison and write `docs/spikes/918/results.json`
  plus the report's metrics table:
  - precision and FPR for both arms (labelled eligible subset);
  - coverage;
  - false negatives from gating;
  - the NOT_REPRODUCED and UNKNOWN rates;
  - harness latency and cost;
  - the count of findings that stay HYPOTHESIS by design;
  - reviewer time-to-decision as an `estimate`.

  — DoD: every metric is a number or `not-measured` with a reason. None is silently zero.
- [ ] 6. (depends on 5) Write the mapping-only status/evidence contract section. It maps the five outcomes
  onto ADR 018 `AUTHORITIES`, ADR 022 `candidate`/`confirmed`/`rejected` dispositions, ADR 024 results,
  and `SpecVerdict`. Name any outcome that has no carrier. — DoD: every outcome row has a carrier or an
  explicit `gap`.
- [ ] 7. (depends on 5, 6) Write the sections "Classes never gated", "Invariants" and
  "Recommendation". The recommendation is exactly one outcome token, provisionally
  `VALIDATE_SELECTED_FINDING_CLASSES` unless the data says otherwise. Add follow-ups only for proven gaps,
  each with owner repository, control and rollback. `STATUS` stays `DRAFT`. — DoD: the sections are
  present, and the invariants restate all six issue invariants.
- [ ] 8. (depends on 2-7) Add `tests/test_spike_918_report.py`, modelled on
  `tests/test_spike_875_report.py`, plus validator unit tests. Open the PR with `Refs #918` (never
  `Closes`). — DoD: `uv run pytest tests/test_spike_918_report.py` passes and CI is green.

## Tests

- [ ] T1. The report has exactly one `STATUS:` line. Its value is in {`DRAFT`, `NO_GENERIC_GATE`,
  `VALIDATE_SELECTED_FINDING_CLASSES`, `ADD_VALIDATED_FINDING_CONTRACT`}.
- [ ] T2. All 8 taxonomy classes are present, each with an oracle rating from the closed set and a
  non-empty `existing_oracle` cell (`none` allowed).
- [ ] T3. The corpus has at most 60 entries. Each entry has `class`, `ground_truth` in
  {`true_positive`, `noise`, `unlabelled`} and a non-empty `label_basis`.
- [ ] T4. Every result outcome is in the closed set of five. A `FALSE` appears only for a class whose
  row has `falsity_provable: yes`. A `VALIDATED_FINDING` always carries a revision, digest or
  `captured_at`.
- [ ] T5. The validators are independent of conclusion text: changing a finding's free-text claim while
  keeping its structured fields and evidence leaves the outcome unchanged.
- [ ] T6. Failed, partial or missing evidence yields `UNKNOWN`, never `FALSE` or `NOT_REPRODUCED`. A
  finding of a `NO_SAFE_ORACLE` class yields `HYPOTHESIS`.
- [ ] T7. The harness output has no field name containing `approve`, `allow`, `grant`, `permit` or
  `authorized`. The harness makes no network call in fixture mode (socket patched to raise).
- [ ] T8. The metrics table has every issue measurement, each as a value or `not-measured` with a reason.
- [ ] T9. No token-shaped strings (`ghp_`, `gho_`, `github_pat_`, `sk-ant-`, `-----BEGIN`) appear in the
  report, the corpus or the evidence.

## Rollback

The change is docs, fixtures, an offline tool and tests only. Reverting the PR removes the report,
`docs/spikes/918/`, `tools/spike_918_finding_oracles.py` and the tests. No runtime, Temporal, gitops,
profile or mctl-api state changes. Follow-up issues filed from the report can be closed independently.
