# Design: issue-266-feat-context-evals-measure-retrieval-qua

## Current state

### What exists — the substrate

`orchestrator/context_snapshot.py` (994 lines, ADR 009, issue #264) is the
frozen, inert contract: `ContextSource` with `Freshness`, `Trust`, `Selection`,
`Redaction`; `ExecutionCorrelation`; `ContextStrategy`; `ContextBudget`;
`EvidenceRef`; `RetentionPolicy`. `seal()` (`:902`) computes
`content_hash = "sha256:" + sha256(canonical JSON of everything except
content_hash/snapshot_id/created_at)` and `snapshot_id = "cs-" + content_hash[7:23]`
(`:932-933`). `hash_bytes` (`:92`) and `canonical_json` (`:102`) are public
aliases deliberately exported so no caller invents a second hash convention —
ADR 009 names two already-disagreeing prompt-hash algorithms as the cautionary
tale. `to_log_dict()` (`:824`) is the payload-free telemetry shape. The module
is stdlib-only, asserted by `tests/test_context_snapshot.py:266`.

`orchestrator/context_assembly.py` (797 lines, issue #265, ADR 009 follow-up
(a)) is the producer. `STRATEGY_NAME = "deterministic-fixed-order"`,
`STRATEGY_VERSION = "1.0.0"` (`:53-54`). Five collectors in fixed order
(`_COLLECTOR_ORDER`, `:553`): `collect_inline_template`, `collect_github_issue`,
`collect_issue_comments`, `collect_target_repo`, `collect_prior_proposal`. The
deterministic pipeline in `assemble()` (`:656`) runs `assign_ranks` (`:274`),
`normalize` (`:282`), `classify_freshness` (`:290`), a stale sweep (`:689-695`
setting `reason_code="stale"`), `deduplicate` (`:307`, setting
`reason_code="duplicate-content"`), `truncate_to_per_source_limit` (`:323`),
and `apply_budget` (`:346`, setting `reason_code="budget-exhausted"`), then
`seal()`. `AssemblyConfig` (`:140`) carries `max_sources=12`,
`max_bytes=120_000`, `max_bytes_per_source=50_000`, `max_candidates=100`,
`max_comments=20`, plus a per-kind `freshness_table` (`:69`), the first three
overridable by `ISSUE_INVESTIGATOR_CONTEXT_MAX_*` env vars (`.env.example:65-67`).

`AssemblyMetrics` (`:187-229`) already counts `candidates_by_kind`,
`included_by_kind`, `candidates_dropped_pre_budget`, `dropped_stale`,
`dropped_duplicate`, `excluded_budget`, `truncated_sources`, `used_sources`,
`used_bytes`, `assembly_latency_ms`, `collector_calls`. Its `to_log_dict()` is
documented as "the only thing this module ever prints".

`orchestrator/run_issue_investigator.py` wires it: `_assemble_context` (`:1580`)
is gated by `ISSUE_INVESTIGATOR_CONTEXT_MODE` in `("off", "shadow", "on")`
(`:135-142`, default `off`), catches every exception in `shadow` and re-raises
in `on` (`:1640-1645`), and prints one line —
`[context] context_assembly={...}` (`:1650`). `write_status_yaml` (`:1043`)
persists an additive `context:` block into the proposal's `.status.yaml`
carrying `snapshot_id`, `content_hash`, `strategy`, `strategy_version`
(`:1058-1063`) and nothing else. That block is the only durable record of
snapshot identity anywhere.

`tests/fixtures/context/investigator-snapshot.json` is the one golden fixture;
`tests/test_context_snapshot.py:184` asserts its `content_hash` byte-for-byte.
Every source in it has `"score": null`.

### What does not exist

- **No evaluator of any kind.** No `evals/` directory, no scorer, rubric,
  judge, benchmark or golden answer set. `grep` for `#60` across `*.py`,
  `*.md` and `*.yaml` returns nothing: final-output evaluation is not in this
  repository, so there is no stack to be incompatible with — only a seam to
  define.
- **No ranker.** `ContextStrategy.ranker_name`/`ranker_version` (`:528-529`)
  and `Selection.score` (`:218`) are declared-but-unpopulated slots, explicitly
  "because no ranker exists yet".
- **No token accounting.** Nothing reads `usage`, `input_tokens` or
  `total_cost_usd` back off the SDK's `ResultMessage`. `budget_usd` values in
  `orchestrator/options.py:98-104` are pre-declared caps, never measured
  actuals. `ContextBudget`'s docstring (`context_snapshot.py:553-560`) is a
  normative prohibition: *"No field here may ever be named after a token or
  context-window concept"*, enforced by `from_dict`'s unknown-key rejection.
- **No metrics client.** Prometheus exists only at
  `orchestrator/temporal/worker.py:451-481` for Temporal SDK metrics. Every
  application "counter" is a stable stdout line prefix that Promtail's metrics
  stage scrapes — see `orchestrator/lifecycle/shadow.py:121` and
  `orchestrator/temporal/workflows/dev_loop.py:1737`
  (`lifecycle_claim_abandoned_total`).
- **No database.** Persistence is GitOps YAML plus GitHub PR state. Sealed
  snapshots are not stored at all; ADR 009 follow-up (b) owns that and still
  needs an issue.
- **No per-file retrieval visibility.** `collect_target_repo` (`:475`) emits a
  single source with `selector.mode: agent-directed`; ADR 009 sec. 8 states
  plainly that a faithful per-file list needs a tool-call hook that does not
  exist.

### Constraints this design must not break

ADR 009's follow-up section (`docs/adr/009-...:454`) lists what a follow-up
**may not reopen**: the field shape and owner table, the
`content_hash`/`snapshot_id` derivation, the step-chaining rule, the "context
relevance is never authorization" boundary, the closed vocabularies **and the
token-budget deferral**, and the no-payload/bounded-length retention rules.
Two live test suites enforce the spirit: `tests/test_context_assembly.py:532`
(stdlib-only import, so the 256Mi worker of ADR 008 can import it) and `:560`,
`:572` (module source contains no authorization vocabulary and imports no
policy symbol).

## Proposed solution

Add a **separate, additive, read-only evaluation layer** that consumes a sealed
`ContextSnapshot` plus an optional label set and produces its own sealed
document. Nothing in `context_snapshot.py` or `context_assembly.py` changes
shape; the only production edit is one extra log line.

### 1. `orchestrator/context_eval.py` — the contract (new, stdlib-only)

`API_VERSION = "context.mctl.ai/v1alpha1"`, `KIND = "ContextEvaluation"`, with
the same `SUPPORTED_API_VERSIONS` allow-list, `_reject_unknown_keys` /
`_require_*` validators and `ContextEvaluationError` fail-closed discipline as
`context_snapshot.py`. It imports `hash_bytes`, `canonical_json`,
`ExecutionCorrelation` and `ContextStrategy` from `orchestrator.context_snapshot`
— never a second hash or serialization rule.

Frozen dataclasses:

- `SourceLabel(source_id, label, rationale_code)` with closed
  `LABEL_VALUES = {"useful", "irrelevant", "stale", "duplicate", "conflicting"}`.
- `MissingEvidence(evidence_id, kind, rationale_code)` — evidence a case
  declares *should* have been retrievable but that appears in no source. `kind`
  is validated against `context_snapshot.SOURCE_KINDS`.
- `LabelSet(labelset_id, version, content_hash, labels, expected_missing)`.
  `content_hash` is over the canonical JSON of the labels themselves, so a
  metric computed under one label revision is never silently compared to one
  computed under another.
- `RetrievalQuality(labelled, selected_precision, useful_recall, stale_rate,
  duplicate_rate, noise_rate, conflict_rate, missing_evidence_count)` — the
  four rate fields are always populated; the two labelled fields are `None`
  when `labelled=False`.
- `ContextCost(used_bytes, estimated_tokens, estimator_name, estimator_version,
  assembly_latency_ms, collector_calls, capability_calls)`.
- `SourceContribution(kind, candidate_count, included_count, included_bytes,
  useful_count)` — one entry per `ContextSource.kind`, sorted by kind for hash
  stability.
- `ContextEvaluation(api_version, kind, eval_id, content_hash, created_at,
  snapshot_id, snapshot_content_hash, execution, strategy, labelset_ref,
  quality, cost, contributions, retention)`.

`seal_evaluation(...)` mirrors `seal()`: hash the canonical JSON of every field
**except `content_hash`, `eval_id`, `created_at` and
`cost.assembly_latency_ms`**, then `eval_id = "ce-" + content_hash[7:23]`.
Excluding latency is the one deliberate extension of `seal()`'s rule and is why
a case evaluated on a fast and a slow machine yields one `eval_id`; it is
documented in the module docstring and in ADR 012 alongside `created_at`.

Metric definitions, all computed from fields the assembler already writes —
never re-derived:

```
included      = [s for s in snapshot.sources if s.selection.included]
considered    = snapshot.sources
useful        = labels where label == "useful"
selected_precision = |included ∩ useful| / |included|            (None if unlabelled)
useful_recall      = |included ∩ useful| / |useful|              (None if unlabelled)
stale_rate      = |{s in considered: s.freshness.staleness == "stale"}| / |considered|
duplicate_rate  = |{s in considered: s.selection.reason_code == "duplicate-content"}| / |considered|
noise_rate      = |included ∩ irrelevant| / |included|           (0.0 if unlabelled)
conflict_rate   = |included ∩ conflicting| / |included|          (0.0 if unlabelled)
```

Zero-denominator cases return `None`, never a silent `0.0`.

`estimate_tokens(byte_count)` is `byte_count // 4` under
`ESTIMATOR_NAME = "bytes-div-4"`, `ESTIMATOR_VERSION = "1.0.0"`. Both names ride
on every evaluation precisely so the figure can never be mistaken for a
tokenizer measurement, and so a future real tokenizer bumps the version rather
than silently redefining a comparison. **No token-named field is added to
`ContextBudget`** — this is the whole reason cost lives in a new document.

`ContextOutcomeLink(eval_id, snapshot_id, temporal_workflow_id, service, slug,
outcome, observed_at, pr_url)` is a second, separate, append-only document.
`OUTCOME_VALUES` is the union of the `.status.yaml` statuses (`proposed`,
`accepted`, `implementing`, `review-fixing`, `needs-triage`) and
`orchestrator/pr_adoption.py:643`'s `TERMINAL_STATUSES` (`merged`, `rejected`,
`review-stuck`). Keeping it separate is what lets the evaluation seal once, at
evaluation time, and never be mutated when the outcome lands hours later.

