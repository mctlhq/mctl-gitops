# Context release rollout ladder, observe shadow pass, and release telemetry (#472 Slice B)

## Context

mctlhq/mctl-agents#472 Slice A landed the inert half of the context-strategy
release contract (ADR 019, `docs/adr/019-context-strategy-release-contract.md`):
the committed catalog under `config/context-strategies/`, the loader/resolver
`orchestrator/context_release.py`, the operator CLI `tools/context_release.py`,
and the drift guard in `tests/test_context_release.py`. Nothing reads any of it
at runtime: `orchestrator/context_assembly.py` still chooses its strategy from
`ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` alone (`AssemblyConfig.from_env`,
`context_assembly.py:229-238`), and `orchestrator/context_release.py`'s own
docstring says so in as many words.

Slice B is the rollout wiring: the four-stage `off/observe/enforce/only` ladder
ADR 019 sec. 4 specifies, the selection hook that lets a committed
`ContextStrategyBinding` decide which strategy a run assembles under, a
behaviour-neutral `observe` shadow pass that runs the bound strategy as a
second, non-authoritative `run_pipeline` pass so there is something for
mctlhq/mctl-agents#526's evaluator to measure later, and the two telemetry lines
ADR 019 sec. 5 names. It matters because without `observe` there is no evidence
path at all: ADR 019 forbids a production promotion on `evidence.kind: none`, so
until a run can compute "what the other strategy would have sealed", no strategy
can ever be promoted past the inert shadow baseline. Slice B creates no
production binding and, at its default `off`, changes nothing: every snapshot
keeps its exact bytes and its `snapshot_id`.

## User stories

- AS a platform operator I WANT a single env var, `CONTEXT_RELEASE_ROLLOUT_MODE`,
  that moves the investigator from "the catalog is inert" to "the catalog
  decides" in four reviewable stages SO THAT I can adopt the release contract
  without a redeploy and roll back by unsetting one variable.
- AS a platform operator I WANT an `observe` stage that computes what the bound
  strategy would have sealed without letting it reach the prompt, the sealed
  snapshot or the work-item store SO THAT I can gather comparison evidence at
  zero behavioural risk.
- AS the author of mctlhq/mctl-agents#526's evaluator I WANT each run to emit the
  authoritative and candidate `snapshot_id`s plus both strategy identities SO
  THAT I can evaluate them without re-implementing assembly or ranking.
- AS a reviewer of a promotion I WANT one `CONTEXT_STRATEGY_RELEASE` line per run
  naming mode, agent, environment, strategy, version, content hash, binding
  revision, override state and verdict SO THAT I can tell from logs alone which
  strategy actually decided a given execution.
- AS an on-call engineer I WANT a break-glass switch, `CONTEXT_RELEASE_REQUIRED`,
  inside `enforce`/`only` SO THAT a broken or missing binding can be made
  non-blocking without changing the rollout stage.
- AS a maintainer of the tracing pipeline I WANT every new `mctl.*` attribute
  reserved in the mctl-docs catalog before this issue closes SO THAT the
  attribute namespace stays a catalog and not a collection of local inventions.

## Acceptance criteria (EARS)

### The ladder

- WHILE `CONTEXT_RELEASE_ROLLOUT_MODE` is unset THE SYSTEM SHALL answer `off`
  from `mode()`, answer `False` from `binding_is_observed()`,
  `binding_decides()`, `binding_is_sole_selector()` and `blocks_on_unknown()`,
  open no file under `config/context-strategies/`, and import neither
  `orchestrator.context_release` nor `yaml`.
- IF `CONTEXT_RELEASE_ROLLOUT_MODE` holds a value outside
  `off/observe/enforce/only` THEN THE SYSTEM SHALL answer `off`, print one
  warning line naming the variable, the bad value and the accepted set, and
  never raise.
- WHILE the ladder is at `observe` or above THE SYSTEM SHALL answer `True` from
  `binding_is_observed()`; WHILE at `enforce` or above, `True` from
  `binding_decides()`; WHILE at `only`, `True` from
  `binding_is_sole_selector()` — ordered stages, never independent flags.
- WHEN `CONTEXT_RELEASE_REQUIRED` is read THE SYSTEM SHALL treat `false`, `no`,
  `0` and `off` (case-insensitive, whitespace-stripped) as false and every other
  value, including unset, as true.
