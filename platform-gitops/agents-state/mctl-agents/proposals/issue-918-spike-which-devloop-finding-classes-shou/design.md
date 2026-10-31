# Design: issue-918-spike-which-devloop-finding-classes-shou

## Current state

DevLoop produces findings in several places. Only some of them already separate a model claim from an
independently reproduced one.

| Producer | Finding shape today | Validation state today |
|---|---|---|
| Issue-investigator (`orchestrator/run_issue_investigator.py`) | Free-text claims inside `requirements.md` / `design.md` / `tasks.md`. `_landed_triplet_defects` checks only that the triplet files exist and are well-formed. The prompt asks for a `Deployed state checked:` list and says "could not observe is never observed absent" (`_deployed_state_grounding_block`), but nothing checks it mechanically. `_target_repository_sha` pins the clone HEAD. | None. Every claim is effectively a hypothesis with no label. |
| Shepherd review (`orchestrator/run_shepherd.py`) | `CodexFinding`: body, path, line, `commit_id`, severity `P1`/`P2` from `_extract_severity`. `findings_p1_p2(at)` and `fresh_findings_p1_p2` anchor findings to the head SHA. | Anchored to a revision, but never reproduced. A P1 blocks on the reviewer's word. |
| CI (`orchestrator/ci_checks.py`) | `CheckBlocker` / `CIStatus`. The `Blockers` docstring forbids coercing a check failure into a review finding. | Deterministic by construction: the check ran at the head SHA. Flaky checks are the exception. |
| Implementer refusals (`.status.yaml` `notes`) | Model text, for example the issue-875 proposal note "Failure is not reproducible and not caused by this PR". | None. This is a model asserting `NOT_REPRODUCED` with no oracle record. |
| Spec verification (`orchestrator/sdd/verify.py`) | `SpecVerdict(outcome in pass/fail/unknown)`, explicitly "no merge, approve or authorize affordance". | Deterministic, with a three-valued result that already keeps `unknown` distinct. |
| Runtime assurance (ADR 022, `orchestrator/runtime_assurance.py`) | `AssuranceFinding` `candidate -> confirmed` only via `transition_finding` with a replay run. `rejected` carries a disposition from `false_positive`, `not_reproducible`, `duplicate`, `out_of_scope`. A model-`asserted` finding is never `confirmed` without validation. `ObservationRef` status `observation_failed` / `partial` maps to `unknown`, never to absence. | This is already the hypothesis/validated split the issue asks about, for scenario-bound runtime findings. |
| SecurityFinding (ADR 024, `orchestrator/security_findings/`, `run_security_verifier.py`) | mctl-api owns state. Mechanisms are listed in `vocabulary.json`: `deterministic_regression_test` > `assurance_replay` > `scanner_rerun_exact_revision` > `provider_claim` > `manual`. Results: `passed`, `failed`, `unavailable`, `error`, `timeout`, `unverifiable`. "Merge is not resolution." `locally_bound` drops outcomes for any other revision. | Validated per exact revision. Transient results are kept separate from `unverifiable`. |
| Evidence (ADR 018, `orchestrator/execution_evidence.py`) | `AUTHORITIES = ("observed", "derived", "asserted")`, `AUTHORITY_RANK`, `ev-` evidence ids, `OUTCOME_CODES`. | The generic grading that any validator verdict can be expressed in. |

