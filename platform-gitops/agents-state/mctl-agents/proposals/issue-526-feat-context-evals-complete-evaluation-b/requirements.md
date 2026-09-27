# Context evaluation, baseline and replay evidence for context promotion

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

## Context

`docs/adr/015-context-evaluation-contract.md` is committed and normative: it
fixes the identity rules, the metric table, the telemetry-safety rule, the
fixture contract and the outcome-link rule for a retrieval-quality evaluator.
Its own "Implementation map" section states which parts landed
(`docs/adr/015-*.md` itself plus the behaviour-preserving `run_pipeline`
extraction in `orchestrator/context_assembly.py:996`) and which did not: the
evaluator module, the live emission, the fixture corpus, the committed
baseline and the replay CLI. mctlhq/mctl-agents#266 was closed on that partial
state. This proposal carries the undelivered half against current main and
adds one thing #266 did not specify: the freshness semantics by which
mctlhq/mctl-agents#472 decides whether the evidence in front of it is good
enough to promote a context strategy to production.

Without it, the platform can say what the assembler *did*
(`AssemblyMetrics.to_log_dict()`, `orchestrator/context_assembly.py:286`) but
not whether the evidence the model needed was actually selected, cannot score
the same input under both `deterministic-fixed-order` and
`trust-freshness-ranked`, and cannot replay a snapshot sealed days ago. #472's
production promotion path is therefore gated on this work: it must not accept
`evidence.kind = none`, and "stale" or "mismatched" must be defined here
rather than guessed there. Today the store identity of a persisted snapshot is
computed and then thrown away —
`context_assembly._persist_to_work_item_store` (line 1277) returns `None` and
the `SnapshotAnswer` reaches only a `WORK_CONTEXT_SNAPSHOT` log line — so even
the join key an evaluation needs is unavailable to its caller.

## User stories

- AS a platform engineer I WANT a retrieval-quality record emitted next to
  every sealed `ContextSnapshot` SO THAT I can tell bad reasoning over good
  context apart from good reasoning over missing, stale, noisy or duplicated
  context.
- AS a platform engineer I WANT a committed baseline over curated fixture
  cases, scored under both strategies through the real pipeline SO THAT a
  ranking, filter or config regression fails CI instead of shipping.
- AS an operator I WANT `python -m orchestrator.run_context_eval --work-item
  <id> [--execution we_...]` SO THAT I can score a snapshot that was sealed
  days ago, read-only, with no rerun of the investigation.
- AS the owner of #472 I WANT evidence that names the strategy, the strategy
  version and the implementation identity it was produced by, plus an explicit
  freshness window and minimum observation count SO THAT production promotion
  refuses missing, stale or mismatched evidence by rule rather than by
  judgement.
- AS a security reviewer I WANT every evaluation record to carry only ids,
  kinds, closed-vocabulary codes, counts and ratios SO THAT a measurement path
  never becomes a payload exfiltration path.
- AS an investigator-agent operator I WANT evaluation to be strictly
  best-effort SO THAT a metric bug can never fail an investigation that would
  otherwise have succeeded.

## Acceptance criteria (EARS)

### Store answer and `StoreRef`

- WHEN `context_assembly._persist_to_work_item_store` receives a
  `SnapshotAnswer` from `work_context.snapshots.persist` THE SYSTEM SHALL
  return that answer to its caller instead of discarding it, preserving the
  existing `SnapshotNotPersisted` raise conditions unchanged.
- WHEN `assemble_investigator_context` completes with `answer.stored` true and
  a `cs_`-prefixed `answer.snapshot_id` THE SYSTEM SHALL populate
  `AssemblyResult.store_ref` with `StoreRef(work_item_id, execution_id,
  store_snapshot_id, store_content_hash)` taken from the snapshot's
  `work_context` and that answer.
- IF no store execution exists, or the persist answer was not `stored`, or the
  reported store snapshot id is not `cs_`-prefixed, THEN THE SYSTEM SHALL set
  `AssemblyResult.store_ref` to `None` and SHALL NOT fail assembly for that
  reason alone.
- WHILE a `StoreRef` exists anywhere in the system THE SYSTEM SHALL keep it
  free of any payload, locator, selector, canonical document or rendered text
  field.

### Identity verification

