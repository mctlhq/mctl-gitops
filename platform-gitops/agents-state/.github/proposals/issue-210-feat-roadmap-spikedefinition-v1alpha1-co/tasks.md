# Tasks: issue-210-feat-roadmap-spikedefinition-v1alpha1-co

- [ ] 1. Add `roadmap/schemas/common.schema.json` (`$id`
  `https://mctl.ai/schemas/roadmap/common-v1alpha1.json`) with `$defs.issueRef`,
  `$defs.localId`, `$defs.name`, copied from `epic-definition.schema.json`; turn the
  epic schema's `$defs.issueRef` / `$defs.localId` into `$ref` wrappers to the
  common `$id`. — DoD: both pass `Draft202012Validator.check_schema`; the epic
  schema's other content is unchanged.
- [ ] 2. In `roadmap/scripts/validate.py`, build `SCHEMA_REGISTRY` (a
  `referencing.Registry` of every `roadmap/schemas/*.schema.json` keyed by `$id`)
  and pass `registry=SCHEMA_REGISTRY` in `schema_errors` (depends on 1). — DoD: the
  whole existing `roadmap/tests` suite and `validate.py roadmap/epics` are green
  with no message changes.
- [ ] 3. Add `roadmap/schemas/spike-definition.schema.json` per design section 2
  (fields, `outcomes` minItems 2 / unique / UPPER_SNAKE, `date` def, relative
  `evidence.report`, `allOf` if/then for parked/active/decided/not-decided,
  `additionalProperties: false` throughout) (depends on 1). — DoD: `check_schema`
  passes; the issue's example manifest (with dates) validates.
- [ ] 4. Normalise `datetime.date` values to ISO strings in
  `validate._load_manifest` (recursive; `datetime.datetime` untouched). — DoD:
  quoted and unquoted dates load identically; epic loads unchanged.
- [ ] 5. Add kind dispatch and spike semantics to `validate.py`: `SPIKE_SCHEMA`,
  `DEFAULT_SPIKES`, `KINDS`, `kind_error`, `spike_semantic_errors` (verdict in
  outcomes, calendar dates, followUps dedupe/self-reference),
  `validate_spike_document`, `validate_manifest` (depends on 2, 3, 4). — DoD:
  `validate_document` / `semantic_errors` unchanged; unknown kind yields a `$.kind:`
  message.
- [ ] 6. Extend `corpus_errors` to partition by kind and add
  `_spike_corpus_errors` (spike name uniqueness, one SpikeDefinition per issue,
  spike issue not an epic root, epic-work-item binding must be declared as
  `spec.epic`, declared `spec.epic` must resolve to an existing epic, work item, and
  the same issue; "epic failed validation" message when applicable) (depends on 5).
  — DoD: epics-only input gives byte-identical output to today.
- [ ] 7. Update `validate.main`: default paths epics + spikes, `--spike-schema`,
  per-kind schema selection, "no roadmap manifests found", docstring (depends on 5,
  6). — DoD: exit codes 0/1/2 preserved; `--schema` still overrides the epic schema.
- [ ] 8. Author the five pilots in `roadmap/spikes/` (`portable-runtime.yaml`,
  `agent-scale-coordination.yaml`, `duet-sessions.yaml`,
  `security-finding-lifecycle.yaml`, `openspec-contract.yaml`) per design section 5,
  quoting dates, taking unstated outcomes/dates from each issue body, and listing
  every value the issue did not give in the PR description for owner confirmation
  (depends on 3). — DoD: `python roadmap/scripts/validate.py roadmap/epics
  roadmap/spikes` exits 0 with ten-plus `PASS` lines and five spike `PASS` lines.
- [ ] 9. Add pure manifest mutators for spikes in a separate section of
  `roadmap/tests/mutations.py` (deep-copy, no snapshot mutators for slice-2 diff
  types). — DoD: each returns a new object; original untouched.
