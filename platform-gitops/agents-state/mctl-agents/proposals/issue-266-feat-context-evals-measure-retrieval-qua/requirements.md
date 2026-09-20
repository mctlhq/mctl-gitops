# Context evaluation: retrieval quality, freshness, cost and outcome impact

## Context

`mctl-agents` can already say, precisely, *what contract ran* (ADR 007,
`orchestrator/resolver.py`'s `ExecutionPlan`) and *what was put in front of the
model* (ADR 009, `orchestrator/context_snapshot.py`'s sealed `ContextSnapshot`,
produced for real by `orchestrator/context_assembly.py` since
mctlhq/mctl-agents#265). What it cannot say is whether that context was any
**good**. `AssemblyMetrics` (`orchestrator/context_assembly.py:188`) already
counts `dropped_stale`, `dropped_duplicate`, `excluded_budget`,
`truncated_sources`, `used_sources`, `used_bytes`, `assembly_latency_ms` and
`collector_calls`, and `run_issue_investigator._assemble_context`
(`orchestrator/run_issue_investigator.py:1650`) prints them as one
`[context] context_assembly={...}` line. Those are *activity* counters: they
describe what the pipeline did, never whether the right evidence was selected,
whether useful evidence was missed, or whether a ranking/filtering/config
change made retrieval worse.

This proposal adds a retrieval/context evaluation layer that is deliberately
**distinct from final model-output evaluation** (issue #60), so the platform can
tell apart bad model reasoning over good context, good reasoning over
missing/stale/noisy context, and retrieval regressions caused by changing
`AssemblyConfig`, the collector order, or a future ranker. It ships a small
curated, labelled fixture set and a checked-in metric baseline so a regression
fails CI instead of being discovered in a bad proposal. No evaluator stack of
any kind exists in this repository today — `grep` for `#60`, an evaluator, a
scorer, a rubric or a token counter returns nothing — so this work defines the
seam #60 will plug into rather than competing with it.

## User stories

- AS a platform engineer changing `AssemblyConfig` or the collector order in
  `orchestrator/context_assembly.py` I WANT a CI check that recomputes
  retrieval metrics against labelled fixtures SO THAT a ranking or filtering
  regression is caught before it reaches a live investigation.
- AS a reviewer of a poor agent proposal I WANT the run's context evaluation
  next to its `ContextSnapshot` SO THAT I can tell whether the model reasoned
  badly or was simply handed stale, noisy or incomplete evidence.
- AS an operator comparing context strategies I WANT per-strategy token/latency
  cost and per-source-kind contribution reported SO THAT I can judge whether a
  richer strategy earns its cost.
- AS the owner of final-output evaluation (#60) I WANT context evaluation to be
  a separate, joinable document keyed on ids I already hold SO THAT I can
  correlate retrieval quality with outcome without adopting a second,
  incompatible evaluator stack.
- AS a security reviewer I WANT evaluation telemetry to be payload-free by
  construction SO THAT no raw production context leaks into an evaluation store.

## Acceptance criteria (EARS)

### Contract and identity

- WHEN a `ContextEvaluation` is sealed THE SYSTEM SHALL compute its
  `content_hash` as `"sha256:" + sha256(canonical JSON)` using
  `orchestrator.context_snapshot.hash_bytes` and `canonical_json`, and SHALL NOT
  introduce a second hashing or serialization convention.
- WHEN a `ContextEvaluation` is sealed THE SYSTEM SHALL derive
  `eval_id = "ce-" + content_hash[7:23]`, mirroring `seal()`'s `cs-` rule in
  `orchestrator/context_snapshot.py:933`.
- WHILE computing `content_hash` THE SYSTEM SHALL exclude `created_at` and
  `cost.assembly_latency_ms`, so that evaluating identical inputs on two
  machines at two wall-clock times yields one `eval_id`.
- WHEN a `ContextEvaluation` document is loaded THE SYSTEM SHALL reject unknown
  top-level or nested keys and an unsupported `api_version`/`kind`, failing
  loudly exactly as `ContextSnapshot.from_dict` does, never falling back to a
  default shape.
- IF a label, outcome or rationale value lies outside its closed vocabulary
  THEN THE SYSTEM SHALL raise a `ContextEvaluationError` rather than coerce it.

### Retrieval quality metrics, distinct from output score

- WHEN a snapshot is evaluated against a label set THE SYSTEM SHALL report
  `selected_precision` (useful-labelled included sources over all included
  sources) and `useful_recall` (useful-labelled included sources over all
  useful-labelled sources in the label set).
- WHEN a snapshot is evaluated without a label set THE SYSTEM SHALL report
  `labelled=false` with `selected_precision` and `useful_recall` set to `null`,
  and SHALL still report `stale_rate`, `duplicate_rate`, `noise_rate`, cost and
  per-source contribution.
- WHEN a snapshot is evaluated THE SYSTEM SHALL report `stale_rate` and
  `duplicate_rate` derived from `ContextSource.freshness.staleness` and
  `selection.reason_code` values the assembler already writes
  (`"stale"`, `"duplicate-content"` in `orchestrator/context_assembly.py:307`
  and `:694`), never from a re-derivation of its own.
- WHEN a label set declares expected evidence that appears in no source THE
  SYSTEM SHALL report it as `missing_evidence_count` with per-entry
  `rationale_code`, so a missing-evidence case is measurable rather than
  invisible.
- WHEN a snapshot is evaluated THE SYSTEM SHALL report, per
  `ContextSource.kind`, the candidate count, included count, included bytes and
  (when labelled) useful count.
- WHILE any evaluation is produced THE SYSTEM SHALL NOT compute, contain or
  name a score of the model's final output; that remains #60's exclusive
  concern.

### Cost

- WHEN a snapshot is evaluated THE SYSTEM SHALL report `used_bytes`,
  `estimated_tokens`, `estimator_name`, `estimator_version`,
  `assembly_latency_ms` and `collector_calls`.
- WHILE reporting `estimated_tokens` THE SYSTEM SHALL carry an explicit
  estimator name and version and SHALL NOT present the figure as a tokenizer
  measurement, because no tokenizer or token accounting exists anywhere in this
  repository.
- WHILE recording cost THE SYSTEM SHALL NOT add any token- or
  context-window-named field to `ContextBudget`, which ADR 009 sec. 6 closes
  against exactly that (`orchestrator/context_snapshot.py:553-560`).

### Fixtures and regression detection

- WHEN the evaluation harness runs THE SYSTEM SHALL execute a checked-in
  curated case set covering, at minimum: relevant and irrelevant log evidence;
  stale versus current deployment evidence; GitHub issue/PR evidence;
  conflicting evidence; duplicated evidence; and a missing-evidence case.
- WHEN a case is evaluated twice from the same inputs THE SYSTEM SHALL produce
  a byte-identical `content_hash` and identical metrics, performing no network
  call and reading no state outside the fixture directory.
- WHEN computed metrics for any case differ from the checked-in baseline THE
  SYSTEM SHALL fail the test suite and name the case and the differing metric.
- IF a change to `AssemblyConfig`, the collector order, freshness table,
  deduplication rule or a future ranker alters selection THEN THE SYSTEM SHALL
  surface that as a baseline diff rather than silently absorbing it.
- WHEN a baseline is intentionally updated THE SYSTEM SHALL require an explicit
  `--update-baseline` invocation of the harness, so the diff is a reviewable
  commit.

### Correlation and the #60 seam

- WHEN a `ContextEvaluation` is sealed THE SYSTEM SHALL carry `snapshot_id`,
  `snapshot_content_hash`, the snapshot's `ExecutionCorrelation` block and its
  `ContextStrategy` block verbatim, so the chain `execution -> context_snapshot
  -> strategy/version -> selected sources -> agent/profile/model -> context
  evaluation` is closed by ids both sides already hold (ADR 009 sec. 4).
- WHEN a downstream outcome becomes known THE SYSTEM SHALL record it as a
  separate append-only `ContextOutcomeLink` document keyed on `eval_id`, and
  SHALL NOT reseal or mutate the `ContextEvaluation`.
- WHEN a `ContextOutcomeLink` is derived THE SYSTEM SHALL join it through the
  additive `context:` block `run_issue_investigator.write_status_yaml`
  (`orchestrator/run_issue_investigator.py:1043`, block written at `:1058-1063`)
  already commits into each proposal's `.status.yaml` — `snapshot_id`,
  `content_hash`, `strategy`, `strategy_version` — so no new cross-process
  callback is invented.
- WHILE recording an outcome THE SYSTEM SHALL restrict it to a closed
  vocabulary drawn from the statuses this repository already writes: the
  `.status.yaml` statuses (`proposed`, `accepted`, `implementing`,
  `review-fixing`, `needs-triage`) plus the terminal set in
  `orchestrator/pr_adoption.py:643` (`merged`, `rejected`, `review-stuck`).
- WHEN #60's final-output evaluator exists THE SYSTEM SHALL be joinable to it
  on `execution.temporal_workflow_id` and `eval_id` without either side
  importing the other.

### Telemetry safety

- WHILE emitting evaluation telemetry THE SYSTEM SHALL emit ids, hashes,
  counts, rates and durations only, and SHALL NOT emit a `locator`, a
  `selector`, retrieved payload bytes, or any free text derived from a source.
- WHEN a production run emits an evaluation line THE SYSTEM SHALL classify it
  `retention: telemetry`, reserving `execution-record` for the durable
  persistence follow-up ADR 009 already names.
- IF the evaluation code raises for any reason during a `shadow`-mode
  investigation THEN THE SYSTEM SHALL log a warning and continue the
  investigation, matching `_assemble_context`'s existing failure policy
  (`orchestrator/run_issue_investigator.py:1640`).

## Out of scope

- Training, shipping or tuning a production reranker, or any embedding,
  semantic or vector retrieval. This proposal measures the existing
  `deterministic-fixed-order` strategy and records where a future ranker's
  identity and score already belong (`ContextStrategy.ranker_name`,
  `Selection.score`).
- Final model-output evaluation, rubrics, LLM-as-judge scoring, or any grading
  of proposal quality — #60's territory.
- A production-scale benchmark, a golden corpus of real issues, or statistical
  significance machinery. The issue explicitly does not require it for v1.
- Declaring one universal retrieval metric sufficient for every agent. Only the
  issue-investigator assembles a snapshot today.
- New mctl-api tables, HTTP endpoints or GitOps schema. Durable persistence of
  snapshots and evaluations stays ADR 009 follow-up (b).
- Adding a real tokenizer, per-model token accounting, or USD cost attribution.
- Adding `loki-logs` or `incident` **collectors** to production assembly; those
  kinds are exercised as fixture-declared candidates only.
- Any change to agent prompts, tools, budgets or the `ISSUE_INVESTIGATOR_CONTEXT_MODE`
  default (`off`).

## Open questions

- **Token estimator fidelity.** No tokenizer exists in the repo and adding one
  would pull a dependency into a deliberately stdlib-only module. Proceeding
  with a declared `bytes-div-4` estimator, versioned so a better one can
  replace it without ambiguity about which figures are comparable.
- **Who authors and maintains labels.** Labels are a human judgement that can
  rot as the strategy changes. Proceeding with hand-authored label sets that
  carry their own `version` and `content_hash`, recorded in every evaluation,
  so a metric produced under old labels is never silently compared to one
  produced under new labels.
- **Where production evaluations durably live.** ADR 009 follow-up (b) already
  owns snapshot persistence and needs an issue. Proceeding with a stdout
  telemetry line only, `retention: telemetry`, and treating durable storage as
  the same follow-up.
- **Whether a separate `ISSUE_INVESTIGATOR_CONTEXT_EVAL` flag is warranted.**
  Proceeding without one: evaluation is emitted whenever
  `ISSUE_INVESTIGATOR_CONTEXT_MODE != "off"`, to avoid a second knob for a
  strictly additive, payload-free log line.
- **Outcome capture mechanics.** The proposal `.status.yaml` is the only honest
  outcome signal today: the investigator already writes a `context:` block into
  it (`run_issue_investigator.py:1058-1063`) and the shepherd/reconciler later
  flip `status` via `proposal_state.update_status_file`. Proceeding with a
  `ContextOutcomeLink` derived by reading those two fields out of one
  `.status.yaml`, rather than inventing a cross-process callback; a scheduled
  sweep that walks every proposal is left to the persistence follow-up.
- **Per-file retrieval precision is unmeasurable today.** `collect_target_repo`
  (`orchestrator/context_assembly.py:475`) emits one `target-repo` source with
  `selector.mode: agent-directed`, because the model Globs/Greps/Reads the
  clone itself and no tool-call hook records which files it opened (ADR 009
  sec. 8, follow-up (e), which still needs an issue). Proceeding by labelling
  `target-repo` at source granularity and stating the limitation in the report
  rather than implying file-level precision this codebase cannot observe.
- **Exact baseline tolerance.** Proceeding with exact equality for every metric
  except `assembly_latency_ms`, which is excluded from both the baseline
  comparison and the content hash and asserted only against a ceiling.
