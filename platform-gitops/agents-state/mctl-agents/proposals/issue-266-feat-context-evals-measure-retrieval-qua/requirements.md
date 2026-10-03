# Context evaluation: retrieval quality, freshness, cost and outcome impact

## Context

`orchestrator/context_assembly.py` already assembles, ranks, deduplicates,
budgets and seals a `ContextSnapshot` for every issue-investigation
(mctlhq/mctl-agents#265, #471), and since #431 every snapshot of a store
execution (`we_...`) is persisted in mctl-api at
`WORK_CONTEXT_ROLLOUT_MODE` >= `observe` — proven live in #490. What does
not exist is any statement of whether the context that was assembled was
*good*: `AssemblyMetrics` (`orchestrator/context_assembly.py:258-306`)
counts what the pipeline did (candidates, drops, bytes, latency), not
whether the evidence the model needed was actually selected. ADR 009
amendment 1 ends on exactly this gap: "Wiring promotion/rollback of
strategies is mctlhq/mctl-agents#472; measuring them is #266"
(`docs/adr/009-context-snapshot-contract.md:402`).

This proposal adds a retrieval/context evaluator that is *independent of*
final model-output scoring, so the platform can tell bad reasoning over good
context from good reasoning over missing, stale, noisy or duplicated
context, and can detect a retrieval regression caused by a ranking, filter
or config change. It reads stored snapshots and adds no new storage. It
evaluates every fixture case under **both** shipped strategies —
`deterministic-fixed-order` and `trust-freshness-ranked` — so the two can be
compared against each other and against the execution outcome the store
ledger records. It complements the final-output evaluator of #60 by joining
on `execution_id` / `context_snapshot_id` rather than producing a competing
single score.

## User stories

- AS a platform owner I WANT retrieval quality measured separately from the
  model's answer SO THAT a bad proposal can be attributed to missing context
  or to the model, not guessed at.
- AS an agent developer I WANT every evaluation case scored under both
  `deterministic-fixed-order` and `trust-freshness-ranked` SO THAT I can
  decide whether to promote the ranked strategy (#472) on evidence.
- AS a reviewer of a ranking/filter change I WANT staleness, noise and
  duplicate rates as numbers against a committed baseline SO THAT a
  regression fails a test instead of being discovered in production.
- AS an operator I WANT context size, estimated token cost, assembly latency
  and capability-call counts reported per strategy SO THAT a retrieval
  improvement that triples prompt cost is visible at review time.
- AS an incident investigator I WANT to replay the evaluation offline
  against a stored snapshot by work item SO THAT I can inspect what a past
  execution was given without re-running the agent or writing anything.
- AS a security reviewer I WANT the evaluation record to carry only ids,
  kinds, codes and counts SO THAT no raw production context reaches
  evaluation telemetry.

## Acceptance criteria (EARS)

### Emission and safety

- WHEN `ISSUE_INVESTIGATOR_CONTEXT_MODE` is `shadow` or `on` and a snapshot
  has been sealed THE SYSTEM SHALL print exactly one
  `[context] context_eval=<canonical json>` line, from its own guarded block
  placed after the existing `[context] context_assembly=` line
  (`orchestrator/run_issue_investigator.py:1837`, which is itself outside
  the `try` at `:1791`).
- WHEN the sealed snapshot carries a `WorkContextRef` THE SYSTEM SHALL
  include `work_item_id`, `execution_id` and `execution_sequence` in that
  line, and SHALL omit those keys when it does not.
- WHILE `ISSUE_INVESTIGATOR_CONTEXT_MODE` is `off` THE SYSTEM SHALL emit no
  `context_eval` line and run byte-for-byte as it does today.
- THE SYSTEM SHALL NOT gate the `context_eval` line on
  `WORK_CONTEXT_ROLLOUT_MODE`: it is emitted whenever the context mode is
  not `off`, with or without a store execution (owner choice (b)).
- WHILE `ISSUE_INVESTIGATOR_CONTEXT_EVAL` is `off` THE SYSTEM SHALL skip
  evaluation entirely, so an operator can roll the feature back without a
  redeploy; the variable is read fresh per call, like `_context_mode()`
  (`orchestrator/run_issue_investigator.py:155`).
- IF evaluation raises for any reason THEN THE SYSTEM SHALL print
  `warn: context evaluation failed: <type>: <msg>` and continue the
  investigation unchanged, in `shadow` and in `on` alike — measurement must
  never be able to fail an investigation, which is a stricter policy than
  `_assemble_context`'s (`:1827-1831`, where `on` re-raises).
- WHILE emitting any record THE SYSTEM SHALL carry no `locator`, no
  `selector`, no payload byte and no rendered text — only `source_id`s,
  `kind`s, closed-vocabulary codes, counts and ratios, mirroring
  `AssemblyMetrics.to_log_dict()`'s rule
  (`orchestrator/context_assembly.py:285-306`).

### Identity verification

- WHEN evaluating any snapshot THE SYSTEM SHALL first recompute both
  identities: the document identity (`recompute_content_hash`,
  `orchestrator/context_snapshot.py:1266`, and
  `snapshot_id == "cs-" + content_hash[7:23]`, `:1245`, a hash that
  excludes `created_at`), and the store identity
  (`hash_bytes(canonical_bytes(snapshot))` over the whole canonical
  document, `orchestrator/work_context/snapshots.py:88-99`).
- WHEN a store snapshot is involved THE SYSTEM SHALL carry a `store_ref`
  block of `{work_item_id, execution_id, store_snapshot_id,
  store_content_hash}`, where `store_snapshot_id` is mctl-api's opaque
  `cs_`-prefixed id (`snapshots.py:42`), carried and compared but never
  recomputed.
- IF either recomputed hash disagrees with the value it is checked against
  THEN THE SYSTEM SHALL emit the record with `verdict: "hash-mismatch"`,
  the two disagreeing field names, and no metrics at all — a document whose
  identity does not hold is not measured.
- IF no `store_ref` is available (no store execution, or the persist answer
  was not `stored`) THEN THE SYSTEM SHALL still verify the document
  identity and SHALL record `store_ref: null` rather than failing.

### Metrics (distinct from final model output)

- WHEN a case carries labelled useful evidence THE SYSTEM SHALL report
  `selected_precision`, `useful_recall` and `f1` over the labelled
  candidates.
- IF a case carries no labels THEN THE SYSTEM SHALL report those three as
  `null`, never as `0.0` or `1.0`.
- THE SYSTEM SHALL report `stale_rate`, `duplicate_rate`, `noise_rate`,
  `context_bytes`, `context_tokens_estimate`, `assembly_latency_ms`,
  `capability_calls` and per-source-kind coverage (candidates, included,
  bytes) for every evaluated snapshot.
- WHILE computing staleness THE SYSTEM SHALL count a source whose
  `selection.reason_code` is `stale-demoted` as stale, alongside one whose
  `freshness.staleness` is `stale` (the ranked strategy demotes rather than
  drops, `orchestrator/context_assembly.py:521-530`).
- WHEN deriving conflict metrics THE SYSTEM SHALL read `snapshot.conflicts`
  only, and SHALL never re-derive a conflict from text.
- THE SYSTEM SHALL report `context_tokens_estimate` as a declared estimate
  derived from bytes, never as a billed token count; billed model cost stays
  with `orchestrator/usage_ledger.py` and ADR 012.
- THE SYSTEM SHALL name itself in every record with `evaluator_name` and
  `evaluator_version`, so a metric change is attributable.

### Fixtures and both strategies

- WHEN the fixture suite runs THE SYSTEM SHALL evaluate every case under
  both `deterministic-fixed-order` and `trust-freshness-ranked`
  (`context_assembly.STRATEGIES`) and produce one record per
  (case, strategy) pair.
- THE SYSTEM SHALL ship a committed fixture set containing at least:
  relevant and irrelevant log evidence; stale versus current deployment
  information; GitHub issue/PR evidence; duplicated evidence; conflicting
  evidence that fires `CONFLICT_PRIOR_PROPOSAL_SUPERSEDED`
  (`orchestrator/context_assembly.py:102`); a `stale-demoted` case; and a
  missing-evidence case where the labelled useful evidence is absent from
  every candidate.
- WHEN a fixture case declares expected useful evidence that no candidate
  carries THE SYSTEM SHALL report `missing_expected > 0` and
  `useful_recall < 1.0` rather than silently scoring it.
- WHEN the fixture suite runs against the committed baseline THE SYSTEM
  SHALL fail if any metric of any (case, strategy) pair differs from the
  baseline, so a ranking, filtering or config regression is a red test.
- THE SYSTEM SHALL keep the default strategy's sealed bytes and
  `snapshot_id`s unchanged: the golden fixture
  `tests/fixtures/context/investigator-snapshot.json` and the pins in
  `tests/test_context_ranking.py:120,148` must still pass untouched.

### Correlation and outcome

- WHEN a record is emitted THE SYSTEM SHALL carry the chain
  `execution_id -> context_snapshot_id -> strategy/version -> selected
  source ids -> agent/profile/definition versions -> context evaluation`,
  reading agent/profile identity from `snapshot.execution`
  (`ExecutionCorrelation`, `orchestrator/context_snapshot.py:461`).
- WHEN linking an evaluation to an outcome THE SYSTEM SHALL join on the
  store ledger — `work_context.execution_id` (`we_`),
  `work_context.prior_execution_ids` and
  `work_context.resumed_from_snapshot_id` against
  `WorkItemClient.get`'s `WorkItem.state` and `ExecutionRef.phase`
  (`orchestrator/work_context/client.py:162`,
  `orchestrator/work_context/contract.py:166-191,265-289`) — owner choice
  (a).
- IF a run has no store execution THEN THE SYSTEM SHALL fall back to the
  published proposal's `.status.yaml` `status` field, and SHALL record
  `outcome_source: "status-yaml"` so the weaker link is visible.

### Offline replay

- WHEN invoked as `python -m orchestrator.run_context_eval --work-item <id>
  [--execution we_...]` THE SYSTEM SHALL read the work item, its execution
  ledger and the stored snapshot through `WorkItemClient` only
  (`get`, `execution_snapshot`, `client.py:162,251`) and SHALL write
  nothing — no file, no gitops commit, no POST (owner choice (c)).
- WHEN `--execution` is omitted THE SYSTEM SHALL evaluate the latest
  execution in the ledger that sealed a snapshot.
- IF the store answers `SNAPSHOT_ABSENT` or `SNAPSHOT_UNKNOWN` THEN THE
  SYSTEM SHALL print the verdict and exit non-zero without inventing a
  result.
- WHEN invoked as `python -m orchestrator.run_context_eval --fixtures` THE
  SYSTEM SHALL evaluate the committed fixture set offline with no network
  access at all.

### Documentation

- THE SYSTEM SHALL add ADR **015** (`docs/adr/015-context-evaluation-contract.md`);
  012 is taken by model-usage cost attribution and 014 by the policy
  checkpoint, so 015 is the next free number.
- THE SYSTEM SHALL update ADR 009's follow-up row (b)
  (`docs/adr/009-context-snapshot-contract.md:513`), which still reads
  "needs an issue", to record that snapshot persistence was delivered by
  mctlhq/mctl-agents#431 and proven live in #490, and SHALL add a row for
  measurement pointing at this issue.

## Out of scope

- Training or shipping a production reranker, or any learned model in the
  evaluation path. Every rule here is fixed and deterministic.
- Declaring one universal retrieval metric sufficient for all agents. The
  fixture set and metrics are the *issue-investigator's*; other agents may
  reuse the module, but no cross-agent metric is asserted.
- Storing raw production context anywhere. No payload, locator or selector
  leaves the process.
- New storage or new mctl-api routes. Snapshots are already persisted
  (#431/#490); this reads them and adds nothing.
- Changing what the assembler selects. `run_pipeline` is an extraction, not
  a behaviour change; the default strategy's snapshot ids and bytes are
  pinned.
- Replacing or re-implementing #60's final-output evaluation, or grading the
  model's proposal text.
- A production-scale benchmark, human relevance labelling at scale, or a
  dashboard. Fixtures are small, curated and committed.
- Promotion/rollback of a context strategy on the evidence produced here —
  that is mctlhq/mctl-agents#472.

## Open questions

- **Token estimate.** `context_tokens_estimate` is derived from bytes
  (`ceil(used_bytes / 4)`), because no tokenizer is a dependency of this
  stdlib-only module. Proceeding with the byte-derived estimate, explicitly
  labelled as such; a real count can be joined later from the usage ledger
  (ADR 012) by `execution_id`.
- **Shape of the #60 join.** Whether #60's final-execution evaluation wants
  the context record inline or joined by key is not settled in this repo.
  Proceeding with join-by-key (`execution_id`, `context_snapshot_id`), which
  is additive for either answer.
- **Log evidence has no production collector.** `collect_*` covers five
  kinds; Loki/incident sources are explicitly out of scope of #265
  (`orchestrator/context_assembly.py:632-635`). The "relevant + irrelevant
  logs" case therefore uses synthetic `loki-logs` candidates fed straight to
  `run_pipeline`, which is kind-agnostic when a candidate supplies its own
  `max_age_seconds`. Proceeding, and recording that this case measures the
  pipeline, not a collector that exists.
- **Baseline drift policy.** A deliberate ranking change must update the
  committed baseline in the same PR. Proceeding with "baseline is a golden
  fixture, regenerated only by an explicit `--write-baseline` run", matching
  `tools/record_workflow_history.py`'s deliberate-regeneration convention.
- **Owner choices from the review, adopted as proposed:** (a) outcome link
  on the store ledger — yes; (b) gate the live line on
  `WORK_CONTEXT_ROLLOUT_MODE >= observe` — no, emit whenever the context
  mode is not `off`; (c) `--work-item` replay in v1 — yes, read-only.