`to_log_dict()` on both documents emits ids, hashes, counts, rates and
durations only — no `locator`, no `selector`, no payload — matching
`ContextSnapshot.to_log_dict` and enforced by test.

### 2. `orchestrator/context_eval_cases.py` — the fixture-driven harness (new)

The insight that makes this shippable without network access or new collectors:
what #266 actually wants measured is the **deterministic filtering and ranking
pipeline**, not the fetchers. So a case declares `CandidateSource` values
directly and feeds them through the *real* exported stage functions —
`assign_ranks`, `normalize`, `classify_freshness`, the stale sweep,
`deduplicate`, `truncate_to_per_source_limit`, `apply_budget` — then `seal()`s
with a fixture `ExecutionCorrelation`. This exercises the production code path
verbatim, is fully reproducible, and reaches `SOURCE_KINDS` members
(`loki-logs`, `incident`, `github-pr`, `gitops-file`) that the contract already
allows but for which #265 deliberately shipped no collector.

A small refactor supports it: `assemble()` (`:656`) currently inlines the stale
sweep and the metrics construction. Extract the portion after collection into
`run_pipeline(candidates, config, now) -> (sources, budget, PipelineCounters)`
and have both `assemble()` and the harness call it. `assemble()`'s observable
behaviour, and the golden fixture's hash, are unchanged — asserted by the
existing `tests/test_context_assembly.py` suite plus the byte-for-byte golden
in `tests/test_context_snapshot.py:184`.