- WHILE the ladder is below `enforce` THE SYSTEM SHALL answer `False` from
  `blocks_on_unknown()` whatever `CONTEXT_RELEASE_REQUIRED` is set to.
- THE SYSTEM SHALL read `CONTEXT_RELEASE_ROLLOUT_MODE` in exactly one module and
  `CONTEXT_RELEASE_REQUIRED` only through `blocks_on_unknown()`.
- THE SYSTEM SHALL document the three-switch table
  (`ISSUE_INVESTIGATOR_CONTEXT_MODE` = does assembly happen at all;
  `CONTEXT_RELEASE_ROLLOUT_MODE` = which strategy; `CONTEXT_RELEASE_REQUIRED` =
  break-glass inside enforce/only) in the ladder module's docstring, in the same
  shape `orchestrator/work_context/rollout.py` and
  `orchestrator/lifecycle/rollout.py` already use.

### Selection

- WHEN `resolve_strategy_for_run(agent, config)` is called at `off` THE SYSTEM
  SHALL return `(config.strategy, None)` without importing
  `orchestrator.context_release`.
- WHEN `resolve_strategy_for_run` is called past `off` THE SYSTEM SHALL import
  `orchestrator.context_release` from inside the function body, following the
  deferred-import pattern `_work_context_active` (`context_assembly.py:1242`),
  `_client` (`:1253`) and `_persist_to_work_item_store` (`:1277`) already use.
- WHILE the ladder is at `observe` THE SYSTEM SHALL keep
  `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` (via `AssemblyConfig.strategy`)
  authoritative and treat the resolved binding as observation only.
- WHILE the ladder is at `enforce` or `only` THE SYSTEM SHALL make the resolved
  binding's strategy the authoritative one.
- IF the ladder is at `only` AND `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` is set to
  a non-empty value THEN THE SYSTEM SHALL raise a hard error naming both the
  variable and the binding, so the env var can never silently shadow the binding.
- IF the ladder is at `enforce` or `only` AND the binding cannot be resolved
  THEN THE SYSTEM SHALL raise when `blocks_on_unknown()` holds, and otherwise
  fall back to `deterministic-fixed-order` and record the reason code
  `binding-unresolved-fallback-default`.
- IF the ladder is at `observe` AND the binding cannot be resolved THEN THE
  SYSTEM SHALL record the reason code `binding-unresolved-observe-skipped`, skip
  the shadow pass, and never fail the run — `observe` is behaviour-neutral by
  definition.
- WHILE the authoritative strategy differs from `AssemblyConfig.strategy` THE
  SYSTEM SHALL apply the substitution before the collector loop runs, because
  `collect_prior_proposal` reads `assembly_input.config.ranked`
  (`context_assembly.py:821`) and would otherwise age a prior proposal under one
  strategy while the pipeline ranks under another.

### The observe shadow pass

- WHEN the ladder is at `observe` AND a binding resolves to a strategy other than
  the authoritative one THE SYSTEM SHALL run `run_pipeline` a second time over
  the same pre-pipeline candidate list with `replace(config, strategy=bound)`,
  and seal that outcome locally for the sole purpose of obtaining its
  `snapshot_id`.
- WHILE the shadow pass is enabled THE SYSTEM SHALL keep the authoritative
  snapshot's `content_hash` and `snapshot_id` byte-identical to what the same
  inputs produce with the shadow pass disabled.
- THE SYSTEM SHALL never let the candidate snapshot reach `seal()`'s returned
  value, `AssemblyResult.snapshot`, `AssemblyResult.rendered`
  (`context_assembly.py:1128-1130`) or `_persist_to_work_item_store`
  (`:1222`).
- WHILE the ladder is at `observe` THE SYSTEM SHALL call the work-item store
  client exactly once per run.
- IF the shadow pass raises for any reason THEN THE SYSTEM SHALL log the failure
  under a closed-vocabulary reason code and complete the run unchanged.
- THE SYSTEM SHALL leave `run_pipeline`'s purity contract
  (`context_assembly.py:1008-1016`) intact: the pre-pipeline candidate list must
  be observably unchanged after both passes.

### Observability

