# Tasks: issue-504-feat-usage-populate-devloop-stage-with-t

- [ ] 1. Add the closed vocabulary to `orchestrator/usage_ledger.py`: module
      constants `STAGE_INVESTIGATOR`/`STAGE_IMPLEMENTER`/`STAGE_REVIEWER`/
      `STAGE_SHEPHERD`, `DEVLOOP_STAGES` (frozenset of the four), and
      `_AGENT_STAGES` mapping the ledger agent names `investigator`,
      `implementer`, `shepherd` to their stage — placed next to `_AGENT_NAMES`
      with a comment naming mctlhq/.github#50 owner decision 2 and stating that
      `reviewer` is produced by the collector (mctlhq/.github#126), not here.
      — DoD: constants exist, no behaviour change yet, `uv run ruff check
      orchestrator` and `uv run mypy` clean.

- [ ] 2. Clamp the field in `_checked_correlation` (depends on 1): drop
      `devloop_stage` with the existing `drop(...)` warning whenever the value
      is not in `DEVLOOP_STAGES` (covers non-strings, wrong case, free text,
      empty). — DoD: an out-of-vocabulary value never reaches the POST body and
      logs exactly one warning; the four valid values pass through.

- [ ] 3. Default the field per agent in `UsageRecorder.__init__` (depends on
      1, 2): after `self._correlation = _checked_correlation(...)`, set
      `devloop_stage` from `_AGENT_STAGES.get(self.agent)` only when the key is
      absent and a stage exists. — DoD: every record built by `_plan` for
      `investigator`/`implementer`/`shepherd` carries the stage; an agent absent
      from `_AGENT_STAGES` carries no `devloop_stage` key at all; `_plan`,
      `_commit`, `_deliver`, `records_for`, `_seen` and `_baseline` are not
      edited.

- [ ] 4. Add an optional `devloop_stage: str | None = None` keyword to
      `usage_ledger.work_correlation` that is included in the returned dict when
      truthy, with no validation there (depends on 1) — DoD: existing callers
      are unaffected (the parameter is keyword-only with a `None` default) and
      the docstring points at `_checked_correlation` as the single gate.

- [ ] 5. Thread the stage through `run_implementer._usage_correlation` (depends
      on 4): add a `devloop_stage: str | None = None` keyword forwarded to
      `work_correlation`. — DoD: signature and docstring updated; both existing
      call sites still type-check.

- [ ] 6. Mark the shepherd-owned implementer run (depends on 5): in
      `run_implementer.review_feedback_one`, pass
      `devloop_stage=usage_ledger.STAGE_SHEPHERD` to the `_usage_correlation`
      call inside the `usage_ledger.correlate(...)` block
      (`orchestrator/run_implementer.py` ~2726), with a comment explaining that
      the remediation cost belongs to the stage that ordered it while `agent`
      still names the binary that spent it. — DoD: a review-feedback run's
      records carry `agent=implementer` and `devloop_stage=shepherd`; the
      first-pass `implement_one` call site (~4114) is left untouched and relies
      on the `_AGENT_STAGES` default.

- [ ] 7. Confirm no other producer site needs an explicit stage (depends on 3):
      re-grep `tracing.agent_run(` and assert the three call sites
      (`run_issue_investigator.py:1654`, `run_implementer.py:2421`,
      `run_shepherd.py:2127`) are the complete set, and that
      `run_service_agent.py`, `run_mentor.py`, `run_incident_responder.py` still
      contain no `tracing.` reference. — DoD: findings recorded in the PR
      description; no code change if the grep matches the design.

- [ ] 8. Amend `docs/adr/012-model-usage-cost-attribution-contract.md` (depends
      on 3, 6): add a subsection to the 2026-09-24 producer amendment recording
      the closed v1 vocabulary, the per-agent default table, the
      review-feedback rule (`agent=implementer` + `devloop_stage=shepherd`), the
      omit-with-a-warning rule for anything outside the vocabulary, and that
      `reviewer` comes from the collector (mctlhq/.github#126). Add testable
      invariants 10 and 11 as stated in design.md. — DoD: the ADR states the
      vocabulary and matches the code exactly; `devloop_stage` at line ~147 of
      the record block is no longer an unpopulated field.

- [ ] 9. Update the two exact-equality scope assertions broken by the new field
      (depends on 6): `tests/test_usage_correlation.py`
      `test_a_review_fix_names_its_pr` (~line 333) and
      `test_the_shepherd_names_the_pr_its_issue_and_its_tick` (~line 374). —
      DoD: they assert the new `devloop_stage` explicitly rather than loosening
      the comparison; full suite green.

## Tests

- [ ] T1. `tests/test_usage_ledger.py`: the investigator's records carry
      `devloop_stage=investigator` — driven through `_run_investigator_agent`
      with tracing off, in the style of
      `test_each_sdk_driver_records_its_usage_with_tracing_off`, asserting
      `(record["agent"], record["devloop_stage"]) == ("investigator",
      "investigator")`.
- [ ] T2. Same test module: a first-pass implementer run records
      `devloop_stage=implementer` alongside `agent=implementer` (extend the
      existing parametrised driver test rather than adding a third path).
- [ ] T3. Same test module: the shepherd's own normalising call records
      `devloop_stage=shepherd` — extend
      `test_the_shepherd_records_the_usage_of_its_normalising_call`.
- [ ] T4. `tests/test_usage_correlation.py`: a review-feedback run records
      `agent=implementer` with `devloop_stage=shepherd` — drive
      `run_implementer.review_feedback_one` with the existing
      `_probe_anyio_run` harness (as `test_a_review_fix_names_its_pr` does) and
      assert the scope carries `devloop_stage: "shepherd"`; plus one
      record-level assertion through `_recorder(api, "implementer",
      devloop_stage="shepherd")` that the POSTed record has
      `agent=implementer` and `devloop_stage=shepherd`.
- [ ] T5. `tests/test_usage_ledger.py`: an out-of-vocabulary stage is dropped
      with a warning and never POSTed — parametrised over `"reviewing"`,
      `"Shepherd"`, `""`, `42`, `None`, extending the existing
      `test_a_value_the_server_would_reject_is_not_sent` style (`caplog`
      asserted, record key absent).
- [ ] T6. `tests/test_usage_ledger.py`: a `_recorder(api, "mentor")` — an agent
      with no entry in `_AGENT_STAGES` — produces a record with no
      `devloop_stage` key at all (absent, not empty, not guessed).
- [ ] T7. `tests/test_usage_ledger.py`: precedence — an explicit
      `devloop_stage` argument wins over a `correlate` scope, and the scope wins
      over the per-agent default (mirrors
      `test_explicit_correlation_wins_over_the_scope_and_the_scope_over_the_environment`).
- [ ] T8. `tests/test_usage_ledger.py`: adding the stage changes no identity or
      counter — a two-turn session still produces per-turn deltas and the same
      `(session_id, result_uuid, model_key)` identity on redelivery (assert the
      existing `test_a_redelivered_batch_is_byte_for_byte_the_same_identity` and
      `test_cumulative_session_counters_are_recorded_as_per_turn_deltas` still
      pass unmodified).
- [ ] T9. A vocabulary-closure test: `usage_ledger.DEVLOOP_STAGES ==
      frozenset({"investigator", "implementer", "reviewer", "shepherd"})` and
      every value of `_AGENT_STAGES` is a member — so widening the vocabulary
      cannot happen by accident without touching a test that names the contract.
- [ ] T10. Full gate: `uv run pytest tests/`, `uv run ruff check orchestrator
      config tests`, `uv run mypy` all clean (per CONTRIBUTING.md and
      `.github/workflows/pr-validation.yml`).

## Rollback

The change is additive and confined to one field on an outbound bookkeeping
record, so rollback is a plain revert of the PR — there is no state to undo: no
migration, no GitOps state file, no `.status.yaml` field, and no change to
dedupe keys or delta baselines, so already-ingested rows stay valid and are
simply the last ones carrying (or not carrying) the stage.

Two narrower escape hatches if a revert is not desirable mid-incident:

1. If mctl-api turns out to reject the field and whole batches start failing
   (visible as the `usage records not delivered (...)` warning with a rising
   undelivered count in the runners' logs), delete the default-filling block in
   `UsageRecorder.__init__` and the `review_feedback_one` argument. Records then
   go back to exactly today's shape; no other code path depends on the field.
2. If only the review-feedback attribution is disputed, revert task 6 alone —
   the shepherd's forked implementer run falls back to
   `devloop_stage=implementer` via the default, which is the pre-change
   (indistinguishable) behaviour without losing the other three stages.

In all cases, unsetting `MCTL_USAGE_WRITER_TOKEN` remains the existing
kill switch for the producer as a whole: recording turns off with one warning and
no DevLoop behaviour changes.