- [ ] 10. Update `roadmap/README.md` (Layout, Validation command, new
  "SpikeDefinition v1alpha1" section incl. lifecycle meanings, rules, cross-kind
  invariants, date handling, slice-2 pointer) and
  `.github/workflows/roadmap-validate.yml` (validate `roadmap/epics roadmap/spikes`
  in one step). — DoD: README commands run as written; workflow green on the PR.
- [ ] 11. Red-proof: for each new test, temporarily remove the corresponding check
  (schema conditional, semantic rule or corpus rule), run it, and record the red
  run in the PR description; restore. — DoD: PR lists every test with its removed
  check and the observed failure.

## Tests

All in `roadmap/tests/test_validate_spike.py` unless noted; each asserts the exact
message and JSON path.

- [ ] T1. Minimal valid spike and the issue's example manifest validate with `[]`.
- [ ] T2. `decision.verdict` outside `outcomes` -> `$.spec.decision.verdict: ...`.
- [ ] T3. `lifecycle: decided` without `decision` fails at `$.spec`.
- [ ] T4. `decision` present with `lifecycle` `active` and with `archived` fails.
- [ ] T5. `parked` without `activation`, and with `activation` lacking `trigger`, fail.
- [ ] T6. `active` without `timebox`, and with `timebox` lacking `decisionBy`, fail.
- [ ] T7. Duplicate outcome, single outcome, lower-case outcome fail.
- [ ] T8. Unquoted YAML date loads and validates; `2026-02-30` fails as not a
  calendar date; a datetime value fails the date pattern.
- [ ] T9. Undeclared observed field (`spec.state`, `spec.prs`) is rejected.
- [ ] T10. `evidence.report` absolute or with `..` fails.
- [ ] T11. `followUps` duplicate (case-differing repository) and self-reference fail.
- [ ] T12. Unknown / missing `kind` fails with `$.kind:`.
- [ ] T13. Corpus: `spec.epic` resolving correctly passes; unknown epic, unknown
  work item, unbound work item, and work item bound to a different issue each fail
  with their own message (epic binding on a different issue).
- [ ] T14. Corpus: spike issue bound as an epic work item with no `spec.epic`, or a
  `spec.epic` naming a different pair, fails (duplicate binding across kinds).
- [ ] T15. Corpus: two spikes binding the same issue (case-differing repository)
  fail both; two spikes with one `metadata.name` fail both; spike issue equal to an
  epic root issue fails.
- [ ] T16. Corpus: referenced epic manifest invalid -> "failed validation" message,
  not "unknown epic".
- [ ] T17. Regression: `corpus_errors` on epics-only input yields exactly the
  pre-change messages; all current `roadmap/epics` manifests pass.
- [ ] T18. Every file in `roadmap/spikes/` validates together with `roadmap/epics/`;
  the decided pilot has `verdict: ADAPTER_ONLY`.
- [ ] T19. CLI: `validate.main([epics, spikes])` returns 0; each mutator from task 9
  applied to a temp copy returns 1 with `FAIL <path>` and the precise message, and
  restoring returns 0; `--spike-schema` with an unreadable file returns 2;
  `main([])` validates both default directories.
- [ ] T20. Existing `test_validate.py`, `test_reconcile.py`, `test_plan.py`,
  `test_apply.py`, `test_publish.py`, `test_ready.py`, `test_health.py`,
  `test_completion.py`, `test_publication_freshness.py` pass unchanged.

## Rollback

The change is additive and offline. Revert the PR: removing `roadmap/spikes/`,
`spike-definition.schema.json`, `common.schema.json`, the `validate.py` changes,
the new tests, README section and the workflow line restores the epic-only
validator exactly. If only the shared-schema extraction causes trouble (for
example an external standalone consumer of `epic-definition.schema.json`), restore
the epic schema's inline `$defs` and point the spike schema at the epic `$id`
(design Alternative 1); nothing else depends on `common.schema.json`. No published
artifact, GitHub state or deployed service is touched, so there is nothing to
clean up outside the repository.