- WHEN an assembly run completes THE SYSTEM SHALL extend `AssemblyMetrics`
  (`:259`) and `to_log_dict()` (`:286`) with `release_mode`,
  `binding_revision`, `strategy_content_hash` and `override_active`.
- WHEN a resolution verdict is reached THE SYSTEM SHALL emit exactly one
  `CONTEXT_STRATEGY_RELEASE` line per run carrying mode, agent, environment,
  strategy name, version, content hash, binding revision, `override_active`,
  verdict and reason code.
- WHEN the shadow pass completes THE SYSTEM SHALL emit exactly one
  `CONTEXT_STRATEGY_COMPARE` line carrying only the two strategy identities
  (name and version), the binding revision and the two `snapshot_id`s.
- THE SYSTEM SHALL emit both lines through the single
  `json.dumps(..., sort_keys=True)` shape `_emit_snapshot_answer` uses
  (`:1231-1239`).
- THE SYSTEM SHALL never emit a `locator`, a `selector`, or any string derived
  from a retrieved payload in either line (ADR 009 sec. 5, ADR 015 sec. 3).
- THE SYSTEM SHALL delegate every evaluation semantic — counter deltas, verdicts
  about which strategy is better, pass/fail thresholds — to
  mctlhq/mctl-agents#526, and SHALL NOT maintain a second evaluation metric
  implementation in `orchestrator/context_assembly.py`.

### Attribute reservation

- WHEN a new `mctl.*` attribute name is introduced THE SYSTEM SHALL list it in
  `docs/observability/execution-traces.md`'s attributes table marked
  `**proposed**`, in the existing `| Attribute | Where | Status | Source |`
  shape, and SHALL have a reservation PR against mctl-docs
  `docs/reference/telemetry-attributes.md` linked from this issue before it
  closes. The five names are `mctl.context.strategy.name`,
  `mctl.context.strategy.version`, `mctl.context.strategy.content_hash`,
  `mctl.context.binding.revision` and `mctl.context.release.mode`.

### Catalog integrity

- WHEN `orchestrator/context_assembly.py` changes THE SYSTEM SHALL republish
  every affected `ContextStrategyVersion` and append a new binding revision
  pinning the new hashes, so that
  `tests/test_context_release.py::test_published_catalog_hashes_are_not_drifted`
  and `::test_committed_shadow_binding_resolves` pass on the merge commit.
- THE SYSTEM SHALL never rewrite an existing binding revision in place;
  a hash refresh is a new, appended revision (ADR 019 sec. 2).

### Safety and isolation

- THE SYSTEM SHALL keep `orchestrator/context_assembly.py`'s module-scope import
  graph stdlib-only, so `tests/test_worker_isolation.py` and
  `tests/test_context_snapshot.py`'s isolation/import-direction tests pass
  unchanged.
- THE SYSTEM SHALL never let a strategy version, binding revision, content hash
  or comparison result be read by a policy, capability-eligibility or
  authorization decision, and no module added here may be imported by a policy
  path (ADR 019 "Safety invariant", ADR 009 sec. 5).

## Out of scope

- mctlhq/mctl-agents#526's evaluator, its evaluation record format, its counter
  deltas and any pass/fail threshold. Slice B emits identities and
  `snapshot_id`s only.
- Including an evaluation record reference or verdict on the
  `CONTEXT_STRATEGY_COMPARE` line. That is Slice C, once #526 exists.
- mctlhq/mctl-agents#528's real promotion-evidence checks (exact identity,
  <= 7 days, >= 3 consecutive observe runs, no `hash-mismatch`).
  `promote()`'s Slice A shadow-only refusal stays as it is.
- Creating a `production` binding, or any binding for
  `trust-freshness-ranked`. `tests/test_context_release.py::test_committed_catalog_has_no_production_binding`
  stays green.
- Populating `ContextStrategy.release_revision` / `ContextStrategy.content_hash`
  into the sealed snapshot (ADR 009 amendment 2, ADR 019 sec. 6). The fields
  exist from Slice A; nothing in the merged Slice B task text populates them, and
  doing so would change sealed bytes at `enforce`/`only`. See Open questions.
