# Design: issue-266-feat-context-evals-measure-retrieval-qua

## Current state

Read on the clone of `mctlhq/mctl-agents` at the revision this proposal was
written against. Every line number below was re-checked against that tree.

### The snapshot contract

`orchestrator/context_snapshot.py` is the frozen, inert contract: no
retrieval, no ranking, no I/O. `seal()` (`:1210`) hashes every field except
`content_hash`, `snapshot_id` and `created_at` (`_content_payload`, `:1162`)
and mints `snapshot_id = "cs-" + content_hash[7:23]` (`:1245`).
`recompute_content_hash()` (`:1266`) re-derives that hash without mutating
the snapshot — it exists precisely so a fixture can be verified.
`work_context` and a non-empty `conflicts` block enter the hash only when
present (`:1199-1206`), so older documents keep their identity.
`WorkContextRef` (`:559`) carries `work_item_id`, `work_item_revision`,
`execution_id`, `execution_sequence`, `prior_execution_ids` and
`resumed_from_snapshot_id`. `ExecutionCorrelation` (`:461`) carries the
agent, environment, target repo SHA and the definition/profile version and
content hashes.

### The assembler

`orchestrator/context_assembly.py` (stdlib-only by design, see its module
docstring `:22-27` and `tests/test_worker_isolation.py`) runs five
collectors in fixed order (`_COLLECTOR_ORDER`, `:855`) and then a
deterministic pipeline inside `assemble()` (`:964`):

- `deterministic-fixed-order` 1.0.0 (`STRATEGY_NAME`, `:70`): `assign_ranks`
  (`:352`), `normalize` (`:360`), `classify_freshness` (`:368`), then a
  **drop** of anything `stale` (`:1018-1022`).
