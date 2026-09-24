# Tasks: issue-266-feat-context-evals-measure-retrieval-qua

- [ ] 1. Write `docs/adr/015-context-evaluation-contract.md`: metric
      definitions (precision/recall/f1, stale, duplicate, noise, bytes,
      token estimate, latency, capability calls, per-kind coverage,
      conflicts), the two identity pairs (`cs-` + `content_hash` excluding
      `created_at`; `cs_` + sha256 over the canonical bytes), the
      telemetry-safety rule, the fixture contract, the outcome-link rule,
      and a restatement that context relevance is never authorization
      (ADR 009 sec. 5). — DoD: ADR committed as **015** (012 and 014 are
      taken), status `proposed`, cross-linked from ADR 009 amendment 1's
      closing line (`docs/adr/009-context-snapshot-contract.md:402`).
- [ ] 2. Update ADR 009's follow-up table: rewrite row (b)
      (`docs/adr/009-context-snapshot-contract.md:513`) from "needs an
      issue" to "delivered by mctlhq/mctl-agents#431, proven live in #490",
      and add a measurement row pointing at #266 / ADR 015. — DoD: no row in
      that table claims snapshot persistence is unowned; `docs` diff only.
- [ ] 3. Extract `run_pipeline` in `orchestrator/context_assembly.py`
      (depends on 1) — move `assemble()`'s body between the pre-budget
      ceiling and `seal()` (`:992-1036`) into
      `run_pipeline(candidates, config, now) -> PipelineOutcome`, covering
      BOTH branches (default drop-stale at `:1012-1023`, ranked
      rank/`detect_conflicts`/`flag_stale` at `:996-1010`) and the shared
      dedupe/truncate/budget/`stale_demoted` tail. `assemble()` becomes a
      caller and keeps collectors, latency clock, `seal()` and
      `AssemblyMetrics`. — DoD: pure move, no behaviour change;
      `tests/fixtures/context/investigator-snapshot.json` and the pins in
      `tests/test_context_ranking.py:120,148` pass untouched.
- [ ] 4. Return the persist answer (depends on 3) — make
      `context_assembly._persist_to_work_item_store` (`:1201`) return its
      `SnapshotAnswer`, add `StoreRef {work_item_id, execution_id,
      store_snapshot_id, store_content_hash}` and an optional
      `AssemblyResult.store_ref` populated when `answer.stored` holds
      (`work_context/snapshots.py:78-81`). — DoD: no extra HTTP call; the
      sealed document and its `content_hash` are unchanged; `store_ref` is
      `None` when the rollout is `off` or the execution is not `we_`.
- [ ] 5. Add `orchestrator/context_eval.py` (depends on 3, 4) — stdlib-only,
      importing `context_snapshot` and `context_assembly` only:
      `EvalCase`/labels, `verify_identity`, `ContextEvalMetrics`,
      `ContextEvalRecord.to_log_dict()` with `record_kind: "context-eval"`,
      `evaluator_name`, `evaluator_version`, the correlation chain and the
      `store_ref`. A `hash-mismatch` verdict emits the disagreeing field
      names and NO metrics. — DoD: `evaluate()` is pure (no I/O, no clock
      beyond what it is given); every emitted value is an id, kind, code or
      number; `tests/test_worker_isolation.py` still passes.
- [ ] 6. Add outcome linking (depends on 5) — `OutcomeLink` resolved from
      the store ledger (`WorkItemClient.get` → `WorkItem.state` and the
      matching `ExecutionRef.phase`, joined on `execution_id`,
      `prior_execution_ids`, `resumed_from_snapshot_id`), with a
      `.status.yaml` fallback recording `outcome_source: "status-yaml"`. —
      DoD: outcome resolution lives outside `evaluate()` and is injected, so
      the evaluator stays pure and offline-testable.