### 3. `tests/fixtures/context/eval/` — the curated case set (new)

```
tests/fixtures/context/eval/
  cases/logs-relevant-and-irrelevant/{case.json,labels.json}
  cases/deployment-stale-vs-current/{case.json,labels.json}
  cases/github-issue-and-pr-evidence/{case.json,labels.json}
  cases/conflicting-and-duplicate-evidence/{case.json,labels.json}
  cases/missing-evidence/{case.json,labels.json}
  cases/budget-truncation-cost/{case.json,labels.json}
  baseline.json
```

`case.json` declares `now`, an `AssemblyConfig` override and an ordered list of
candidate specs (`source_id`, `kind`, `locator`, `selector`, `body`,
`observed_at`, `trust`, `reason_code`, `strategy_step`). Bodies are short,
synthetic, obviously-fake strings — never a copied production log line, which
the issue's third non-goal forbids. The six cases map one-to-one onto the
issue's required coverage, with `budget-truncation-cost` added to exercise
truncation and the cost block.

`baseline.json` records, per case, the sealed `snapshot_id`, snapshot
`content_hash`, `eval_id`, evaluation `content_hash`, and every metric except
`assembly_latency_ms`.

### 4. `tools/run_context_eval.py` — the runner (new)

Mirrors `tools/record_workflow_history.py`'s convention. `python -m
tools.run_context_eval` loads every case, runs the pipeline, evaluates, and
prints a JSON report plus a human-readable per-case table.
`--update-baseline` rewrites `baseline.json`; `--case <id>` narrows.
Regenerating a baseline is therefore always an explicit, reviewable commit.

### 5. `tests/test_context_eval.py` — the regression gate (new)

The mechanism that satisfies "staleness/noise/duplicate regressions are
detectable": a parametrized test over every case asserting computed metrics
equal `baseline.json` exactly. Because the pipeline is deterministic and
latency is excluded, exact equality is correct — no tolerance window that could
mask a small real regression. Changing `AssemblyConfig` defaults, the
`freshness_table`, `_COLLECTOR_ORDER`, the dedup rule or a future ranker moves
a metric and fails CI with the case and metric named.

### 6. Production emission — one line

In `run_issue_investigator._assemble_context`, after the existing
`[context] context_assembly=` print (`:1650`), add:

```python
evaluation = context_eval.evaluate(result.snapshot, result.metrics, labelset=None, now=...)
print(f"[context] context_eval={json.dumps(evaluation.to_log_dict(), sort_keys=True)}")
```

Inside the same `try`, so `shadow` mode's existing catch-and-continue policy
(`:1640-1645`) covers it and a telemetry feature can never fail an
investigation. `labelset=None` is the honest production path: no labels exist
in production, so `labelled=false` and precision/recall are `null`, while
staleness, duplicate rate, cost and per-kind contribution are real. The stable
`[context] context_eval=` prefix is the Promtail-scrapeable counter surface
this repo already uses; no metrics client is introduced. No new env var — the
line rides the existing `ISSUE_INVESTIGATOR_CONTEXT_MODE` gate.

### 7. `docs/adr/012-context-evaluation-contract.md` — the ADR (new)

This repo's convention is that a contract gets an ADR. ADR 012 records: the
separation of context evaluation from output evaluation and the join keys for
#60; the hash rule and the `created_at` + `assembly_latency_ms` exclusion; the
closed label/outcome vocabularies; why cost is estimated rather than measured;
why `ContextBudget` is not extended; the payload-free rule; and the honest
statement that `target-repo` precision is source-granular, not file-granular,
until ADR 009 follow-up (e) lands.

### Correlation chain, closed

```
temporal_workflow_id (issue_ref.workflow_id_for)
  -> ExecutionCorrelation {agent, environment, definition_version/hash,
                           profile_version/hash, release_revision,
                           target_repository_sha}          [ADR 007 pins]
  -> snapshot_id / content_hash                            [ADR 009 seal]
  -> ContextStrategy {name, version, ranker_name, ranker_version}
  -> ContextSource[] {included, rank, reason_code, freshness, trust}
  -> eval_id / ContextEvaluation {quality, cost, contributions}   [this proposal]
  -> ContextOutcomeLink {outcome}                                 [this proposal]
  -> final execution evaluation                                   [#60, joins on
                                                                   workflow_id + eval_id]