- `trust-freshness-ranked` 1.0.0 (`:77`, #471): `normalize` +
  `classify_freshness`, then `rank_candidates` (`:491`), `detect_conflicts`
  (`:532`) and `flag_stale` (`:521`), which **demotes and flags**
  (`reason_code="stale-demoted"`) instead of dropping.
- Both branches then share `deduplicate` (`:385`),
  `truncate_to_per_source_limit` (`:401`), `apply_budget` (`:424`) and
  `seal()` (`:1040`).

`AssemblyMetrics` (`:258`) already counts candidates by kind, included by
kind, `dropped_stale`, `dropped_duplicate`, `excluded_budget`,
`truncated_sources`, `used_sources`, `used_bytes`, `assembly_latency_ms`,
`collector_calls`, `stale_demoted`, `conflict_count` and
`conflict_sources_capped`, and `to_log_dict()` (`:285`) is the only thing
the module ever prints — never a locator or a payload byte.

Everything in that list is a statement about *what the pipeline did*.
Nothing states whether the evidence the model needed was selected, and
nothing compares one strategy against the other on the same input.

### Snapshots are stored now

`assemble_investigator_context` (`:1080`) calls
`_persist_to_work_item_store` (`:1201`) whenever `_work_context_active`
(`:1166`) holds — a `we_`-prefixed execution id and
`WORK_CONTEXT_ROLLOUT_MODE >= observe`. `orchestrator/work_context/
snapshots.py` sends the whole canonical document: `canonical_bytes` (`:88`)
and `seal_body` (`:95`) post `canonical_b64` plus a `content_hash` that is
sha256 over *those* bytes (so, unlike the document's own `content_hash`, it
includes `created_at`). `WorkItemClient` (`orchestrator/work_context/
client.py`) exposes `get` (`:162`, the work item plus its full execution
ledger), `list_executions` (route, `:61`), `execution_snapshot` (`:251`,
route `:63`) and `seal_snapshot` (`:261`). A read returns the stored
document decoded from `canonical_b64` (`snapshots.py:261-269`) and the
store's own opaque `cs_`-prefixed id (`snapshots.py:42,128-135`). This
path is live (#490), so the 2026-09-20 proposal's premise that "snapshots
are not stored" is simply false now, and no new storage is needed.

### Where the outcome lives

`WorkItem` (`orchestrator/work_context/contract.py:265`) carries `state`,
`issue_url`, `service`, `slug` and the ledger of `ExecutionRef`s (`:166`),
each with `execution_id`, `sequence`, `temporal_workflow_id`, `started_at`
and `phase`. For runs outside the store, the only outcome record is the
published proposal's `.status.yaml`, whose `context` block already carries
`snapshot_id`, `content_hash`, `strategy` and `strategy_version`
(`orchestrator/run_issue_investigator.py:1226-1232`).

### Where a line can be printed

`_assemble_context` (`orchestrator/run_issue_investigator.py:1763`) wraps
collection and sealing in a `try` (`:1791`) whose `except` (`:1827-1831`)
re-raises in `on` mode and warns in `shadow`. The
`[context] context_assembly=` print at `:1837` is **outside** that `try`,
after the `cast`. `investigate()` calls `_assemble_context` at `:2444` and
passes `context.snapshot` into `_write_status_yaml` at `:2598`.
`tests/test_context_ranking.py` (644 lines) pins the default strategy's
snapshot ids and stored bytes (`:120`, `:148`) and covers the ranked
strategy, the conflict rule and the metrics.

## Proposed solution

Four pieces, no new storage and no new API route.

### 1. Extract `run_pipeline` from `assemble()` (behaviour-preserving)

Move everything between the collector loop and `seal()` out of `assemble()`
into one pure function in `orchestrator/context_assembly.py`:

```python
@dataclass(frozen=True)
class PipelineOutcome:
    candidates: list[CandidateSource]   # ordered by rank
    strategy: ContextStrategy
    budget: ContextBudget
    conflicts: list[ContextConflict]
    counters: PipelineCounters          # the drop/dup/budget/stale/conflict counts

def run_pipeline(
    candidates: list[CandidateSource], config: AssemblyConfig, now: datetime
) -> PipelineOutcome: ...
```

It covers **both** branches — the default drop-stale branch
(`context_assembly.py:1012-1023`) and the ranked
rank/`detect_conflicts`/`flag_stale` branch (`:996-1010`) — plus the shared
`deduplicate` / `truncate_to_per_source_limit` / `apply_budget` /
`stale_demoted` counting (`:1025-1036`). `assemble()` keeps the collectors,
the pre-budget ceiling, `seal()`, the latency clock and `AssemblyMetrics`,
and becomes a caller. This is the single change to production selection
code, and it is a move: the default strategy's canonical bytes and
`snapshot_id`s are pinned by the existing golden fixture
(`tests/fixtures/context/investigator-snapshot.json`,
`tests/test_context_ranking.py:120,148`), which must pass untouched.

The extraction is what lets the evaluator run a fixture's candidate list
through *the real pipeline* under either strategy with no network, no
collector and no clone — rather than re-implementing ranking in test code,
which would measure the copy instead of the system.

### 2. `orchestrator/context_eval.py` — the evaluator (stdlib-only)

A new module with the same import discipline as `context_assembly`
(`context_snapshot`, `context_assembly` and stdlib only; never
`claude_agent_sdk`, so `tests/test_worker_isolation.py` stays green).

**Identity first.** `verify_identity(snapshot, store_ref)` runs before any
metric:

- document identity: `recompute_content_hash(snapshot) == snapshot.content_hash`
  and `snapshot.snapshot_id == "cs-" + content_hash[7:23]` — the `cs-` pair
  whose hash excludes `created_at`;
- store identity: `hash_bytes(canonical_bytes(snapshot)) ==
  store_ref.store_content_hash` — the `cs_` pair whose hash is over the whole
  canonical document, minted by mctl-api. `store_snapshot_id` is opaque: it
  is carried and compared to what the store reported, never recomputed.

Both pairs are modelled explicitly in `StoreRef {work_item_id, execution_id,
store_snapshot_id, store_content_hash}`. A mismatch produces a record with
`verdict: "hash-mismatch"`, the disagreeing field names and **no metrics**.

**Labels.** `EvalCase` declares, per source id: `useful` (expected useful
evidence), `noise` (expected-irrelevant), `expect_stale`,
`expect_duplicate_of`, and case-level `expect_conflicts:
[CONFLICT_PRIOR_PROPOSAL_SUPERSEDED]` plus `expect_missing: [...]` for
evidence deliberately absent from the candidate list.

**Metrics** (`ContextEvalMetrics`), computed from the sealed snapshot plus
the `AssemblyMetrics` counters:

| Metric | Definition |
|---|---|
| `selected_precision` | selected ∩ useful / selected, over labelled candidates |
| `useful_recall` | selected ∩ useful / declared useful; `null` when a case is unlabelled |
| `f1` | harmonic mean of the two; `null` when either is `null` |
| `missing_expected` | declared useful ids that no candidate carried |
| `stale_rate` | (`freshness.staleness == "stale"` OR `selection.reason_code == "stale-demoted"`) over selected sources — the ranked strategy demotes rather than drops, so `stale-demoted` counts as stale |
| `duplicate_rate` | `dropped_duplicate` / `candidates_total` |
| `noise_rate` | selected-but-labelled-noise / selected |
| `context_bytes` / `context_tokens_estimate` | `budget.used_bytes`; `ceil(used_bytes / 4)`, declared an estimate |
| `assembly_latency_ms` | from `AssemblyMetrics` |
| `capability_calls` | `collector_calls` plus store round trips (0 in replay, 1-2 live) |
| `coverage_by_kind` | per kind: candidates, included, bytes — "per-source contribution" |
| `conflicts_detected` / `conflicts_expected_detected` / `conflict_sources_capped` | derived from `snapshot.conflicts` only, never from text |

**Record.** `ContextEvalRecord.to_log_dict()` emits `record_kind:
"context-eval"`, `evaluator_name`/`evaluator_version`, `verdict`, the
correlation chain (`execution_id`, `context_snapshot_id`,
`content_hash`, `strategy`/`strategy_version`/`ranker_name`/`ranker_version`,
`selected_source_ids`, `agent`, `environment`, `definition_version`,
`profile_version`, `release_revision` off `snapshot.execution`), the
`store_ref`, the `work_context` keys when present, the outcome block and the
metrics. Ids, kinds, closed-vocabulary codes and numbers only — the same
rule `AssemblyMetrics.to_log_dict()` already keeps.

### 3. Emission and outcome link

In `run_issue_investigator._assemble_context`, a **new guarded block placed
after** the existing `print(f"[context] context_assembly=...")` at `:1837`:

```python
if _context_eval_enabled():          # ISSUE_INVESTIGATOR_CONTEXT_EVAL, read fresh
    try:
        record = context_eval.evaluate_live(result)
        print(f"[context] context_eval={json.dumps(record.to_log_dict(), sort_keys=True)}")
    except Exception as exc:         # noqa: BLE001 - measurement never fails a run
        print(f"warn: context evaluation failed: {type(exc).__name__}: {exc}")
```

It is its own block, not folded into the assembly `try`, precisely because
that `try` re-raises in `on` mode: a snapshot that describes the built
prompt must still be sealed even when measurement breaks. The line carries
`work_item_id` / `execution_id` / `execution_sequence` whenever
`result.snapshot.work_context` is set. It is **not** gated on
`WORK_CONTEXT_ROLLOUT_MODE` (owner choice (b)) — a `shadow` run with the
rollout `off` is exactly the baseline this issue wants measured.

To carry a `store_ref` on the live line, `_persist_to_work_item_store`
(`context_assembly.py:1201`) returns its `SnapshotAnswer` instead of `None`,
and `AssemblyResult` gains one optional field `store_ref: StoreRef | None`
populated when `answer.stored` holds (`snapshots.py:78-81`). That is an
in-process field on a non-sealed dataclass — no schema change, no effect on
`content_hash`.

**Outcome link (owner choice (a)).** The live record cannot know the outcome
yet, so it records `outcome: null` and the join keys. `OutcomeLink` is
resolved by the replay runner and by the analysis path:

1. via the store ledger — `WorkItemClient.get(work_item_id)` gives
   `WorkItem.state` and the `ExecutionRef` whose `execution_id` matches;
   `prior_execution_ids` and `resumed_from_snapshot_id` chain a resumed
   execution back to the snapshot it continued from;
2. only for runs with no `we_` execution, `.status.yaml`'s `status`, with
   `outcome_source: "status-yaml"` recorded so the weaker link is visible.

### 4. Fixtures, baseline and the replay runner

`tests/fixtures/context_eval/` holds one JSON file per case (candidate
sources with explicit `kind`, `trust_tier`, `observed_at`,
`max_age_seconds`, `content_time`, raw bytes, plus the labels) and one
`baseline.json` holding every metric for every (case, strategy) pair. The
cases:

| Case | What it exercises |
|---|---|
| `logs-relevant-and-irrelevant` | synthetic `loki-logs` candidates, half labelled noise — precision/noise rate |
| `deployment-stale-vs-current` | two deployment-info sources, one past `max_age_seconds` — default drops (`reason_code="stale"`), ranked demotes |
| `stale-demoted` | a stale source that must appear as `stale-demoted` and still be counted stale |
| `github-issue-and-pr-evidence` | issue + comments, one comment carrying the decisive constraint |
| `duplicate-evidence` | byte-identical candidates — `duplicate-content` under both strategies |
| `conflict-prior-proposal-superseded` | prior proposal `.status.yaml` `updated_at` older than a later comment — fires `CONFLICT_PRIOR_PROPOSAL_SUPERSEDED` under ranked, none under default |
| `missing-evidence` | a declared useful id no candidate carries — `missing_expected > 0`, recall < 1 |
| `budget-eviction` | useful evidence below the default cut but retained by the ranked order — the strategy comparison the issue asks for |

Every case is run through `run_pipeline` **twice**, once per strategy, and
sealed with a fixed `now` and a fixed `ExecutionCorrelation`, so results are
byte-stable. `python -m orchestrator.run_context_eval --fixtures` prints the
records; `--write-baseline` rewrites `baseline.json` deliberately (the
convention `tools/record_workflow_history.py` sets).

`orchestrator/run_context_eval.py` is the CLI:

- `--work-item <id> [--execution we_...]` — read-only replay. Reads only
  `WorkItemClient.get` and `WorkItemClient.execution_snapshot`; rebuilds the
  `ContextSnapshot` from the stored `canonical_b64` document via
  `ContextSnapshot.from_dict`; verifies both hashes; resolves the outcome
  from the same ledger read; prints the record. It never POSTs, never
  writes a file and never touches gitops. Without `--execution` it walks the
  ledger newest-first for the latest execution that sealed a snapshot.
- `--fixtures [--write-baseline]` — offline, no network at all.

The flag is `--work-item`, deliberately distinct from the investigator's own
`--work-item-id` (`run_issue_investigator.py:3123`): these are different
programs, and a reader should not mistake a read-only replay for a run.

### How this complements #60

The record is a *second, separately-named* measurement keyed by
`execution_id` and `context_snapshot_id`, with `record_kind:
"context-eval"`, `evaluator_name` and `evaluator_version`. It produces no
overall quality score and grades no model output, so #60's final-execution
evaluator joins to it on those keys rather than competing with it. If #60
later wants the context metrics inline, `to_log_dict()` is already the
join-ready payload.

### ADR work

- New `docs/adr/015-context-evaluation-contract.md` (012 is model-usage cost
  attribution, 014 is the policy checkpoint; 015 is next free): metric
  definitions, the two hash pairs, the telemetry-safety rule, the fixture
  contract and the "context relevance is never authorization" restatement
  (ADR 009 sec. 5).
- ADR 009's follow-up row (b) (`:513`) is rewritten from "needs an issue" to
  "delivered by mctlhq/mctl-agents#431, proven live in #490", and a
  measurement row pointing at #266 / ADR 015 is added next to it.

## Alternatives

1. **Extend `AssemblyMetrics` in place instead of a new evaluator module.**
   Rejected. The assembler would grade itself, which cannot express the two
   things this issue needs: one case scored under *both* strategies, and a
   score computed offline against a snapshot sealed days ago. It would also
   push label data into the production assembly path, where it has no
   business being.
2. **Build on #60's final-output evaluator and derive context quality from
   the score.** Rejected — it is the exact conflation the issue names: a low
   score cannot distinguish bad reasoning over good context from good
   reasoning over missing context. Joining by key keeps both signals and
   costs nothing.
3. **Persist evaluation records in a new mctl-api table.** Rejected for v1.
   The durable artefact already exists (#431/#490) and the evaluation is a
   pure function of it, so a stored record would be a derived duplicate that
   can silently disagree with its source. A structured log line plus
   on-demand replay gives the same answers with no migration.
4. **Re-implement ranking/filtering inside the test suite to score
   fixtures.** Rejected: it would measure a copy of the pipeline, so a real
   regression in `context_assembly` could leave every metric green. Hence
   the `run_pipeline` extraction.
5. **Use a model judge to label relevance.** Rejected: non-goal ("training a
   production reranker"), non-deterministic, and it would put model cost and
   an injection surface into a measurement path.

## Platform impact

- **Migrations:** none. No schema change, no new mctl-api route, no new
  table, no gitops shape change. `ContextSnapshot`'s `content_hash` inputs
  are untouched (`_content_payload`, `context_snapshot.py:1162`), so every
  already-persisted snapshot keeps its identity.
- **Backward compatibility:** `run_pipeline` is an extraction pinned by the
  existing golden fixture and by `tests/test_context_ranking.py:120,148`;
  `AssemblyResult.store_ref` is a new optional field on an in-process
  dataclass. With `ISSUE_INVESTIGATOR_CONTEXT_MODE=off` (still the default)
  nothing new runs at all.
- **Resource impact:** one extra pure pass over at most `max_candidates`
  (100) sources — microseconds — and one extra stdout line per
  investigation. No extra HTTP call on the live path: the `store_ref` comes
  from the persist answer the run already receives. The replay runner adds
  at most four round trips (`get` re-reads once on a ledger mismatch,
  `client.py:179`) plus one snapshot read, and only when a human runs it.
- **Security/telemetry:** records carry ids, kinds, closed-vocabulary codes
  and numbers. `source_id`s are already constrained to plain tokens
  (`_SAFE_SOURCE_ID`, `context_assembly.py:572`) and are re-checked before
  emission; anything else is replaced by its kind. No locator, selector,
  payload byte or rendered text is ever emitted, satisfying the issue's
  "no sensitive raw production context in evaluation telemetry" non-goal.
  The replay runner needs `MCTL_TOKEN` with read scope only and performs no
  mutation, so it passes no policy checkpoint (`client.py:261-278` guards
  only writes).
- **Risks and mitigations:**
  - *The extraction silently changes selection.* Mitigated by the pinned
    golden fixture and by a test asserting `assemble()`'s output is
    unchanged for both strategies across every fixture case.
  - *Evaluation breaks an investigation.* Mitigated by its own guarded
    block, which swallows every exception in `shadow` and `on` alike, and by
    the `ISSUE_INVESTIGATOR_CONTEXT_EVAL=off` kill switch read fresh per
    call.
  - *A metric definition drifts and old numbers stop comparing.*
    Mitigated by `evaluator_version` in every record and by the committed
    baseline, which must be regenerated deliberately in the same PR.
  - *Fixtures rot against the real pipeline.* Mitigated by feeding them
    through `run_pipeline` and `seal()` rather than through hand-written
    expectations, so a contract change fails the fixture test.
  - *Labels encode one author's opinion of relevance.* Accepted and stated:
    the fixture set is small, curated and committed, so a disagreement is a
    reviewable diff rather than a hidden constant.
