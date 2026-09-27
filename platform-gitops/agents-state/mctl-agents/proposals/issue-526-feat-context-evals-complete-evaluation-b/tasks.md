# Tasks: issue-526-feat-context-evals-complete-evaluation-b

> **Correction 2026-09-27 (after #472 Slice A, mctlhq/mctl-agents#530).**
> Two things this proposal defined are now owned elsewhere on `main`:
> (1) the implementation identity of a strategy version is #472's catalog
> `contentHash`/`implementationHash` (`config/context-strategies/`,
> `orchestrator/context_release.py`, ADR 019), and evidence must carry it so
> #528 can match it exactly; (2) the freshness window (7 days) and minimum
> consecutive observations (3) are ADR 019's **v1 promotion policy
> constants**, changed only by amending ADR 019 — so this evaluator takes them
> as parameters and reads no env var for them. `assess_evidence` reports a
> status; the promotion decision is #528's.

- [ ] 1. Add `StoreRef` and `store_ref_from(snapshot, answer)` to
  `orchestrator/work_context/snapshots.py`, reusing the existing
  `_is_snapshot_id` TypeGuard for the `cs_` prefix check — DoD: frozen
  dataclass with `to_dict`/`from_dict` in the `execution_evidence.py` style;
  `store_ref_from` returns `None` unless `answer.stored` and the reported
  `snapshot_id` is `cs_`-prefixed; no field can hold a document, payload,
  locator or selector; module stays stdlib-only.

- [ ] 2. Return the persist answer and expose the ref (depends on 1) — DoD:
  `context_assembly._persist_to_work_item_store` is annotated
  `-> SnapshotAnswer | None` and returns the answer; its `SnapshotNotPersisted`
  raise conditions and `_emit_snapshot_answer` call are unchanged;
  `AssemblyResult` gains `store_ref: StoreRef | None = None` as a defaulted
  final field; `assemble_investigator_context` returns
  `dataclasses.replace(result, store_ref=store_ref_from(...))` when an answer
  exists; the `StoreRef` annotation is imported under `TYPE_CHECKING`; existing
  `AssemblyResult` constructions compile untouched.

- [ ] 3. Add `orchestrator/context_eval.py` with the identity layer (depends on
  1) — DoD: module imports only stdlib plus `context_snapshot` and
  `work_context.snapshots`; no `os.getenv`, no network, no filesystem, no clock
  read; `verify_identity(snapshot, store_ref=None)` checks
  `recompute_content_hash(snapshot) == snapshot.content_hash`, then
  `snapshot.snapshot_id == "cs-" + snapshot.content_hash[7:23]`, then the store
  hash when a ref is present; `store_snapshot_id` is compared, never
  recomputed; returns an `IdentityCheck` naming the two disagreeing fields.

- [ ] 4. Add the metric layer to `context_eval.py` (depends on 3) — DoD:
  `EvalMetrics`, `CoverageEntry`, `CaseLabels`, `EvidenceIdentity`,
  `EvalRecord`, and `evaluate(...) -> EvalRecord` implementing exactly ADR 015
  sec. 2's table; unlabelled cases report `selected_precision`/`useful_recall`/
  `f1` as `null`; `stale_rate` counts `freshness.staleness == "stale"` OR
  `selection.reason_code == "stale-demoted"`; conflict metrics read
  `snapshot.conflicts` only; `context_tokens_estimate` is
  `ceil(used_bytes / 4)` and named an estimate; a failed identity yields
  `verdict: "hash-mismatch"` with `metrics=None`.

- [ ] 5. Add telemetry safety to `context_eval.py` (depends on 4) — DoD:
  `to_log_dict()` is the only printing path; `SAFE_SOURCE_ID` substitutes a
  source's `kind` for any id not matching `^[A-Za-z0-9._-]{1,128}$`; every
  record carries `record_kind: "context-eval"`, `evaluator_name`,
  `evaluator_version`; no code path can put a `locator`, `selector`, payload
  byte or rendered text into a record.

- [ ] 6. Add outcome linking (depends on 4) — DoD: `link_outcome(...)` is pure
  and maps `ExecutionRef.phase` (`Pending|Running|Succeeded|Failed|Error`) and
  `WorkItem.state` (`WORK_ITEM_STATES`) into
  `{succeeded, failed, abandoned, in-progress, unknown}` with
  `outcome_source: "work-item-ledger"`; the `.status.yaml` `status` fallback is
  reachable only when no `we_` execution exists and records
  `outcome_source: "status-yaml"`; an unrecognised value yields
  `outcome: "unknown"` plus a reason code, never an absent key.

- [ ] 7. Add freshness/promotion-readiness semantics to `context_eval.py`
  (depends on 4) — DoD: `EVIDENCE_KINDS`, `FRESHNESS_STATUSES`,
  `ADR019_V1_FRESHNESS_WINDOW_SECONDS = 604800` and
  `ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS = 3` (ADR 019's v1 promotion policy
  constants); `FreshnessPolicy(window_seconds, min_consecutive_observations)`
  with no defaults, no `from_env()` and no `CONTEXT_EVAL_*` variable;
  `EvidenceIdentity` carries `strategy_content_hash` and
  `strategy_implementation_hash`; `pipeline_source_hash(*functions)` over
  `inspect.getsource`, recorded as a diagnostic only;
  `assess_evidence(records, *, expected, now, policy)` applying the documented
  precedence missing -> mismatched (declared fields) -> mismatched (catalog
  identity, including empty = `catalog-identity-unavailable`) -> stale ->
  insufficient-observations -> fresh; `now` is an argument; `fresh` is
  unreachable for `kind == "none"`. The callers (tasks 8, 10, 12) resolve the
  catalog identity through `orchestrator.context_release.load_version`
  imported inside the function body; `context_eval` never imports it.

- [ ] 8. Add the guarded live emission (depends on 2, 5) — DoD:
  `_context_eval_enabled()` reads `ISSUE_INVESTIGATOR_CONTEXT_EVAL`, default
  `off`; `_emit_context_eval(result)` prints
  `[context] context_eval=<json>` after the existing
  `[context] context_assembly=` line in
  `run_issue_investigator._assemble_context`; the whole body is wrapped so no
  exception escapes in ANY mode, including `on`, with the asymmetry against
  assembly's `on`-mode propagate rule explained in the docstring; the record
  carries `outcome: null`, its join keys, and `evidence_kind: "live"`.

- [ ] 9. Add the fixture corpus (depends on 4) — DoD: seven cases under
  `tests/fixtures/context_eval/cases/` covering all-fresh-labelled,
  stale-source, duplicate-content, budget-exhausted,
  conflicting-prior-proposal, candidate-ceiling-overflow and one deliberately
  unlabelled case; each holds `case_id`, an explicit `config` block, a
  `candidates` array mirroring `CandidateSource` with short synthetic
  `raw_text` (no secrets, no real locators) and `labels` or `labels: null`.

- [ ] 10. Add the fixture harness (depends on 9) — DoD:
  `tests/test_context_eval.py` drives every case through the real
  `context_assembly.run_pipeline` under both `STRATEGY_NAME` and
  `RANKED_STRATEGY_NAME` with an explicitly constructed `AssemblyConfig` (never
  `from_env()`), a fixed `now` and a fixed `ExecutionCorrelation`, then
  `context_snapshot.seal()`, then `context_eval.evaluate(...,
  evidence_kind="fixture-baseline")`; no pipeline stage is re-implemented in
  test code.

- [ ] 11. Commit the baseline and its regeneration gate (depends on 10) — DoD:
  `tests/fixtures/context_eval/baseline.json` holds every metric for every
  (case, strategy) pair plus a header carrying the `EvidenceIdentity` it was
  produced under; the suite fails on any drift naming case, strategy and
  metric; regeneration is `python -m tests.test_context_eval --regenerate
  [case ...]` behind `# pragma: no cover` and `if __name__ == "__main__":`,
  with no pytest or CI caller.

- [ ] 12. Add `orchestrator/run_context_eval.py` (depends on 3, 4, 6) — DoD:
  `python -m orchestrator.run_context_eval --work-item <id> [--execution we_...]
  [--json]` reads the work item and its executions, picks `--execution` or the
  newest `we_` execution with a stored snapshot, rebuilds it with
  `ContextSnapshot.from_dict`, verifies both identities, evaluates with
  `evidence_kind="stored-replay"`, links the outcome, and prints one
  `context_eval=<json>` line; `capability_calls` is 0 and the CLI's own reads
  are reported as `replay_store_reads`; exits non-zero with a named reason code
  on absent work item, snapshot-less execution or an undecodable document;
  never prints `stored_document`; issues no write and needs no writer token;
  `main()` follows `run_usage_collector.main()`'s argparse shape.

- [ ] 13. Update the ADRs (depends on 7) — DoD:
  `docs/adr/015-context-evaluation-contract.md` status `proposed` ->
  `accepted`, a new sec. 7 "Evidence freshness and promotion readiness"
  (closed status set, precedence order, the catalog-identity rule, a
  reference to ADR 019 as owner of the window/observation constants, and the
  statement that #472's production
  path must refuse `evidence.kind = none`), and the Implementation map updated
  to record what #526 delivered; sections 1-6 byte-unchanged;
  `docs/adr/009-context-snapshot-contract.md` follow-up row (f) annotated with
  #526 the way row (b) names #431/#490.

- [ ] 14. Update the runbook (depends on 8, 11, 12) — DoD: a README "Context
  evaluation" subsection covering enabling live emission, reading a
  `context_eval=` line, running the replay CLI, regenerating the baseline, and
  what #472 requires; a `.env.example` block after the existing "Context
  assembly pilot" block (lines 65-81) for `ISSUE_INVESTIGATOR_CONTEXT_EVAL`
  only, commented out; the freshness constants are ADR 019's and have no
  variable.

## Tests

- [ ] T1. Document identity: a sealed snapshot verifies; a tampered
  `content_hash` and a tampered `snapshot_id` each produce
  `verdict: "hash-mismatch"` with `metrics is None` and both disagreeing field
  names present.
- [ ] T2. Store identity: a `StoreRef` whose `store_content_hash` matches
  `hash_bytes(canonical_bytes(snapshot))` verifies; a mutated one mismatches;
  `store_snapshot_id` is never recomputed (a ref with an arbitrary but
  `cs_`-prefixed id still verifies on hash alone).
- [ ] T3. `store_ref_from` returns `None` for `snapshot-skipped`,
  `snapshot-diverged`, `snapshot-unknown` and for a `stored` answer with a
  non-`cs_` id; returns a populated ref for `snapshot-sealed` and
  `snapshot-replayed`; `AssemblyResult.store_ref` is `None` when there is no
  store execution and assembly does not fail.
- [ ] T4. `_persist_to_work_item_store` still raises `SnapshotNotPersisted`
  under exactly the pre-change conditions, and now returns the answer in every
  non-raising path.
- [ ] T5. Metric definitions: labelled case yields the expected
  `selected_precision`/`useful_recall`/`f1`/`missing_expected`/`noise_rate`;
  the unlabelled case yields `null` for all three ratios and never `0.0` or
  `1.0`.
- [ ] T6. `stale_rate` counts both shapes: the default strategy's dropped
  `reason_code == "stale"` source and the ranked strategy's still-selected
  `reason_code == "stale-demoted"` source, on the same fixture case.
- [ ] T7. Conflict metrics come from `snapshot.conflicts` only — a case whose
  ranked run populates conflicts and whose default run does not gives
  `conflicts_detected > 0` and `0` respectively, with no text re-derivation.
- [ ] T8. Telemetry safety: a candidate carrying a distinctive locator,
  selector value and payload string is scored, and none of those three strings
  appears anywhere in `json.dumps(record.to_log_dict())`.
- [ ] T9. Unsafe `source_id` (spaces, a slash, >128 chars) is replaced by the
  source's `kind` in every emitted field.
- [ ] T10. Regex pinning: `context_eval.SAFE_SOURCE_ID.pattern ==
  context_assembly._SAFE_SOURCE_ID.pattern`.
- [ ] T11. Store-hash pinning: for a real sealed snapshot, the evaluator's
  store hash equals `hash_bytes(canonical_bytes(snapshot))` from
  `work_context/snapshots.py`.
- [ ] T12. Outcome mapping is total over `WORK_ITEM_STATES` — every member maps
  to a member of the outcome vocabulary or to `unknown` with a reason code, and
  the test iterates the frozenset so a new store state fails loudly.
- [ ] T13. The `.status.yaml` fallback is used only when no `we_` execution
  exists, and always sets `outcome_source: "status-yaml"`.
- [ ] T14. A live record carries `outcome: null`, `execution_id` and
  `context_snapshot_id`.
- [ ] T15. `assess_evidence` precedence: empty list and `kind == "none"` ->
  `missing`; a differing `strategy_version` -> `mismatched`; a differing
  `strategy_implementation_hash` or `strategy_content_hash` with every
  declared field equal -> `mismatched`; an empty catalog identity ->
  `mismatched` / `catalog-identity-unavailable`; a differing
  `pipeline_source_hash` alone -> still `fresh` (diagnostic only); an
  observation older than the window ->
  `stale`; two observations against a minimum of three ->
  `insufficient-observations`; three agreeing recent observations -> `fresh`.
  Every case asserts the reason code, and `fresh` is never returned for
  `kind == "none"`.
- [ ] T16. `ADR019_V1_FRESHNESS_WINDOW_SECONDS == 604800` and
  `ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS == 3`, pinned against the values
  stated in `docs/adr/019-context-strategy-release-contract.md`;
  `FreshnessPolicy` has no defaults and no `from_env`, rejects a non-positive
  window or count loudly, and no `CONTEXT_EVAL_` string appears in
  `context_eval`'s source.
- [ ] T17. With `ISSUE_INVESTIGATOR_CONTEXT_EVAL` unset, investigator stdout
  contains no `context_eval=` line and is otherwise unchanged; with it `on`,
  exactly one `context_eval=` line is printed after the
  `context_assembly=` line.
- [ ] T18. A `context_eval.evaluate` monkeypatched to raise does not fail the
  investigation in `shadow` OR in `on`; one bounded `warn:` line is printed.
- [ ] T19. Baseline drift: mutating one metric in `baseline.json` fails the
  suite with a message naming the case, the strategy and the metric.
- [ ] T20. Baseline isolation: setting every `ISSUE_INVESTIGATOR_CONTEXT_*`
  variable to a non-default value leaves every fixture record byte-identical.
- [ ] T21. Both strategies are exercised for every case, asserted by counting
  `(case_id, strategy)` pairs against `len(cases) * 2`.
- [ ] T22. The harness calls the real `run_pipeline` — asserted by
  monkeypatching `context_assembly.run_pipeline` to raise and confirming every
  case fails, so no case can silently bypass it.
- [ ] T23. Replay CLI happy path against a fake `WorkItemClient`: selects the
  newest snapshot-carrying execution, prints one record with
  `evidence_kind: "stored-replay"` and `capability_calls: 0`, exits 0.
- [ ] T24. Replay CLI read-only: the fake client fails the test on any non-GET
  request; no `seal_snapshot`, no `.status.yaml` write, no writer token
  required.
- [ ] T25. Replay CLI failure paths exit non-zero with a reason code for an
  absent work item, an `--execution` with no stored snapshot, and an
  undecodable stored document; the stored document is never printed.
- [ ] T26. `--execution` on a non-`we_` id is rejected with a named error
  rather than silently falling back.
- [ ] T27. Non-authorization: no module under `orchestrator/` imports
  `context_eval` except `run_issue_investigator` and `run_context_eval`,
  asserted by scanning imports — in particular no policy, capability or
  lifecycle module does.
- [ ] T28. Purity: `context_eval`'s module source contains no `os.getenv` or
  `os.environ` at all, no `urllib`/`httpx`/`subprocess` import, no import of
  `context_release` or `yaml`, and no `datetime.now` call.
- [ ] T29. Catalog identity in the callers: the fixture harness and the replay
  CLI put the committed catalog's `contentHash`/`implementationHash` for each
  strategy version into every record; a temporary catalog whose
  `implementationHash` does not match the code yields records assessed
  `mismatched` / `catalog-identity-unavailable`.

## Rollback

Three independent levels, smallest first.

1. **Disable at runtime, no deploy.** Unset `ISSUE_INVESTIGATOR_CONTEXT_EVAL`
   (or set it to `off`). Live emission stops; `_emit_context_eval` returns
   before importing `context_eval`. Investigator output returns to
   byte-identical-to-today, pinned by T17. The replay CLI and the fixture suite
   are unaffected and stay usable.
2. **Catalog-hash churn.** There is no knob to relax identity: evidence that
   measured other code is not evidence for this version. Republish the
   strategy version (`tools/context_release.py publish`), regenerate the
   baseline, and restart the observation window.
3. **Revert the commit.** Everything added is additive: one new module, one new
   CLI, one new test file, one new fixture directory, four doc edits, and two
   touched functions. Reverting restores
   `_persist_to_work_item_store -> None` and drops
   `AssemblyResult.store_ref` — which nothing outside `context_eval` reads, and
   which is a defaulted field, so no other construction site changes. No
   migration to undo: no mctl-api schema, route or table was added, no stored
   snapshot was written or rewritten, and `ContextSnapshot`'s hash inputs were
   never touched, so every already-persisted snapshot keeps its identity across
   the revert.

If a regression is suspected in assembly itself rather than in evaluation, the
pre-existing rollback stands and is untouched by this work: set
`ISSUE_INVESTIGATOR_CONTEXT_MODE=off`, or
`ISSUE_INVESTIGATOR_CONTEXT_STRATEGY=deterministic-fixed-order` to leave the
ranked strategy.