Related spikes:
- `docs/spikes/875-gh-aw-guardrail-comparison.md` adopted only S2 (output limiter, #879) and P3. Its row
  T1 (a pre-publish threat detection scan) is `not-observed`. This spike does not re-open T1.
- `docs/spikes/796-rea-investigation-evidence.md` is the precedent for fixture-based oracle scoring.
- Previous spike reports follow a common shape: a `STATUS:` line, tables, and a guard test such as
  `tests/test_spike_875_report.py` or `tests/test_spike_852_report.py`. Experiment code lives under
  `tools/` (for example `tools/semantic_decision_spike.py`) and data under `docs/spikes/<n>/`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/` (read-only checkout): 145 proposal
  directories. `.status.yaml` statuses: 94 merged, 26 accepted, 11 rejected, 8 proposed, 6 needs-triage.
  This is the sampling corpus for investigator findings. The rejected and needs-triage entries
  (`issue-778-...`, `issue-404-...`, `incident-17840763` and others) are candidate "noise" examples.
- `.../proposals/issue-875-.../.status.yaml` `notes`: the implementer-refusal text quoted in the table
  above. It is a real example of a model-asserted `NOT_REPRODUCED` with no oracle.
- `$MCTL_GITOPS_ROOT/services/` lists the tenants `admins`, `karabu`, `labs` and `namax66`. This spike
  changes no service config, so no service values were read.
- mctl MCP tools: not called. The spike touches no deployed service, tenant or runtime setting, so no
  deployed-state claim depends on them.
- mctlhq/.github#222: not observed. It is in another repository and was not retrievable from this clone.
  It is recorded under Open questions.

## Proposed solution

A docs-and-offline-harness spike modelled on #796 and #875. Nothing is wired into DevLoop.

1. **Taxonomy and oracle map.** The report `docs/spikes/918-finding-oracle-classes.md` has one row per
   class. Each row has these columns:
   - `class`;
   - `oracle` (`DETERMINISTIC | BOUNDED_BUT_NONDETERMINISTIC | NO_SAFE_ORACLE`);
   - `existing_oracle` (the module or contract, or `none`);
   - `evidence_consumed`;
   - `binding` (revision, digest or capture time);
   - `falsity_provable` (yes/no and why);
   - `gate_allowed` (yes/no).

   The initial ratings below are hypotheses the experiment confirms or overturns:

   | class | provisional oracle | existing oracle to reuse | binding |
   |---|---|---|---|
   | runtime/test failure | DETERMINISTIC. Downgraded to BOUNDED_BUT_NONDETERMINISTIC when a rerun at the same SHA disagrees (flaky). | `ci_checks.CIStatus` at head SHA; a local `uv run pytest <nodeid>` at the pinned SHA | head SHA |
   | static invariant / schema | DETERMINISTIC | `orchestrator/validate_manifest.py`, `sdd/verify.py`, `tools/check_*.py`, `runtime_assurance` parsers | revision |
   | security with safe local oracle | DETERMINISTIC only via ADR 024 mechanisms, otherwise NO_SAFE_ORACLE | `security_findings.verification` (regression test, assurance replay, scanner rerun) | exact revision / digest |
   | dependency / version affectedness | DETERMINISTIC | lockfile (`uv.lock`) at pinned SHA against a declared affected range; .github#222 pattern if it fits | revision + advisory id |
   | stale factual premise | DETERMINISTIC for GitHub state (`source_issue.py`, `spike_issue.py`) and for file or symbol existence at `_target_repository_sha`; BOUNDED_BUT_NONDETERMINISTIC for live cluster state (mctl read tools, time-varying) | as listed | SHA or capture time |
   | architecture / design | NO_SAFE_ORACLE | none | - |
   | governance / ownership | BOUNDED_BUT_NONDETERMINISTIC (store or CODEOWNERS read) for the mechanical part, NO_SAFE_ORACLE for the judgement part | `mctl_get_lifecycle_ownership` read, CODEOWNERS | capture time |
   | incomplete requirement / ambiguous decision | NO_SAFE_ORACLE. Routed to ADR 013 human input. | `orchestrator/human_input.py` | - |

2. **Corpus.** `docs/spikes/918/corpus.yaml` holds at most 60 findings. Each entry has:
   - `id`;
   - `source` (proposal path, PR comment URL, or check run id);
   - `revision`;
   - a quoted claim, bounded to 300 characters and passed through `redaction.redact_text` rules;
   - a human-assigned `class`;
   - `ground_truth` (`true_positive | noise | unlabelled`) and `label_basis`.

   Sources:
   - investigator claims from merged, rejected and needs-triage proposals;
   - shepherd P1/P2 review comments on recent mctl-agents PRs;
   - CI blockers;
   - implementer refusal notes.

   Evidence the validators consume is captured once into `docs/spikes/918/evidence/` as small JSON files:
   - issue and PR state;
   - file and symbol listings at the SHA;
   - lockfile excerpts;
   - check-run conclusions.

   Each capture carries `captured_at` and its SHA, so the experiment replays offline and deterministically.

3. **Smallest independent validators.** `tools/spike_918_finding_oracles.py` is stdlib-only plus the
   repo's existing parsers. It has one function per DETERMINISTIC class, and each function takes
   `(claim_structured_fields, evidence)`. A validator reads the structured target of the claim (path,
   symbol, issue number, package, test node id, revision), never the model's conclusion text. Each
   validator returns one of these outcomes:
   - `VALIDATED_FINDING`: the oracle reproduced the claim.
   - `NOT_REPRODUCED`: the oracle ran and did not reproduce the claim. The hypothesis is kept.
   - `FALSE`: allowed only for classes whose row says `falsity_provable: yes`, for example "the issue is
     closed" checked against canonical GitHub state.
   - `UNKNOWN`: the evidence read failed, was partial or timed out.
   - `HYPOTHESIS`: no oracle exists for the class.

   The harness runs no exploit payload, has no network access in its test mode, and its output has no
   field that grants, approves or merges anything. This follows the field-name scan rule of ADR 022.

4. **Before/after comparison.** The "before" arm is today's flat reporting: every finding is actionable.
   The "after" arm is the two-level output. The harness computes:
   - precision and FPR on validator-eligible labelled findings, for both arms;
   - coverage, the share of findings in a DETERMINISTIC class;
   - false negatives from gating, meaning `true_positive` findings that the after arm left at
     `NOT_REPRODUCED` or `UNKNOWN`;
   - the `NOT_REPRODUCED` and `UNKNOWN` rates;
   - harness wall time per finding, and model cost, which is 0 because the validators are not model
     calls;
   - the count of findings that stay `HYPOTHESIS` by design.

   Reviewer time-to-decision is estimated from PR and comment timestamps and marked `estimate`.

5. **Status/evidence contract, as a mapping only.** The report maps the five outcomes onto existing
   vocabularies:

   | Spike outcome | ADR 018 | ADR 022 | ADR 024 | `SpecVerdict` |
   |---|---|---|---|---|
   | `VALIDATED_FINDING` | `observed` evidence with an `ev-` id | `confirmed` | `passed`/`failed` per direction | `fail` (the claimed violation holds) |
   | `NOT_REPRODUCED` | - | `rejected` + `not_reproducible` | - | - |
   | `FALSE` | - | `rejected` + `false_positive` | - | - |
   | `UNKNOWN` | - | - | `unavailable`/`error`/`timeout` | `unknown` |
   | `HYPOTHESIS` | `asserted` | `candidate` | - | - |

   A new record is proposed only if a row has no carrier. The expected gap is that investigator and
   shepherd findings have no record at all on which to attach a verdict. The report must decide whether
   ADR 018 evidence covers that gap, which gives `VALIDATE_SELECTED_FINDING_CLASSES`, or whether it needs
   a new contract, which gives `ADD_VALIDATED_FINDING_CONTRACT`.

6. **Classes that must not be gated.** The report states explicitly that these classes are never hidden
   behind a deterministic gate and stay visible as `HYPOTHESIS`:
   - architecture/design;
   - governance judgement;
   - incomplete requirement / ambiguous product decision;
   - any security finding without a safe local oracle;
   - the live-cluster part of stale-premise claims.

7. **Recommendation.** The report gives exactly one outcome token and `STATUS: DRAFT` until the owner
   records `decision.verdict`. The provisional lean is `VALIDATE_SELECTED_FINDING_CLASSES`. Follow-ups
   cover only proven gaps. A likely candidate is labelling investigator stale-premise claims with a
   revision-bound oracle result as ADR 018 evidence. Each follow-up names an owner repository, a control
   and a rollback.

## Alternatives

- **Universal validator gate.** Require an oracle for every finding before it is actionable. Rejected
  because the issue explicitly excludes it. It would hide architecture, governance and requirement
  findings, which by definition have no oracle, and it would treat the absence of a validator as
  falsity.
- **New generic `ValidatedFinding` lifecycle now.** Rejected for the spike: ADR 022 and ADR 024 already
  model candidate, confirmed, not_reproducible and transient results. A third lifecycle would duplicate
  them. It stays possible as the `ADD_VALIDATED_FINDING_CONTRACT` outcome only if the experiment proves
  the gap.
- **Model self-verification ("re-ask the model whether its claim holds").** Rejected because it violates
  the invariant that model judgement alone cannot mark a mechanically verifiable claim as validated. It
  also adds model cost.
- **Live experiment that re-runs investigations.** Rejected because it costs about $3 per investigation
  and is non-reproducible. Captured evidence keeps the experiment offline and deterministic, as in #796.

## Platform impact

- **Migrations:** none.
- **Backward compatibility:** unaffected. The change is additive docs, a fixture corpus, an offline tool
  and a guard test. No orchestrator, Temporal, CWFT, profile or mctl-api change.
- **Resource impact:** CI runs one more pytest file over fixtures, which takes seconds. Building the
  corpus uses read-only `gh api` calls by the implementer. No model spend beyond the implementer run.
- **Risks and mitigations:**
  - *Quoted findings leak secrets or untrusted instructions.* Claims are bounded to 300 characters and
    passed through `redaction.redact_text` semantics. The guard test scans for token shapes. Quoted text
    is data, and the harness never interprets it.
  - *Labels are biased: "merged" read as "correct".* `label_basis` is required, and unlabelled findings
    are excluded from precision. The report states the labelled subset size.
  - *A validator over-claims falsity.* `FALSE` is allowed only where the row says `falsity_provable: yes`,
    and the guard test enforces this.
  - *The validation result is read as approval.* The harness output has no authority-word fields, and the
    report restates that validation never grants approval, merge or authorization.
  - *Unsafe validation.* No exploit payloads, no third-party or production targets, and no network in
    test mode.