- WHEN an evaluation begins THE SYSTEM SHALL verify the document identity
  first: `context_snapshot.recompute_content_hash(snapshot) ==
  snapshot.content_hash` and `snapshot.snapshot_id == "cs-" +
  snapshot.content_hash[7:23]`.
- WHEN a `StoreRef` is present THE SYSTEM SHALL also verify the store identity:
  `hash_bytes(canonical_bytes(snapshot)) == store_ref.store_content_hash`.
- WHILE verifying the store identity THE SYSTEM SHALL treat
  `store_snapshot_id` as opaque — carried and compared against what the store
  reported, never recomputed locally.
- IF either identity pair disagrees THEN THE SYSTEM SHALL emit a record with
  `verdict: "hash-mismatch"`, the names of the two disagreeing fields, and no
  metrics block at all.
- WHEN no `StoreRef` is available THE SYSTEM SHALL still verify the document
  identity, record `store_ref: null`, and proceed to metrics.

### Metrics

- WHEN both applicable identities hold THE SYSTEM SHALL compute exactly the
  metrics named in ADR 015 sec. 2: `selected_precision`, `useful_recall`,
  `f1`, `missing_expected`, `stale_rate`, `duplicate_rate`, `noise_rate`,
  `context_bytes`, `context_tokens_estimate`, `assembly_latency_ms`,
  `capability_calls`, `coverage_by_kind`, `conflicts_detected`,
  `conflicts_expected_detected` and `conflict_sources_capped`.
- IF a case carries no labels THEN THE SYSTEM SHALL report
  `selected_precision`, `useful_recall` and `f1` as `null`, never as `0.0` or
  `1.0`.
- WHEN computing `stale_rate` THE SYSTEM SHALL count a selected source whose
  `freshness.staleness == "stale"` OR whose `selection.reason_code ==
  "stale-demoted"`, because the ranked strategy demotes rather than drops.
- WHEN computing `context_tokens_estimate` THE SYSTEM SHALL derive it as
  `ceil(budget.used_bytes / 4)` and label it an estimate; it SHALL NOT be
  presented as a billed token count, which stays with
  `orchestrator/usage_ledger.py`.
- WHEN computing conflict metrics THE SYSTEM SHALL read `snapshot.conflicts`
  only and SHALL NOT re-derive conflicts from any text.
- WHILE evaluating THE SYSTEM SHALL perform no network call, no filesystem
  read, no clock read and no subprocess call inside the evaluator module.

### Telemetry safety

- WHILE emitting any evaluation record THE SYSTEM SHALL emit only ids, kinds,
  closed-vocabulary codes, counts and ratios, and SHALL NOT emit a `locator`,
  a `selector`, a payload byte or any rendered text.
- IF a `source_id` does not match the safe-token pattern shared with
  `context_assembly._SAFE_SOURCE_ID` (`^[A-Za-z0-9._-]{1,128}$`) THEN THE
  SYSTEM SHALL emit the source's `kind` in its place.
- WHEN emitting a record THE SYSTEM SHALL name itself with `record_kind:
  "context-eval"`, `evaluator_name` and `evaluator_version`.

### Outcome linking

- WHEN a `we_`-prefixed execution exists for the evaluated snapshot THE SYSTEM
  SHALL resolve the outcome from the canonical ledger: `WorkItem.state` plus
  the matching `ExecutionRef.phase`, joined on `execution_id`,
  `prior_execution_ids` and `resumed_from_snapshot_id`, recording
  `outcome_source: "work-item-ledger"`.
- IF and only if no store execution exists THEN THE SYSTEM SHALL fall back to
  the published proposal's `.status.yaml` `status` field and SHALL record
  `outcome_source: "status-yaml"` so the weaker link is visible.
- WHEN a live evaluation is emitted during an investigation THE SYSTEM SHALL
  set `outcome: null` and carry its join keys (`execution_id`,
  `context_snapshot_id`), because the outcome is not knowable yet.
- IF neither source yields a recognised value THEN THE SYSTEM SHALL record
  `outcome: "unknown"` with a reason code, never an absent key.

### Live emission

- WHEN `ISSUE_INVESTIGATOR_CONTEXT_EVAL` is `on` and context assembly produced
  a result THE SYSTEM SHALL print one line
  `[context] context_eval=<json>` after the existing
  `[context] context_assembly=<json>` line in
  `run_issue_investigator._assemble_context`.