- Emitting the five reserved attributes onto real OTel spans. Slice B reserves
  the names and emits the values as structured log lines only; wiring them into
  `orchestrator/tracing.py` spans belongs with mctlhq/mctl-agents#195.
- Any new mctl-api table, route or registry client for context strategies
  (ADR 019 Non-goals).
- Changing `ISSUE_INVESTIGATOR_CONTEXT_MODE`'s `off`/`shadow`/`on` vocabulary or
  `AssemblyConfig`'s budget defaults.

## Open questions

- **Where the ladder module lives.** The merged task text says "add the rollout
  ladder to `orchestrator/context_release.py`", but task 7 and test T7 also
  require that at `off` nothing imports `context_release` and nothing imports
  `yaml`. `orchestrator/context_release.py` imports `yaml` and
  `orchestrator.context_assembly` at module scope (`context_release.py:44-51`),
  so those two requirements cannot both hold with the ladder in that file unless
  Slice A's module constants are restructured. This proposal resolves it the way
  the repository's two existing ladders already do — a dedicated, stdlib-only
  `orchestrator/context_rollout.py` beside the loader, exactly as
  `orchestrator/work_context/rollout.py` sits beside `work_context/client.py`
  and `orchestrator/lifecycle/rollout.py` beside `lifecycle/client.py`. The
  "copy `work_context/rollout.py`'s rules verbatim" and "each switch is read in
  exactly one module" instructions are honoured exactly; only the file name
  differs from the task text. A reviewer who prefers the literal file name should
  say so on the PR: the alternative is in design.md.
- **The compare line's contents.** ADR 019 sec. 5 says the
  `CONTEXT_STRATEGY_COMPARE` line carries "`AssemblyMetrics.to_log_dict()`'s
  counter deltas"; issue #527 task 9 says it carries "only the two strategy
  identities, binding revision and the two `snapshot_id`s" and explicitly
  forbids reimplementing counter-delta logic here. This proposal follows the
  issue (the later and more specific instruction) and treats the ADR sentence as
  satisfied in Slice C via #526's evaluation reference. Flagged so the ADR can be
  amended rather than silently diverged from.
- **Which environment a run resolves.** ADR 019 sec. 4 does not name the source.
  This proposal uses `ExecutionCorrelation.environment`, which
  `build_execution_correlation` already derives from `AGENT_ENVIRONMENT`
  defaulting to `"production"` (`context_assembly.py:909-911`). The only
  committed binding is `shadow`
  (`config/context-strategies/bindings/shadow/issue-investigator.yaml`), so with
  `AGENT_ENVIRONMENT` unset every stage past `off` hits an unresolvable binding —
  which is precisely the break-glass path T8 exercises, and the correct
  fail-closed default. Operators must set `AGENT_ENVIRONMENT=shadow` to actually
  observe anything.
- **What `observe` can honestly compare.** The shadow pass runs over the
  authoritative pass's pre-pipeline candidate list, as the task text requires,
  but `collect_prior_proposal` is itself strategy-sensitive
  (`context_assembly.py:821`: under the ranked strategy a prior proposal is aged
  by its `.status.yaml` `updated_at`). So the candidate `snapshot_id` is "the
  bound strategy's pipeline over the authoritative strategy's candidates", not
  "what the bound strategy would have sealed end to end". This proposal
  documents the asymmetry in the module docstring and keeps the line's field set
  exactly as task 9 specifies; #526's evaluator must not read the candidate
  `snapshot_id` as a full counterfactual.
- **`ContextStrategy.release_revision` / `content_hash`.** ADR 009 amendment 2
  and ADR 019 sec. 6 define them; Slice A shipped the fields
  (`context_snapshot.py:655-712`) and nothing populates them. Populating them at
  `enforce`/`only` would change sealed bytes at those stages only (never at
  `off`), which is what amendment 2 anticipates — but it is not in the merged
  Slice B task list, so it stays out of scope here and needs its own slice or an
  explicit reviewer instruction.
- **The cross-repo reservation PR.** Task 10's DoD requires a merged-or-open PR
  in mctl-docs. The implementer may not have write access there; the in-repo half
  (the five `**proposed**` rows plus the mctl-docs checklist entry) is
  test-verifiable, and the PR link is a human follow-up recorded on the issue.
  Proceeding on that split rather than blocking.
