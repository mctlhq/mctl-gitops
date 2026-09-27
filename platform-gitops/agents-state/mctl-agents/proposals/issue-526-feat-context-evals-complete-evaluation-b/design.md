# Design: issue-526-feat-context-evals-complete-evaluation-b

## Current state

### The contract exists; the producer does not

`docs/adr/015-context-evaluation-contract.md` is committed at status
`proposed`. Its sections 1-5 (identity, metrics, telemetry safety, fixture
contract, outcome-link rule) are normative and this proposal does not reopen
them. Its own "Implementation map" (lines 167-184) lists what it deliberately
deferred: `orchestrator/context_eval.py`, the live emission in
`run_issue_investigator.py`, `tests/fixtures/context_eval/`, the committed
baseline, and the `run_context_eval` replay CLI. A grep for `context_eval`
across the tree hits only that ADR — no Python symbol, no fixture directory,
no env var.

`docs/adr/009-context-snapshot-contract.md` line 517 carries follow-up row
(f), "Measuring retrieval quality, freshness, cost and outcome impact of the
snapshots (b) now persists", pointing at #266 and ADR 015.

### The pipeline is already extractable and pure

`orchestrator/context_assembly.py:996`:

```python
def run_pipeline(candidates: list[CandidateSource], config: AssemblyConfig, now: datetime) -> PipelineOutcome:
```

It copies every `CandidateSource` before any stage rewrites it
(`candidates = [copy.copy(c) for c in candidates]`, line 1017), so the same
input list can be run twice — once per strategy — without the second call
seeing the first call's rewrites. Its docstring says so explicitly and names
ADR 015 sec. 4 as the reason. It returns `PipelineOutcome(candidates,
strategy, budget, conflicts, counters)` (line 981), where `counters` is
`PipelineCounters(dropped_stale, dropped_duplicate, excluded_budget,
truncated_sources, stale_demoted, conflict_sources_capped,
excluded_candidate_ceiling)` (line 965).

Strategy selection is plain string constants, not an enum
(`context_assembly.py:71-84`): `STRATEGY_NAME =
"deterministic-fixed-order"`, `STRATEGY_VERSION = "1.0.0"`,
`RANKED_STRATEGY_NAME = "trust-freshness-ranked"`,
`RANKED_STRATEGY_VERSION = "1.0.0"`, `RANKER_NAME =
"trust-freshness-recency"`, `RANKER_VERSION = "1.0.0"`, `STRATEGIES`,
`STRATEGY_ENV_VAR = "ISSUE_INVESTIGATOR_CONTEXT_STRATEGY"`. The selector is
`AssemblyConfig.strategy` (line 219) with the `ranked` property (line 225) and
`AssemblyConfig.from_env()` (line 229).

The two strategies diverge in exactly the way the metric table cares about:
the default branch drops a stale candidate (`included = False`, `reason_code =
"stale"`, lines 1048-1051), while the ranked branch calls `flag_stale` and
leaves `reason_code = "stale-demoted"` (line 530) on a still-selected source.
That is why `stale_rate` has to accept either signal.

### Metrics today stop short of quality

`AssemblyMetrics` (`context_assembly.py:259`) counts what the pipeline did:
`candidates_total`, `candidates_dropped_pre_budget`, `dropped_stale`,
`dropped_duplicate`, `excluded_budget`, `truncated_sources`, `used_sources`,
`used_bytes`, `assembly_latency_ms`, `collector_calls`, `strategy_name`,
`strategy_version`, `stale_demoted`, `conflict_count`,
`conflict_sources_capped`, plus `candidates_by_kind` / `included_by_kind`.
`to_log_dict()` (line 286) is the only thing the module prints and embeds
`snapshot.to_log_dict()` rather than the snapshot, so no locator, selector or
payload byte escapes. No label, ground-truth, `useful` or `noise` symbol
exists anywhere in `orchestrator/`.

It is printed once, at `run_issue_investigator.py:2019`, inside
`_assemble_context` (line 1943):

```python
print(f"[context] context_assembly={json.dumps(result.metrics.to_log_dict(), sort_keys=True)}")
```

`_assemble_context` already has the failure policy this work must extend: in
`shadow` any exception is caught and logged; in `on` it propagates, because a
sealed snapshot must never describe a prompt that was not built.