- WHILE `ISSUE_INVESTIGATOR_CONTEXT_EVAL` is unset or `off` THE SYSTEM SHALL
  produce byte-identical investigator output to today.
- IF evaluation or emission raises for any reason THEN THE SYSTEM SHALL catch
  it, print one bounded `warn:` line, and continue the investigation — in
  every context mode, including `on`.

### Fixtures and baseline

- WHEN the fixture suite runs THE SYSTEM SHALL drive every case through the
  real `context_assembly.run_pipeline` under both `deterministic-fixed-order`
  and `trust-freshness-ranked`, with a fixed `now`, a fixed
  `ExecutionCorrelation` and an explicitly constructed `AssemblyConfig`, and
  SHALL NOT re-implement any pipeline stage in test code.
- WHILE the fixture suite runs THE SYSTEM SHALL ignore every
  `ISSUE_INVESTIGATOR_CONTEXT_*` environment variable, so no ambient
  configuration can move the baseline.
- WHEN any metric for any (case, strategy) pair differs from
  `tests/fixtures/context_eval/baseline.json` THE SYSTEM SHALL fail the suite
  and name the case, the strategy and the metric.
- WHEN the baseline is regenerated THE SYSTEM SHALL require an explicit,
  deliberate invocation and SHALL NOT regenerate it as a side effect of a
  normal test run or of CI.
- WHEN cases are curated THE SYSTEM SHALL include at least: a labelled
  all-fresh case, a stale-source case that distinguishes the two strategies,
  a duplicate-content case, a budget-exhaustion case, a
  conflicting-prior-proposal case, a candidate-ceiling-overflow case, and one
  deliberately unlabelled case.

### Replay CLI

- WHEN `python -m orchestrator.run_context_eval --work-item <id>` is run THE
  SYSTEM SHALL read the work item and its executions, select the most recent
  execution carrying a stored snapshot, rebuild that snapshot with
  `ContextSnapshot.from_dict`, verify both identities, evaluate, link the
  outcome and print one `context_eval=<json>` line.
- WHEN `--execution we_...` is supplied THE SYSTEM SHALL evaluate exactly that
  execution and SHALL fail with a non-zero exit and a named reason if it
  carries no stored snapshot.
- WHILE replaying THE SYSTEM SHALL perform no write of any kind: no seal, no
  POST, no `.status.yaml` update, no gitops commit, and SHALL require no
  writer token.
- WHILE replaying THE SYSTEM SHALL report `capability_calls: 0` for the
  assembly it is scoring, counting only the store round trips it makes itself
  in a separate field.
- IF the stored document does not decode into a valid `ContextSnapshot` THEN
  THE SYSTEM SHALL exit non-zero with a reason code and SHALL NOT print the
  stored document.

### Evidence freshness for #472 promotion

- WHEN evidence is produced THE SYSTEM SHALL record its `kind` from the closed
  set `{"none", "fixture-baseline", "stored-replay", "live"}`.
- WHEN evidence is produced THE SYSTEM SHALL record the evaluated
  `strategy_name`, `strategy_version`, `ranker_name`, `ranker_version`, the
  strategy version's catalog identity `strategy_content_hash` and
  `strategy_implementation_hash` (#472's `contentHash`/`implementationHash`
  for that name/version), and the evaluator identity `evaluator_name`,
  `evaluator_version`, `metrics_contract_version`. `pipeline_source_hash` is
  recorded as a diagnostic only and is never an assessment input.
- WHEN the catalog identity is needed THE SYSTEM SHALL obtain it in the
  caller (the live emitter, the fixture harness, the replay CLI) through
  `orchestrator.context_release.load_version(name, version)`, imported inside
  the function body as `context_assembly` already does for its non-stdlib
  helpers, and pass it to the evaluator; `context_eval` itself stays
  stdlib-only and never reads the catalog. IF the version cannot be loaded
  (absent, `disabled`, or its recomputed `implementationHash` differs from
  the committed one) THEN the record SHALL carry empty catalog identity and
  assessment SHALL return `mismatched` with reason code
  `catalog-identity-unavailable`.
- WHEN a promotion candidate is assessed THE SYSTEM SHALL return a status from
  the closed set `{"fresh", "missing", "stale", "mismatched",
  "insufficient-observations"}` with a machine-readable reason code.