```

Two links are already persisted today and are reused rather than re-invented:
`.status.yaml`'s `context:` block (`run_issue_investigator.py:1058-1063`) holds
`snapshot_id`, and the same file's `status` field, flipped later by
`proposal_state.update_status_file`, holds the outcome. A
`derive_outcome_link(status_yaml)` helper reads exactly those two fields.

### The #60 boundary, made testable

| Concern | Owner | Never touches |
|---|---|---|
| Was the right evidence selected, fresh, non-duplicated, affordable? | `context_eval` (this proposal) | model output, proposal text |
| Was the model's answer good? | #60 | retrieval internals |
| What was put in front of the model? | `context_snapshot` (ADR 009) | scoring of any kind |
| What contract ran? | `resolver` (ADR 007) | context |

Enforced the way this repo already enforces the authorization boundary: a test
greps `context_eval.py`'s own source for output-grading vocabulary (`answer`,
`response_quality`, `output_score`, `rubric`, `judge`) and fails on a hit,
mirroring `tests/test_context_assembly.py:560`.

## Alternatives

1. **Extend `AssemblyMetrics` / `ContextSnapshot` with quality and cost
   fields.** Rejected on three grounds. ADR 009's follow-up section forbids a
   follow-up from reopening the field shape, the closed vocabularies or the
   token-budget deferral, and `ContextBudget`'s docstring is an explicit
   prohibition on token-named fields; `from_dict`'s unknown-key rejection would
   have to be weakened to admit them. The snapshot is sealed at assembly time,
   before any outcome exists, so an outcome field would force a reseal and
   break `snapshot_id` stability. And quality depends on labels that live
   outside the run entirely — putting them in the snapshot would make the same
   execution hash differently as labels are revised.

2. **LLM-as-judge for relevance, scoring each source with a model call.**
   Rejected for v1. It is nondeterministic, so the baseline-diff mechanism that
   makes regressions detectable would degrade into a tolerance window;
   it consumes the very budget `orchestrator/options.py` caps; and it would put
   a model-derived score on the same `Selection.score` field ADR 009 sec. 5
   rules must never reach an authorization path. Deterministic labelled
   fixtures give sharper regression signal at zero model cost. A judge remains
   a clean follow-up: it would populate `Selection.score` with a declared
   `ranker_name`/`ranker_version`, which the contract already anticipates.

3. **A generic evaluation service or new mctl-api table for evaluations.**
   Rejected: ADR 009's non-goals explicitly exclude a new HTTP API and any
   mctl-api schema migration, and snapshot persistence is already an unowned
   follow-up (b). Shipping an evaluation store before a snapshot store would
   invert the dependency. A stdout line with a stable prefix is the mechanism
   this repo already uses for application counters
   (`lifecycle/shadow.py:121`, `dev_loop.py:1737`).

4. **Evaluate by replaying real recorded investigations.** Rejected: the only
   recorded fixtures are Temporal histories (`tests/fixtures/histories/`), which
   carry no context sources; capturing real ones would mean storing production
   issue bodies and logs, which the issue's third non-goal forbids outright.
   Synthetic cases are reproducible, shareable and safe.

## Platform impact

- **Migrations:** none. No mctl-api table, no GitOps schema change, no manifest
  field change. `agents/_manifests/*/agent.yaml`, `orchestrator/resolver.py`,
  `orchestrator/manifest.py` and every workflow are untouched. No new
  `ISSUE_INVESTIGATOR_*` env var; `.env.example` is unchanged.
- **Backward compatibility:** strictly additive. `ContextSnapshot`'s shape,
  `seal()`'s hash rule and the golden fixture's `content_hash` are unchanged,
  and the existing suites assert it. The only production behaviour change is
  one extra stdout line, emitted only when `ISSUE_INVESTIGATOR_CONTEXT_MODE`
  is already not `off` — and that flag defaults to `off`, so the default
  deployment is byte-identical. The `run_pipeline` extraction is a pure
  refactor with no observable change.
- **Resource impact:** negligible. Evaluation is arithmetic over a source list
  of at most `max_candidates=100` entries plus one sha256 over a few kilobytes
  of JSON — microseconds beside the existing assembly. No new dependency:
  `context_eval.py` is stdlib-only, keeping the 256Mi Temporal worker of ADR
  008 importable, asserted by a test copied from
  `tests/test_context_assembly.py:532`. Fixtures add roughly 20-30 KB to the
  repo. Test-suite time grows by a handful of parametrized cases.
- **Risks and mitigations:**
  - *A token- or cost-named field creeps back into `ContextBudget`, violating a
    normative ADR clause.* Mitigated by putting every cost field in
    `ContextCost` inside the new module, and by a test asserting
    `ContextBudget`'s field set is unchanged.
  - *The estimated token figure is read as a real measurement.* Mitigated by
    `estimator_name`/`estimator_version` on every record, a module docstring
    stating no tokenizer exists in this repo, and ADR 012 saying so normatively.
  - *Evaluation telemetry becomes a covert payload store.* Mitigated the way
    ADR 009 mitigates it: unknown-key rejection in `from_dict`, labels keyed by
    `source_id` only, and a test mirroring
    `tests/test_context_assembly.py:288` asserting no `locator`, `selector` or
    payload text reaches `to_log_dict()`.
  - *Labels rot as the strategy evolves, so a baseline diff means nothing.*
    Mitigated by `LabelSet.version` and `LabelSet.content_hash` riding on every
    evaluation, and by `--update-baseline` forcing an explicit commit.
  - *Baseline churn makes CI noisy.* Mitigated by excluding
    `assembly_latency_ms` from both the content hash and the baseline
    comparison — the only nondeterministic quantity in the pipeline.
  - *Metrics over-claim precision the codebase cannot observe.* Mitigated by
    stating in ADR 012 and in the runner's report that `target-repo` is scored
    at source granularity, because `selector.mode: agent-directed` is all ADR
    009 sec. 8 permits until follow-up (e) exists.
  - *The eval module drifts toward authorization or output grading.* Mitigated
    by two source-grepping tests in the style this repo already uses
    (`tests/test_context_assembly.py:560`, `:572`).
- **Security:** no new network call, no new credential, no new tool permission,
  no change to any agent's prompt or allowed tools. Every fixture body is
  synthetic. Evaluation is non-authoritative by construction and records no
  allow/deny/permit/grant decision, preserving ADR 009 sec. 5's boundary.
