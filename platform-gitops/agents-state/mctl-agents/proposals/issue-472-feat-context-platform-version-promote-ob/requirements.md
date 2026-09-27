# Context strategy release lifecycle: version, promote, observe and roll back

> **Correction 2026-09-27.** The original proposal assumed mctlhq/mctl-agents#266
> had delivered ADR 015's evaluator, fixtures, baseline and stored-run replay.
> Current `main` has only the ADR and the extracted `run_pipeline` portion.
> The missing evidence implementation is now mctlhq/mctl-agents#526.
> This proposal's `tasks.md` implements Slice A only; Slice B is
> mctlhq/mctl-agents#527 and Slice C is mctlhq/mctl-agents#528. In Slice A a
> production promotion is always refused as `evidence-missing`.
> Slice A may establish the inert release contract, but production
> promotion/enforcement is gated on #526. No production path may treat
> `evidence.kind: none` as sufficient evidence.

## Context

`orchestrator/context_assembly.py` already assembles, ranks, deduplicates,
budgets and seals a `ContextSnapshot` for every issue investigation (ADR 009,
mctlhq/mctl-agents#265/#471), and every snapshot records which strategy
produced it in its `ContextStrategy` block (`orchestrator/context_snapshot.py:649`).
What the platform has no contract for is the *other* direction: how a strategy
becomes the one that runs. Today that answer is a single environment variable,
`ISSUE_INVESTIGATOR_CONTEXT_STRATEGY`, read in `AssemblyConfig.from_env()`
(`context_assembly.py:229-238`) and validated against a two-entry tuple of
module constants (`STRATEGIES`, `context_assembly.py:84`). The version a
snapshot claims — `STRATEGY_VERSION = "1.0.0"` (`context_assembly.py:72`) — is a
string literal that names no bytes: `rank_candidates` can be edited and every
snapshot will still claim `trust-freshness-ranked 1.0.0`. There is no per-
environment binding, no revision history, no recorded promoter, no evidence
link, and no rollback primitive beyond unsetting the env var.

ADR 009 amendment 1 closes with the sentence this issue exists to discharge:
"Wiring promotion/rollback of strategies is mctlhq/mctl-agents#472; measuring
them is #266" (`docs/adr/009-context-snapshot-contract.md:402`), and ADR 015
repeats it as an explicit non-goal ("promoting or rolling back a strategy on
this evidence... is #472", `docs/adr/015-context-evaluation-contract.md:153`).
#266 was closed after only that contract/extraction slice; the missing evaluator,
baseline and replay implementation is tracked in #526 and is a prerequisite for
production promotion in this proposal.

This proposal supplies the missing half: an immutable, content-pinned
`ContextStrategyVersion`, an atomic per-(agent, environment)
`ContextStrategyBinding` with append-only revision history, a four-stage
rollout ladder that can run a candidate strategy alongside the active one
without changing what the model reads, and an exact-revision rollback. It
mirrors ADR 007's definition/profile/binding lifecycle
(`docs/adr/007-agent-definition-execution-profile-contract.md:117-212`) and
this repository's own `off -> observe -> enforce -> only` precedent
(`orchestrator/lifecycle/rollout.py`, `orchestrator/work_context/rollout.py`)
rather than inventing a third vocabulary.

## User stories

- AS a platform operator I WANT each context strategy to have an immutable,
  content-pinned version SO THAT a snapshot claiming `trust-freshness-ranked
  1.0.0` can only have been produced by the exact assembly code that version
  names.
- AS a platform operator I WANT to promote a strategy version to one
  environment through a reviewed, audited binding revision SO THAT "which
  strategy is live for the investigator in production" has a single answer with
  a promoter, a timestamp and a reason.
- AS a platform operator I WANT to observe a candidate strategy against the
  active one on the same real inputs, without changing what the model reads,
  SO THAT a promotion rests on measured evidence rather than on a guess.
- AS a platform operator I WANT to roll back to an exact prior binding revision
  SO THAT a bad promotion is reversed to a known pair, not to a guess at "one
  step back".
- AS an incident responder I WANT an instant, no-deploy break-glass SO THAT a
  misbehaving strategy can be taken out of the path without waiting for a
  release.
- AS an auditor I WANT the binding revision and the strategy's content hash
  recorded durably on the sealed snapshot SO THAT "what strategy revision
  produced this proposal" is answerable after telemetry has expired.
- AS a reviewer of `orchestrator/context_assembly.py` I WANT CI to refuse a
  change that alters assembly behaviour without republishing a version SO THAT
  version identity cannot silently drift from implementation.

## Acceptance criteria (EARS)

### Versioning

- WHEN a `ContextStrategyVersion` document is loaded THE SYSTEM SHALL require
  `apiVersion: context.mctl.ai/v1alpha1`, `kind: ContextStrategyVersion`, a
  `name` drawn from the strategies `orchestrator/context_assembly.py` actually
  implements, a semver `version`, a `contentHash` and an
  `implementationHash`, and SHALL reject an unknown `apiVersion` or `kind`
  loudly, never falling back to a default shape — mirroring
  `orchestrator/manifest.py`'s `SUPPORTED_API_VERSIONS` allow-list and
  `orchestrator/resolver.load_release_binding`'s own apiVersion/kind checks
  (`resolver.py:778-781`).
- WHEN a version document is published THE SYSTEM SHALL compute
  `implementationHash` as a sha256 over the declared implementation files, in
  sorted order by path, as length-prefixed `"<len>\n<path><len>\n<bytes>"`
  pairs — the identical unambiguous encoding
  `tools/publish_agent_release.py` already defines for `prompt_hash`.
- WHILE a version document exists THE SYSTEM SHALL treat it as immutable:
  a behaviour change is a new version document, never an edit to a published
  one.
- IF a loaded version's recomputed `implementationHash` differs from the
  committed value THEN THE SYSTEM SHALL fail closed with the exact command
  that regenerates it, and SHALL NOT resolve that version.
- WHEN a version's `lifecycle` is `deprecated` THE SYSTEM SHALL allow existing
  bindings to resolve it and SHALL refuse a new promotion that selects it;
  WHEN it is `disabled` THE SYSTEM SHALL refuse to resolve it at all, exactly
  as ADR 007's lifecycle table rules for registry versions
  (`007-...:193-197`).

### Binding and promotion

- WHEN a `ContextStrategyBinding` is loaded for `(agent, environment)` THE
  SYSTEM SHALL require that the document's declared `environment` and `agent`
  agree with the path it was read from, refusing the document otherwise — the
  same cross-check `resolver.load_release_binding` performs (`resolver.py:791-802`).
- WHILE a binding exists THE SYSTEM SHALL treat its `history` as append-only
  and SHALL treat the entry with the highest `revision` as active; revisions
  SHALL be positive integers, strictly increasing, with no gap and no reuse.
- WHEN a promotion is recorded THE SYSTEM SHALL append one new revision
  carrying the strategy name, version, that version's `contentHash` and
  `implementationHash`, `promotedBy`, `promotedAt`, `reason`, and an
  `evidence` block, and SHALL NOT mutate or delete any prior revision.
- IF a promotion names a strategy version whose document is absent,
  `deprecated`, `disabled`, or whose `implementationHash` does not match the
  code in the same commit THEN THE SYSTEM SHALL refuse the promotion.
- WHEN a promotion targets the `production` environment THE SYSTEM SHALL
  require `evidence.kind: context-eval`; `none` and any unknown kind are
  refused. The evidence SHALL name the exact strategy name/version,
  `contentHash`, `implementationHash`, evaluator version, observation
  timestamp and consecutive-run count.
- WHEN production evidence is evaluated THE SYSTEM SHALL refuse it as
  `evidence-mismatch` unless its strategy/version/content/implementation
  identity exactly matches the version being promoted; SHALL refuse it as
  `evidence-stale` when the newest observation is older than **7 days**; and
  SHALL refuse it as `evidence-insufficient` unless it represents at least
  **3 consecutive observe-mode investigations** with no `hash-mismatch`
  verdict. These are validation rules, not automatic promotion: a human-reviewed
  binding PR is still required. The 7-day window and the 3-run minimum are
  **v1 promotion policy constants**, named as such in ADR 019 and changed only
  by amending it; they are release policy, not a property of the #526
  evaluator.
- WHEN a promotion targets `shadow` THE SYSTEM SHALL accept
  `evidence.kind: none` with a recorded `reason`, because shadow is not an
  authoritative production selection.
- WHEN a rollback is requested THE SYSTEM SHALL require an explicit target
  revision, SHALL append a new revision restoring that revision's exact
  strategy/version/hash triple with `rollbackOf: <revision>` recorded, and
  SHALL NOT infer "one step back".
- IF a rollback names a revision whose strategy version has since become
  `disabled` THEN THE SYSTEM SHALL refuse the rollback and name the disabled
  version.

### Evidence provenance and freshness

- WHILE mctlhq/mctl-agents#526 is not implemented on the running image THE
  SYSTEM SHALL allow contract/catalog validation and shadow binding work, but
  SHALL NOT create or accept a production promotion revision.
- WHEN #526 emits promotion evidence THE release layer SHALL consume its
  closed-vocabulary verdicts and correlation fields rather than reimplementing
  evaluation metrics. `#472` owns release decisions; `#526` owns evaluation.
- A break-glass `CONTEXT_RELEASE_ROLLOUT_MODE=off` may always remove the
  release binding from the execution path without mutating historical evidence
  or snapshots.

### Rollout ladder and resolution

- WHILE `CONTEXT_RELEASE_ROLLOUT_MODE` is unset or `off` THE SYSTEM SHALL
  behave byte-for-byte as it does today: `AssemblyConfig.from_env()` reads
  `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY`, no binding is loaded, no second
  pipeline pass runs, and every sealed snapshot keeps the `snapshot_id` it
  would have had.
- WHILE the mode is `observe` THE SYSTEM SHALL resolve the binding, run the
  bound strategy as a second, non-authoritative pass over the *same* candidate
  list via `context_assembly.run_pipeline` — which is already pure, copies its
  candidates and was extracted for exactly this double-run
  (`context_assembly.py:996-1017`) — and SHALL leave the env var deciding what
  the model reads.
- WHILE the mode is `observe` THE SYSTEM SHALL NOT persist, render into the
  prompt, or return the candidate pass's snapshot; only the authoritative
  snapshot reaches `_persist_to_work_item_store` and `AssemblyResult.rendered`.
- WHILE the mode is `enforce` or `only` THE SYSTEM SHALL let the resolved
  binding select the strategy that produces the authoritative snapshot.
- WHILE the mode is `only` THE SYSTEM SHALL reject a set
  `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` loudly rather than silently ignoring
  it, so the env var can never shadow the binding unnoticed.
- IF the binding is unresolvable at `enforce` or above AND
  `CONTEXT_RELEASE_REQUIRED` is true (its default) THEN THE SYSTEM SHALL fail
  the assembly; IF `CONTEXT_RELEASE_REQUIRED` is false THEN THE SYSTEM SHALL
  fall back to `deterministic-fixed-order`, log
  `binding-unresolved-fallback-default`, and continue — the same break-glass
  shape as `work_context.rollout.blocks_on_unknown()`.
- IF `CONTEXT_RELEASE_ROLLOUT_MODE` holds an unrecognised value THEN THE
  SYSTEM SHALL answer `off` and warn, never raise — matching
  `work_context/rollout.py:mode()`.

### Observability

- WHEN a strategy is resolved through a binding THE SYSTEM SHALL emit one
  structured `CONTEXT_STRATEGY_RELEASE` line carrying mode, agent,
  environment, strategy name, version, content hash, binding revision,
  `override_active`, and the resolution verdict — the shape
  `context_assembly._emit_snapshot_answer` already uses for
  `WORK_CONTEXT_SNAPSHOT` (`context_assembly.py:1231-1239`).
- WHEN the mode is `observe` THE SYSTEM SHALL emit one
  `CONTEXT_STRATEGY_COMPARE` line carrying both strategies' identity, both
  `snapshot_id`s, and the counter deltas already defined by
  `AssemblyMetrics.to_log_dict()` (`used_sources`, `used_bytes`,
  `dropped_stale`, `stale_demoted`, `dropped_duplicate`, `excluded_budget`,
  `conflict_count`, `assembly_latency_ms`).
- WHILE emitting any of these lines THE SYSTEM SHALL carry ids, kinds, closed
  vocabulary codes, versions, hashes, counts and ratios only — never a
  `locator`, a `selector` or any byte derived from a retrieved payload
  (ADR 009 sec. 5, ADR 015 sec. 3).
- WHEN a snapshot is sealed under a binding THE SYSTEM SHALL record
  `release_revision` and `content_hash` inside its `strategy` block as
  optional fields that are omitted when unset and enter `content_hash` only
  when present, so every snapshot sealed at mode `off` — including the golden
  fixture `tests/fixtures/context/investigator-snapshot.json` and every
  snapshot already persisted under mctlhq/mctl-agents#431/#490 — keeps its
  bytes and its `snapshot_id`. This follows ADR 009 amendment 1's own
  field-growth rule for `conflicts` (`context_snapshot.py:866-867,1202-1206`).

### Safety invariant

- WHILE any part of this feature runs THE SYSTEM SHALL treat a strategy
  version, a binding revision and a comparison metric as ordering and
  measurement only; no promotion, binding or score SHALL be read by a policy,
  capability-eligibility or authorization decision, and no module added here
  SHALL be imported by a policy path — restating ADR 009 sec. 5's
  non-negotiable "context relevance is never an authorization mechanism" and
  reusing its existing field-name and import-direction tests.

## Out of scope

- A new mctl-api table, route or registry client for context strategies. The
  catalog is committed in `mctl-agents` for this proposal; a cross-repo
  gitops/registry promotion path is a named follow-up.
- Implementing `orchestrator/context_eval.py`, its fixture set, its baseline
  or its replay CLI — the undelivered part of mctlhq/mctl-agents#266 is now
  mctlhq/mctl-agents#526. This proposal defines and validates the release-side
  evidence reference, but does not duplicate evaluator logic. Production
  promotion/enforcement remains blocked until #526 is implemented.
- Writing a new strategy or ranker, or changing what either existing strategy
  selects. `deterministic-fixed-order` and `trust-freshness-ranked` keep their
  behaviour byte-for-byte.
- Reopening any part of ADR 009 sec. 1-7 other than the optional
  `ContextStrategy` field growth explicitly permitted by sec. 6 and precedented
  by amendment 1.
- Extending the lifecycle to agents other than `issue-investigator`. The
  binding path is keyed by agent from day one, but only the investigator
  assembles context today.
- Per-tenant or per-repository strategy selection.
- Automatic promotion on a metric threshold. Every promotion in this proposal
  is a reviewed commit by a human.

## Open questions

- **Catalog location.** This proposal commits the catalog under
  `config/context-strategies/` in `mctl-agents`, because `implementationHash`
  can only be computed against the assembly code in the same commit, and a
  binding that could move faster than the image it names would select a
  version whose implementation is absent from the running worker — the exact
  floating-half failure ADR 007 sec. 4 documents for `definition.version`. The
  cost is that a promotion is a release, not an API call. Moving the catalog
  to `mctl-gitops/platform-gitops/agent-platform/` alongside
  `CATALOG_RELEASES_DIR` (`resolver.py:105`) once a content pin is enforced
  there is the natural follow-up; proceeding in-repo.
- **Implementation-hash granularity.** Slice A keeps the conservative
  whole-declared-file hash. This intentionally over-reports change rather than
  under-reporting it. Because #526 is expected to touch context assembly code,
  merging #526 invalidates the published hash and therefore requires an
  explicit republish before Slice C can promote anything to production. This churn is
  accepted for v1; per-symbol hashing remains a follow-up.
- **Environments.** `orchestrator/resolver.py:114` sets `DEFAULT_ENVIRONMENT =
  "shadow"` because no production agent binding is written yet. This proposal
  writes both a `shadow` and a `production` context-strategy binding directory
  and defaults resolution to `production` for the investigator, since the
  context pilot's own ladder (`off/shadow/on`) is what gates live effect here,
  not the agent-release environment. If that turns out to conflate two
  environment axes, the resolver's `shadow` default is the fallback.
- **Interaction with `ISSUE_INVESTIGATOR_CONTEXT_MODE`.** The two ladders are
  deliberately orthogonal: `CONTEXT_RELEASE_ROLLOUT_MODE` decides *which*
  strategy runs, `ISSUE_INVESTIGATOR_CONTEXT_MODE` decides whether assembly
  happens at all and whether its output reaches the prompt. With
  `CONTEXT_MODE=off` no assembly runs, so no binding is resolved regardless of
  the release mode. Proceeding on that reading.
- **The `retrieval-ranking-trust` dependency.** The issue lists it as not yet
  bound. `trust-freshness-ranked` (#471) already exists and is a real
  promotable version, so this work does not block on it; a future trust/ranking
  work item publishes new versions into the same lifecycle.
- **Who may promote.** Enforcement is the repository's existing PR review plus
  `.github/workflows/pr-validation.yml`. A CODEOWNERS entry for
  `config/context-strategies/` is suggested but not assumed.