- [ ] 7. Emit the live line (depends on 5) — in
      `run_issue_investigator._assemble_context`, add a NEW guarded block
      after the existing `[context] context_assembly=` print
      (`orchestrator/run_issue_investigator.py:1837`, itself outside the
      `try` at `:1791`) that prints
      `[context] context_eval=<json sorted keys>`; add
      `_context_eval_enabled()` reading `ISSUE_INVESTIGATOR_CONTEXT_EVAL`
      fresh per call, mirroring `_context_mode()` (`:155`). — DoD: the line
      carries `work_item_id`/`execution_id`/`execution_sequence` when
      `snapshot.work_context` is set; it is emitted whenever the context
      mode is not `off`, independently of `WORK_CONTEXT_ROLLOUT_MODE`
      (owner choice (b)); any exception yields
      `warn: context evaluation failed: ...` and the run continues in
      `shadow` AND `on`.
- [ ] 8. Build the fixture set (depends on 5) —
      `tests/fixtures/context_eval/` with eight cases:
      `logs-relevant-and-irrelevant`, `deployment-stale-vs-current`,
      `stale-demoted`, `github-issue-and-pr-evidence`, `duplicate-evidence`,
      `conflict-prior-proposal-superseded`, `missing-evidence`,
      `budget-eviction`; each declares `useful` / `noise` / `expect_stale` /
      `expect_duplicate_of` / `expect_conflicts` / `expect_missing`. — DoD:
      every case runs through `run_pipeline` under BOTH strategies with a
      fixed `now` and a fixed `ExecutionCorrelation`; no case reads the
      network or a clone.
- [ ] 9. Commit `tests/fixtures/context_eval/baseline.json` (depends on 8) —
      every metric for every (case, strategy) pair. — DoD: regenerated only
      by an explicit `--write-baseline` run, never in CI, following
      `tools/record_workflow_history.py`'s deliberate-regeneration
      convention.
- [ ] 10. Add `orchestrator/run_context_eval.py` (depends on 5, 6, 8) —
      `--work-item <id> [--execution we_...]` read-only replay through
      `WorkItemClient.get` and `.execution_snapshot` only, rebuilding the
      snapshot from the stored `canonical_b64` via `ContextSnapshot.from_dict`
      and verifying both hashes before evaluating; `--fixtures
      [--write-baseline]` for the offline suite. — DoD: no POST, no file
      write, no gitops touch on the `--work-item` path; a
      `SNAPSHOT_ABSENT`/`SNAPSHOT_UNKNOWN` answer prints the verdict and
      exits non-zero; `--work-item` is deliberately NOT the investigator's
      `--work-item-id` (`run_issue_investigator.py:3123`).
- [ ] 11. Document the runbook (depends on 7, 10) — add the two env vars
      (`ISSUE_INVESTIGATOR_CONTEXT_EVAL`, and the existing
      `ISSUE_INVESTIGATOR_CONTEXT_MODE`/`..._STRATEGY`) and the replay
      commands to `README.md` and `.env.example`, next to the existing
      context-assembly entries. — DoD: a reader can reproduce a baseline and
      replay one stored execution from the docs alone.

## Tests

- [ ] T1. `tests/test_context_assembly.py` — `run_pipeline` extraction is
      behaviour-preserving: for every fixture case and both strategies,
      `assemble()` produces the same `snapshot_id`, `content_hash`, source
      order, `reason_code`s and `AssemblyMetrics` as before the extraction.