### Identity: two hash pairs, one of which is currently discarded

Document identity lives in `orchestrator/context_snapshot.py`: `seal()`
(line 1210) computes `content_hash = _hash_bytes(_canonical_json(payload))`
over `_content_payload` — which excludes `content_hash`, `snapshot_id` and
`created_at` — then `snapshot_id = "cs-" + content_hash[7:23]` (line 1245).
`recompute_content_hash(snapshot)` (line 1266) reproduces the hash. There is
**no** helper that re-derives and checks `snapshot_id` against the `"cs-" +
content_hash[7:23]` rule; ADR 015 sec. 1 requires that comparison, so this
proposal writes it.

Store identity lives in `orchestrator/work_context/snapshots.py`:
`canonical_bytes(snapshot)` (line 88) is `canonical_json(snapshot.to_dict())`
over the *whole* document, and `seal_body` (line 95) sends
`content_hash: hash_bytes(raw)` alongside the base64 canonical bytes.
`SNAPSHOT_ID_PREFIX = "cs_"` (line 42) is the store's id prefix — note the
underscore, distinct from the document's `cs-`. `persist(snapshot, client)`
(line 285) returns a full `SnapshotAnswer` (line 62) carrying `verdict`,
`snapshot_id` (the store's `cs_` id), `content_hash` (the store hash),
`local_snapshot_id`, `local_content_hash`, an opt-in `stored_document`, and a
`stored` property true for `snapshot-sealed` / `snapshot-replayed`.

That answer is then thrown away.
`context_assembly._persist_to_work_item_store` (line 1277) is annotated
`-> None`; it prints the answer via `_emit_snapshot_answer` as a
`WORK_CONTEXT_SNAPSHOT` line and drops it, and its caller (line 1222) ignores
the call's value entirely. `AssemblyResult` (line 310) is `mode`, `snapshot`,
`rendered`, `metrics` — nothing carries the store identity. A grep for
`StoreRef|store_snapshot_id|store_content_hash` across the tree hits only ADR
015. This is deliverable 1's gap, precisely.

### Store reads available for replay

`orchestrator/work_context/client.py` already has everything a read-only
replay needs: `WorkItemClient.get(work_item_id)` (line 162) returning a
`WorkItemAnswer`, and `execution_snapshot(work_item_id, execution_id)` (line
251) returning a `SnapshotAnswer` whose `stored_document` is populated by
`snapshots.answer_from_read` (line 169). `ContextSnapshot.from_dict`
(`context_snapshot.py:871`) rebuilds the document.
`work_context/contract.py` supplies `WorkItem` (line 266) with `state` from
the closed `WORK_ITEM_STATES = {active, waiting, completed, superseded,
archived}` (line 48), `ExecutionRef` (line 166) with `phase` (line 191,
mctl-api's `Pending|Running|Succeeded|Failed|Error`, `compare=False`), and
`latest_execution_id_of` (line 429). `snapshots.is_store_execution` (line 84)
is the only owner of the `we_` prefix check.

### House conventions this follows

- Frozen dataclasses with `to_dict()` / `from_dict()`, closed vocabularies as
  module-level `frozenset`s, and explicit-absence types rather than absent
  keys — the pattern `orchestrator/execution_evidence.py` sets with
  `ExecutionJoin` (line 246), `SnapshotRef` (line 274), `Outcome` (line 460),
  `Gap` (line 481) and `Requirements` (line 507).
- Golden fixtures read from `tests/fixtures/`, e.g.
  `tests/fixtures/context/investigator-snapshot.json` used by
  `tests/test_context_snapshot.py:23` and `tests/test_context_ranking.py:29`.
- Explicit, non-CI regeneration entry points: `_regenerate(names)` guarded by
  `# pragma: no cover` plus `if __name__ == "__main__":` in
  `tests/test_execution_request_replay.py:397-425`; `--update` in
  `tools/diagram_facts.py:248`.
- `argparse` CLIs with a `main()` and validated arguments, e.g.
  `orchestrator/run_usage_collector.py:609`, including the `--dry-run`
  precedent of "no writer token required".
- `inspect.getsource(...)` as a legitimate identity input — already used at
  `run_issue_investigator.py:1998` to feed `prompt_template`.
- ruff `line-length = 120`, mypy configured, Python 3.12, stdlib-only
  preferred (`work_context` is explicitly stdlib-only).

## Proposed solution

Five code changes plus fixtures and docs. Nothing changes what the assembler
selects; nothing new is stored anywhere.

### 1. `StoreRef` and the returned persist answer

Add to `orchestrator/work_context/snapshots.py` — the stdlib-only module that
already owns `canonical_bytes`, `SnapshotAnswer`, `EXECUTION_ID_PREFIX` and
`SNAPSHOT_ID_PREFIX`, so the type sits with the concepts it names:

```python
@dataclass(frozen=True)
class StoreRef:
    """What the store reported for one execution's snapshot: ids and one
    hash. Never a canonical document, never a payload."""
    work_item_id: str
    execution_id: str
    store_snapshot_id: str
    store_content_hash: str
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Any) -> StoreRef: ...

def store_ref_from(snapshot: ContextSnapshot, answer: SnapshotAnswer) -> StoreRef | None:
    """`None` unless the answer is `stored` and its `snapshot_id` is
    `cs_`-prefixed — an unverifiable ref is worse than no ref."""
```

`store_ref_from` reuses the existing `_is_snapshot_id` TypeGuard (line 128) so
the prefix and length rules stay in one place.

In `orchestrator/context_assembly.py`:

- `_persist_to_work_item_store(...) -> SnapshotAnswer | None` — returns the
  answer; every existing early-return and the `SnapshotNotPersisted` raise
  condition stay byte-identical.
- `AssemblyResult` gains `store_ref: StoreRef | None = None` as a defaulted
  final field, so every existing construction (including `assemble()` at line
  1153) compiles unchanged. The annotation is imported under `TYPE_CHECKING`,
  matching the module's existing habit of importing `work_context.snapshots`
  lazily inside functions.
- `assemble_investigator_context` (line 1156) becomes:

```python
    answer = _persist_to_work_item_store(result.snapshot, client)
    if answer is not None:
        from orchestrator.work_context.snapshots import store_ref_from
        return replace(result, store_ref=store_ref_from(result.snapshot, answer))
    return result
```

`AssemblyResult` stays frozen; `dataclasses.replace` is already imported in
`work_context/snapshots.py` and is the idiomatic move here.

### 2. `orchestrator/context_eval.py` — the pure evaluator

Imports: stdlib plus `orchestrator.context_snapshot` and
`orchestrator.work_context.snapshots` (for `StoreRef` and `canonical_bytes`)
only. No network, no filesystem, no `os.getenv`, no clock: every time value is
an argument. `context_assembly` is imported only under `TYPE_CHECKING` and, in
the one place a live caller needs it, passed in as data — so the evaluator
never becomes a second entry point into assembly.

Constants and closed vocabularies:

```python
RECORD_KIND = "context-eval"
EVALUATOR_NAME = "issue-investigator-context-eval"
EVALUATOR_VERSION = "1.0.0"
METRICS_CONTRACT_VERSION = "adr-015/1"          # sec. 2's metric definitions
VERDICT_EVALUATED = "evaluated"
VERDICT_HASH_MISMATCH = "hash-mismatch"
VERDICTS = frozenset({VERDICT_EVALUATED, VERDICT_HASH_MISMATCH})
OUTCOME_SOURCE_LEDGER = "work-item-ledger"
OUTCOME_SOURCE_STATUS_YAML = "status-yaml"
OUTCOMES = frozenset({"succeeded", "failed", "abandoned", "in-progress", "unknown"})
EVIDENCE_KINDS = frozenset({"none", "fixture-baseline", "stored-replay", "live"})
FRESHNESS_STATUSES = frozenset({"fresh", "missing", "stale", "mismatched", "insufficient-observations"})
SAFE_SOURCE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
```

`SAFE_SOURCE_ID` duplicates `context_assembly._SAFE_SOURCE_ID` (line 573)
deliberately, to keep the evaluator's import graph minimal; a test asserts the
two `.pattern` strings are equal, so they cannot drift. The same trick pins
the store hash: `context_eval` computes it as
`hash_bytes(canonical_json(snapshot.to_dict()))` and a test asserts the result
equals `hash_bytes(canonical_bytes(snapshot))` for a real snapshot, so the
duplicated definition can never disagree with the store's.

Types, all frozen with `to_dict`/`from_dict` in the `execution_evidence.py`
style:

- `CaseLabels(useful_source_ids, noise_source_ids, expected_conflict_source_ids)`
  — `None` for an unlabelled case, which is what makes the three ratio metrics
  `null`.
- `IdentityCheck(document_ok, store_ok, mismatch_fields: tuple[str, ...])`.
  `verify_identity(snapshot, store_ref=None)` checks
  `recompute_content_hash(snapshot) == snapshot.content_hash`, then
  `snapshot.snapshot_id == "cs-" + snapshot.content_hash[7:23]`, then, when a
  ref is present, the store hash; `store_snapshot_id` is compared for prefix
  and equality with what the store reported and never recomputed.
- `CoverageEntry(kind, candidates, included, bytes)` — the `coverage_by_kind`
  rows.
- `EvalMetrics` — exactly ADR 015 sec. 2's table, `float | None` for the three
  ratios.
- `OutcomeLink(outcome, outcome_source, work_item_state, execution_phase, reason_code)`.
- `EvidenceIdentity(strategy_name, strategy_version, ranker_name,
  ranker_version, evaluator_name, evaluator_version, metrics_contract_version,
  pipeline_source_hash)`.
- `EvalRecord(record_kind, evaluator_name, evaluator_version, verdict,
  identity: EvidenceIdentity, evidence_kind, context_snapshot_id,
  content_hash, store_ref, metrics: EvalMetrics | None, outcome, observed_at,
  mismatch_fields)` with `to_log_dict()` as the only printing path, mirroring
  `AssemblyMetrics.to_log_dict()`.

Core entry points:

```python
def evaluate(snapshot, *, observed_at, labels=None, assembly=None,
             store_ref=None, outcome=None, evidence_kind="live") -> EvalRecord
def link_outcome(*, work_item_state, execution_phase, status_yaml_status=None,
                 store_execution=True) -> OutcomeLink
def pipeline_source_hash(*functions) -> str
```

`evaluate` returns a `verdict: "hash-mismatch"` record with
`metrics=None` and the two disagreeing field names when identity fails — no
metrics at all, per ADR 015 sec. 1. `assembly` is an optional small
value object (`used_bytes`, `candidates_total`, `dropped_duplicate`,
`assembly_latency_ms`, `capability_calls`) so the evaluator reads the
pipeline's counters without importing the pipeline; when absent, the
byte/latency metrics come from `snapshot.budget` and the latency fields are
`null`.

`link_outcome` is a pure mapping, no I/O: `ExecutionRef.phase` `Succeeded` ->
`succeeded`, `Failed`/`Error` -> `failed`, `Pending`/`Running` ->
`in-progress`; then `WorkItem.state` `superseded`/`archived` -> `abandoned`,
`completed` -> keep the phase's answer, `active`/`waiting` ->
`in-progress`. Anything unrecognised is `unknown` with a reason code, never
silently bucketed. The `.status.yaml` fallback maps `merged` -> `succeeded`,
`rejected`/`needs-triage` -> `failed`, `proposed`/`accepted`/`implementing`/
`review-fixing` -> `in-progress`, and is reachable only when
`store_execution` is false.

`pipeline_source_hash` hashes the concatenated `inspect.getsource` of
`run_pipeline` and the stage functions it calls (`assign_ranks`, `normalize`,
`classify_freshness`, `rank_candidates`, `detect_conflicts`, `flag_stale`,
`deduplicate`, `truncate_to_per_source_limit`, `apply_budget`), following the
`inspect.getsource` precedent at `run_issue_investigator.py:1998`. The
functions are passed in by the caller, keeping the import out of the module.

### 3. Freshness semantics (deliverable 9, the #472 seam)

Also in `context_eval.py`, so #472 imports one module:

```python
DEFAULT_FRESHNESS_WINDOW_SECONDS = 604_800      # 7 days
DEFAULT_MIN_CONSECUTIVE_OBSERVATIONS = 3

@dataclass(frozen=True)
class FreshnessPolicy:
    window_seconds: int = DEFAULT_FRESHNESS_WINDOW_SECONDS
    min_consecutive_observations: int = DEFAULT_MIN_CONSECUTIVE_OBSERVATIONS
    require_pipeline_identity: bool = True
    @classmethod
    def from_env(cls) -> FreshnessPolicy: ...   # CONTEXT_EVAL_* vars

@dataclass(frozen=True)
class EvidenceAssessment:
    status: str          # FRESHNESS_STATUSES
    reason_code: str
    evidence_kind: str
    observations: int
    newest_age_seconds: int | None

def assess_evidence(records, *, expected: EvidenceIdentity, now, policy) -> EvidenceAssessment
```

Precedence is fixed and documented, because "missing" and "mismatched" would
otherwise be order-dependent: empty or `kind == "none"` -> `missing`; then any
declared-identity difference -> `mismatched`; then `require_pipeline_identity`
and a differing `pipeline_source_hash` -> `mismatched`; then newest
observation older than the window -> `stale`; then fewer than
`min_consecutive_observations` newest-first records agreeing on the same
identity -> `insufficient-observations`; else `fresh`. Only `fresh` licenses a
production promotion, and `assess_evidence` never returns `fresh` for
`kind == "none"` by construction. `assess_evidence` takes `now` as an
argument — the evaluator still reads no clock.

This module grants nothing. ADR 015 sec. 6 is restated in its docstring: no
policy or capability-eligibility path may read an `EvalRecord`, and a test
asserts no module under `orchestrator/` imports `context_eval` except the
investigator emission and the replay CLI.

### 4. Guarded live emission

In `orchestrator/run_issue_investigator.py`, immediately after the existing
`[context] context_assembly=` print inside `_assemble_context`:

```python
    _emit_context_eval(result)
    return result

def _context_eval_enabled() -> bool:
    return os.getenv("ISSUE_INVESTIGATOR_CONTEXT_EVAL", "off").strip().lower() == "on"

def _emit_context_eval(result: context_assembly.AssemblyResult) -> None:
    """Best-effort, in EVERY mode — including `on`. A sealed snapshot must
    describe the prompt actually built, so assembly propagates in `on`; an
    evaluation describes nothing the prompt depends on, so it must never be
    able to fail an investigation (ADR 015, issue #526 deliverable 4)."""
    if not _context_eval_enabled():
        return
    try:
        from orchestrator import context_eval
        record = context_eval.evaluate(
            result.snapshot, observed_at=..., store_ref=result.store_ref,
            assembly=context_eval.assembly_counters_from(result.metrics), evidence_kind="live",
        )
        print(f"[context] context_eval={json.dumps(record.to_log_dict(), sort_keys=True)}")
    except Exception as exc:
        print(f"warn: context evaluation failed: {type(exc).__name__}: {exc}")
```

The asymmetry with assembly's `on`-mode propagate rule is deliberate and is
written into the docstring, because a reviewer will otherwise read it as an
inconsistency. A live record carries `outcome: null` and its join keys
(ADR 015 sec. 5) — nothing here reaches for an outcome it cannot know.

### 5. `orchestrator/run_context_eval.py` — read-only stored replay

```
python -m orchestrator.run_context_eval --work-item <id> [--execution we_...] [--json]
```

`main()` follows `run_usage_collector.main()`'s shape. Flow: `WorkItemClient()`
-> `get(work_item)` -> pick the execution (`--execution` when given, else the
newest `we_`-prefixed one whose `execution_snapshot` read succeeds) ->
`ContextSnapshot.from_dict(answer.stored_document)` -> build a `StoreRef` from
the read answer -> `verify_identity` -> `evaluate(..., evidence_kind=
"stored-replay")` -> `link_outcome` from the same `WorkItem` answer -> print
one `context_eval=<json>` line, exit 0. Non-zero with a named reason code when
the work item is absent, the execution carries no snapshot, or the stored
document does not decode. It never calls `seal_snapshot`, never writes
`.status.yaml`, never commits, and needs no writer token — the
`--dry-run` precedent in `run_usage_collector.py`. `stored_document` is
documented "never logged" in `snapshots.py:76`; the CLI honours that and
prints only the record.

`capability_calls` in the record is 0 — it describes the assembly being
scored, which ran long ago. The CLI's own reads are reported as a separate
`replay_store_reads` field so the two are never conflated.

### 6. Fixtures, baseline, and the regeneration gate

```
tests/fixtures/context_eval/cases/01-all-fresh-labelled.json
                            .../02-stale-source.json
                            .../03-duplicate-content.json
                            .../04-budget-exhausted.json
                            .../05-conflicting-prior-proposal.json
                            .../06-candidate-ceiling-overflow.json
                            .../07-unlabelled.json
tests/fixtures/context_eval/baseline.json
tests/test_context_eval.py
```

Each case JSON holds `case_id`, a `config` block, a `candidates` array whose
entries mirror `CandidateSource` with `raw_text` in place of `raw` bytes (short
synthetic strings, no secrets, no real locators), and `labels` (or
`labels: null` for case 07). The harness in `tests/test_context_eval.py`
loads a case, builds `CandidateSource` objects, and for each of
`(STRATEGY_NAME, RANKED_STRATEGY_NAME)` calls the real
`context_assembly.run_pipeline` with an explicitly constructed
`AssemblyConfig` — never `from_env()`, so no ambient
`ISSUE_INVESTIGATOR_CONTEXT_*` value can move the baseline — then
`context_snapshot.seal()` with a fixed `now` and a fixed
`ExecutionCorrelation` (the same literals `tests/test_context_ranking.py:32-58`
already uses), then `context_eval.evaluate(..., evidence_kind=
"fixture-baseline")`.

`baseline.json` is `{case_id: {strategy_name: {metric: value}}}` plus a header
block carrying the `EvidenceIdentity` it was produced under. The suite fails
on any drift and names case, strategy and metric. Regeneration is
`python -m tests.test_context_eval --regenerate [case ...]`, a
`# pragma: no cover` function behind `if __name__ == "__main__":`, exactly the
`tests/test_execution_request_replay.py:397` pattern — never a pytest fixture,
never a CI step.

Cases 02 and 05 are the ones that earn their keep: 02 makes the default
strategy report `dropped_stale` while the ranked strategy reports
`stale_demoted` on a still-selected source, so the `stale_rate` definition is
exercised in both shapes; 05 makes the ranked strategy populate
`snapshot.conflicts` while the default leaves it empty, exercising
`conflicts_detected` / `conflicts_expected_detected` from
`snapshot.conflicts` only.

### 7. Documentation

- `docs/adr/015-context-evaluation-contract.md`: status `proposed` ->
  `accepted`; add **sec. 7, "Evidence freshness and promotion readiness"**
  (the closed status set, the precedence order, the defaults, the
  `require_pipeline_identity` rule, and the explicit statement that #472's
  production path must refuse `evidence.kind = none`). Sections 1-6 are
  untouched; the Implementation map is updated to record what #526 delivered.
- `docs/adr/009-context-snapshot-contract.md`: follow-up row (f) annotated
  with #526 as the delivering issue, matching how row (b) names #431/#490.
- `README.md`: a "Context evaluation" runbook subsection — how to turn on live
  emission, how to read a `context_eval=` line, how to run the replay CLI, how
  to regenerate the baseline, and what #472 requires of the evidence.
- `.env.example`: a new block after the existing "Context assembly pilot"
  block (lines 65-81) for `ISSUE_INVESTIGATOR_CONTEXT_EVAL`,
  `CONTEXT_EVAL_FRESHNESS_WINDOW_SECONDS`,
  `CONTEXT_EVAL_MIN_CONSECUTIVE_OBSERVATIONS` and
  `CONTEXT_EVAL_REQUIRE_PIPELINE_IDENTITY`, all commented out so a copied file
  pins nothing.

## Alternatives

1. **Extend `AssemblyMetrics` in place instead of a new module.** Rejected,
   and ADR 015 already rejected it: `AssemblyMetrics` is built once per
   assembly inside `assemble()` (line 1132), so it cannot score one case under
   both strategies, cannot replay a snapshot sealed days ago, and would push
   label data into the production assembly path — which the ADR forbids
   outright.

2. **Put `StoreRef` in `context_eval.py`.** Rejected: `context_assembly` must
   populate it, so `context_assembly` would import `context_eval`, which needs
   `context_assembly`'s counters and stage functions — a cycle, and it would
   also drag the evaluator into the production assembly import path. Putting
   it in `work_context/snapshots.py` places it beside `canonical_bytes`,
   `SNAPSHOT_ID_PREFIX` and the `SnapshotAnswer` it is built from, in a module
   that is already stdlib-only.

3. **Add a mctl-api table or route for evaluation records.** Rejected for v1,
   as ADR 015 alternative 3 did: the durable artefact already exists (#431,
   #490), and a stored evaluation record would be a derived duplicate that can
   silently disagree with the snapshot it describes. Everything here is either
   a log line or recomputed on demand from the stored snapshot.

4. **Re-implement the pipeline in the fixture harness.** Rejected: it would
   measure a copy of the system, not the system. It is also precisely what the
   `run_pipeline` extraction exists to avoid — that function's own docstring
   says so.

5. **Derive an implementation identity from the git SHA instead of
   `pipeline_source_hash`.** Rejected: a SHA changes on every commit to the
   repo, so every merge would invalidate every observation; a hash over the
   pipeline's own source changes only when the measured code changes. The
   cost — a comment-only edit invalidating evidence — is accepted, made
   explicit, and made relaxable via `require_pipeline_identity`.

6. **Infer the freshness window from observation cadence.** Rejected: the
   issue requires it be explicit rather than inferred, and an inferred window
   silently widens itself whenever observations slow down, which is exactly
   when evidence should be treated as stale.

## Platform impact

**Migrations.** None. No mctl-api schema change, no new route, no gitops
schema change, no `.status.yaml` field.

**Backward compatibility.** Additive throughout.
`ContextSnapshot`'s `_content_payload` inputs are untouched, so every
already-persisted snapshot keeps its identity and no stored document diverges.
`AssemblyResult.store_ref` is a defaulted field, so existing constructors and
every test that builds an `AssemblyResult` keep working.
`_persist_to_work_item_store`'s return type widens from `None` to
`SnapshotAnswer | None` with no change to its side effects or raise
conditions. With `ISSUE_INVESTIGATOR_CONTEXT_EVAL` unset, investigator stdout
is byte-identical to today, which is what the existing
`tests/test_run_issue_investigator.py` suite already pins.

**Resource impact.** Evaluation is arithmetic over an already-built snapshot:
no network, no disk, no subprocess, well under a millisecond per record, one
extra log line per investigation when enabled. The fixture suite runs 7 cases
x 2 strategies through a pure function with no I/O. The replay CLI makes two
to three HTTP GETs per invocation and is operator-triggered only.

**Risks and mitigations.**

- *A new log line leaks a locator, selector or payload.* Mitigated by
  `to_log_dict()` being the only printing path, by `SAFE_SOURCE_ID`
  substitution, and by a test that asserts a locator/selector substring
  planted in a fixture candidate never appears in the emitted JSON.
- *The duplicated `SAFE_SOURCE_ID` / store-hash definitions drift from their
  originals.* Mitigated by two pinning tests comparing the evaluator's regex
  pattern to `context_assembly._SAFE_SOURCE_ID.pattern` and its store hash to
  `hash_bytes(canonical_bytes(snapshot))`.
- *Evaluation failure kills an investigation.* Mitigated by the catch-all
  around `_emit_context_eval` in every mode, plus a test that injects a raising
  `context_eval.evaluate` and asserts the investigation still completes.
- *A baseline is quietly regenerated, so a regression is committed as the new
  truth.* Mitigated by regeneration living behind an explicit `__main__`
  entry point with no pytest or CI caller, and by the baseline header carrying
  the `EvidenceIdentity` it was produced under, so a regeneration under a
  different identity is visible in the diff.
- *#472 reads the evidence as authorization.* Mitigated by ADR 009 sec. 5/6
  being restated in the module docstring, by the new ADR 015 sec. 7 saying
  promotion readiness is the only permitted consumer, and by a test asserting
  no policy or capability module imports `context_eval`.
- *The replay CLI is mistaken for a write path.* Mitigated by the module
  docstring, by requiring no writer token, and by a test asserting a fake
  client receiving any non-GET request fails the test.
- *`pipeline_source_hash` churn makes evidence perpetually `mismatched`.*
  Mitigated by the documented `CONTEXT_EVAL_REQUIRE_PIPELINE_IDENTITY` knob
  and by the runbook telling operators to regenerate the baseline and restart
  the observation window as one deliberate step.