- IF evidence is absent, or its `kind` is `none` THEN THE SYSTEM SHALL return
  `missing`, and production promotion SHALL refuse.
- IF the newest observation is older than the configured freshness window
  THEN THE SYSTEM SHALL return `stale`.
- IF fewer than the configured minimum number of consecutive observations
  agree on the same strategy and implementation identity THEN THE SYSTEM SHALL
  return `insufficient-observations`.
- IF any declared identity field of the evidence differs from the promotion
  candidate's THEN THE SYSTEM SHALL return `mismatched`.
- IF the evidence's `strategy_content_hash` or `strategy_implementation_hash`
  differs from the promotion candidate's catalog identity THEN THE SYSTEM
  SHALL return `mismatched`, even if every declared name and version matches.
- WHILE the freshness window and minimum-observation count are in force THE
  SYSTEM SHALL take them as explicit parameters from the caller, SHALL export
  ADR 019's v1 values as named constants for that caller to pass, SHALL read
  no environment variable for them, and SHALL NOT infer either from
  observation history. Changing them is an ADR 019 amendment.
- WHILE assessing evidence THE SYSTEM SHALL only report a status and reason
  code; deciding that a `fresh` assessment permits a production promotion is
  #472 Slice C's (mctlhq/mctl-agents#528), not this module's.
- WHILE any of this exists THE SYSTEM SHALL keep retrieval quality
  non-authoritative: no policy, capability-eligibility or authorization
  decision SHALL read an evaluation record (ADR 009 sec. 5/6, ADR 014).

## Out of scope

- Context strategy promotion, rollback or enforcement itself — that is
  mctlhq/mctl-agents#472. This proposal produces and assesses the evidence;
  it does not consume it to change what ships.
- A new snapshot or evidence store, and any new mctl-api route or table. The
  durable artefact already exists (#431, proven live in #490).
- Dashboards, alerts or any Grafana/VictoriaMetrics wiring.
- Learned ranking, a reranker, or a model judge anywhere in the evaluation
  path.
- Automatic promotion on green evidence.
- Replacing or re-implementing final model-output scoring (#60).
- Changing what the assembler selects, or reopening `ContextSnapshot`'s schema
  (ADR 009) or its ranking behaviour (ADR 009 amendment 1, #471).
- Reopening ADR 015 sec. 1 through 5, which are normative for this work.

## Open questions

- **Label storage.** ADR 015 forbids label data in the production assembly
  path but does not say where labels live. Taken as: labels live only in the
  fixture JSON under `tests/fixtures/context_eval/cases/`, and the evaluator
  accepts them as an optional argument, so a live record is always unlabelled
  and reports `null` for precision/recall/f1.
- **Freshness window and minimum observations.** Resolved by ADR 019 (#472
  Slice A): 7 days (604800s) and 3 consecutive observations are v1 promotion
  policy constants. This module exports them as `ADR019_V1_FRESHNESS_WINDOW_SECONDS`
  and `ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS` for the caller to pass, with a
  test pinning them to ADR 019; there is no env override, so no variable can
  widen the gate.
- **Implementation identity.** Resolved by #472's catalog: the enforced
  identity is `contentHash`/`implementationHash`. `pipeline_source_hash` stays
  as a recorded diagnostic (it explains *which function* moved when the
  catalog hash changes) but no longer gates, so the
  `require_pipeline_identity` knob is dropped.
- **Outcome vocabulary mapping.** `WORK_ITEM_STATES` is
  `{active, waiting, completed, superseded, archived}` and `ExecutionRef.phase`
  is mctl-api's `Pending|Running|Succeeded|Failed|Error`. Neither is an
  outcome vocabulary. Taken as a mapping table into
  `{succeeded, failed, abandoned, in-progress, unknown}`, pinned by a test
  against `work_context.contract.WORK_ITEM_STATES` so a new store state fails
  loudly as `unknown` rather than being silently bucketed.
- **`capability_calls` in replay.** ADR 015 says 0 in offline replay. The CLI
  does make store round trips; taken as: `capability_calls` describes the
  assembly being scored and is 0, while the CLI's own reads are reported
  separately as `replay_store_reads`.
- **Live emission default.** Taken as `off` by default, matching
  `ISSUE_INVESTIGATOR_CONTEXT_MODE`'s convention that an unset variable
  changes nothing; the runbook pairs enabling it with `shadow`.