- [ ] T2. `tests/test_context_ranking.py` (the review's explicit ask) —
      extend the existing 644-line suite so the ranked-strategy tests call
      `run_pipeline` directly: pinned primaries first, trust-then-freshness
      order, `stale-demoted` retained-and-flagged, and
      `detect_conflicts` firing `CONFLICT_PRIOR_PROPOSAL_SUPERSEDED`; the
      default-strategy pins at `:120` and `:148` remain unmodified.
- [ ] T3. `tests/test_context_eval.py` — metric correctness on the labelled
      fixtures: precision/recall/f1 on a labelled case; `null` (never 0.0 or
      1.0) on an unlabelled one; `missing_expected > 0` and recall < 1 on
      `missing-evidence`; `duplicate_rate` on `duplicate-evidence`;
      `noise_rate` on `logs-relevant-and-irrelevant`.
- [ ] T4. `stale-demoted` counts as stale: the same candidate set yields
      `stale_rate > 0` under BOTH strategies — dropped (`reason_code="stale"`)
      under `deterministic-fixed-order`, demoted
      (`reason_code="stale-demoted"`) under `trust-freshness-ranked`.
- [ ] T5. Conflict metrics come from `snapshot.conflicts` only: the ranked
      run of `conflict-prior-proposal-superseded` reports
      `conflicts_detected == 1`, the default run reports `0`, and no metric
      is derived from any text comparison.
- [ ] T6. Identity verification: a snapshot whose `content_hash` was tampered
      with, and a `store_ref` whose `store_content_hash` does not match
      `hash_bytes(canonical_bytes(snapshot))`, each yield
      `verdict: "hash-mismatch"`, name the disagreeing field, and emit no
      metrics.
- [ ] T7. Telemetry safety: over every fixture record, no emitted string
      equals any candidate's `locator`, `selector` value or raw payload; a
      `source_id` that is not a plain token (`_SAFE_SOURCE_ID`,
      `context_assembly.py:572`) is replaced by its kind.
- [ ] T8. Emission: with `ISSUE_INVESTIGATOR_CONTEXT_MODE=shadow` exactly one
      `[context] context_eval=` line is printed and it parses as JSON;
      with the mode `off`, none; with `ISSUE_INVESTIGATOR_CONTEXT_EVAL=off`,
      none; with a `WorkContextRef` set, the line carries `work_item_id`,
      `execution_id` and `execution_sequence`.
- [ ] T9. Failure isolation: an evaluator that raises leaves
      `_assemble_context`'s return value and the sealed snapshot unchanged
      and prints `warn: context evaluation failed:` — asserted in `shadow`
      AND in `on`, where the assembly `try` itself re-raises.
- [ ] T10. Replay is read-only: a fake `WorkItemClient` recording every call
      shows only `get` and `execution_snapshot`; `seal_snapshot`,
      `attach_execution` and every `*_execution_request` method are never
      called, and no file under the repo or state dir is created.
- [ ] T11. Outcome link: a work item whose ledger names the evaluated
      execution yields the store-derived outcome; a run with no `we_`
      execution falls back to `.status.yaml` with
      `outcome_source: "status-yaml"`; a resumed execution's
      `prior_execution_ids` / `resumed_from_snapshot_id` chain is carried.
- [ ] T12. Baseline: every (case, strategy) pair matches
      `tests/fixtures/context_eval/baseline.json`; the test fails loudly
      naming the drifted metric, and `--write-baseline` is the only way to
      change it.
- [ ] T13. Isolation and lint: `tests/test_worker_isolation.py` still passes
      with `orchestrator.context_eval` in the graph; `ruff` (line-length
      120) and `mypy` pass over the new modules.

## Rollback

Three independent levels, cheapest first.

1. **Operator, no deploy.** Set `ISSUE_INVESTIGATOR_CONTEXT_EVAL=off` in the
   investigator's env (read fresh per call, like `_context_mode()`): no
   evaluation runs and no `context_eval` line is printed. Setting
   `ISSUE_INVESTIGATOR_CONTEXT_MODE=off` — still the default — disables
   assembly and therefore evaluation as well.
2. **Revert the emission.** Task 7 is a single self-contained guarded block
   in `_assemble_context`; deleting it removes every production effect while
   leaving the evaluator, fixtures and replay runner available offline.
3. **Full revert.** Revert tasks 3-10 in one commit. The only production
   code touched is `context_assembly.py` (the `run_pipeline` move plus the
   `store_ref` return) and the one block in `run_issue_investigator.py`.
   Nothing was migrated, nothing new was persisted, and no sealed snapshot's
   bytes or `snapshot_id` changed, so no stored document needs repair and no
   mctl-api state needs undoing. The ADR 009 row-(b) correction (task 2) is
   a documentation fix that is correct independently of this feature and
   should be kept.
