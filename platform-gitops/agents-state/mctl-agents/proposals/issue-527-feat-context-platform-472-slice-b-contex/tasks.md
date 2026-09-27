# Tasks: issue-527-feat-context-platform-472-slice-b-contex

> **Correction 2026-09-27 (before approval).** Two changes to what follows:
> (1) `observe` resolves the **`shadow`** binding explicitly
> (`OBSERVE_ENVIRONMENT = "shadow"`), independent of `AGENT_ENVIRONMENT`;
> `enforce`/`only` resolve `execution.environment`. No manifest sets
> `AGENT_ENVIRONMENT`, so the production investigator runs as `production`,
> which has no binding, and relabelling it `shadow` would change the sealed
> `execution.environment` and every authoritative `snapshot_id`. Operators
> must not change `AGENT_ENVIRONMENT` to observe. (2) The catalog republish
> appends the **next** binding revision on the base it is rebased onto, not a
> hard-coded revision 2: mctlhq/mctl-agents#526 edits
> `orchestrator/context_assembly.py` in parallel and drifts the same hashes.

Numbering follows the issue's merged task text (6-10) so a reviewer can diff it
against mctl-gitops `8e8b5b54`. Tasks 11-13 are prerequisites and consequences
the merged list omits but CI will fail without.

- [ ] 6. Add `orchestrator/context_rollout.py`: a stdlib-only module (`import os`
      and nothing else) holding the four-stage ladder — `OFF/OBSERVE/ENFORCE/ONLY`,
      `_ORDER`, `ENV_VAR = "CONTEXT_RELEASE_ROLLOUT_MODE"`,
      `REQUIRED_ENV_VAR = "CONTEXT_RELEASE_REQUIRED"`, and `mode()`,
      `at_least()`, `binding_is_observed()` (`at_least(OBSERVE)`),
      `binding_decides()` (`at_least(ENFORCE)`), `binding_is_sole_selector()`
      (`at_least(ONLY)`), `context_release_required()` and `blocks_on_unknown()`
      (`binding_decides() and context_release_required()`). Copy
      `orchestrator/work_context/rollout.py`'s rules verbatim: an unrecognised
      value answers `off` and prints one warning rather than raising;
      `at_least()` raises `ValueError` on an unknown stage;
      `context_release_required()` treats `false/no/0/off` as false and
      everything else including unset as true. Document the three-switch table
      (`ISSUE_INVESTIGATOR_CONTEXT_MODE` = does assembly happen at all;
      `CONTEXT_RELEASE_ROLLOUT_MODE` = which strategy; `CONTEXT_RELEASE_REQUIRED`
      = break-glass inside enforce/only) in the module docstring in the same RST
      shape both existing ladders use, and define
      `OBSERVE_ENVIRONMENT = "shadow"`: `observe` always consults the `shadow`
      binding, `enforce`/`only` consult `execution.environment`; the docstring
      says `AGENT_ENVIRONMENT` must never be changed to enable `observe`.
      A separate file rather than `context_release.py` because task 7 and T7
      require that `off` import neither `context_release` nor `yaml`, and
      `context_release.py:44-51` imports both `yaml` and `context_assembly` at
      module scope — see design.md "Why a separate file" and alternative A.
      — DoD: with `CONTEXT_RELEASE_ROLLOUT_MODE` unset, `mode()` is `"off"`,
      all four predicates are `False`, and a subprocess that imports
      `orchestrator.context_rollout` loads neither `yaml` nor
      `orchestrator.context_release`; no file under `config/context-strategies/`
      is opened.

- [ ] 7. Wire selection into `orchestrator/context_assembly.py` (depends on 6).
      Add `replace` to the `dataclasses` import (`:42`). Add the closed reason
      vocabulary `RELEASE_REASON_OFF = "off-strategy-var-decides"`,
      `RELEASE_REASON_OBSERVE = "observe-strategy-var-decides"`,
      `RELEASE_REASON_BINDING = "binding-resolved"`,
      `RELEASE_REASON_OBSERVE_SKIPPED = "binding-unresolved-observe-skipped"`,
      `RELEASE_REASON_FALLBACK = "binding-unresolved-fallback-default"`,
      `RELEASE_REASON_OBSERVE_FAILED = "observe-pass-failed"`, a frozenset
      `RELEASE_REASONS`, a frozen `StrategyResolution` dataclass (`mode`,
      `reason`, `bound_strategy`, `bound_version`, `binding_revision`,
      `strategy_content_hash`, `override_active`, `verdict`) and
      `class ContextStrategyNotResolved(RuntimeError)` beside
      `SnapshotNotPersisted` (`:1226`) — the exception lives here so this module
      never needs `context_release` at module scope for a type. Then add
      `resolve_strategy_for_run(agent, config, *, environment=None) ->
      tuple[str, StrategyResolution | None]`, which defers
      `from orchestrator import context_rollout` into the function body and, at
      `off`, returns `(config.strategy, None)` with no import of
      `context_release`; past `off`, imports `context_release` **inside the
      function body** (the pattern `_work_context_active` (`:1242`), `_client`
      (`:1256`) and `_persist_to_work_item_store` (`:1287`) already use) and
      resolves the binding for `(agent, OBSERVE_ENVIRONMENT)` at `observe`, and
      for `(agent, environment)` at `enforce`/`only` (argument, else
      `os.getenv("AGENT_ENVIRONMENT", "production")`, matching `:909-911`). At `only`, a non-empty
      `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` raises `ContextStrategyNotResolved`
      naming both the variable and the binding path, checked before `resolve()`.
      At `observe` `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` (the strategy variable,
      not `AGENT_ENVIRONMENT`) still decides the authoritative strategy, and the
      `shadow` binding is
      observation only; an unresolvable binding at `observe` returns reason
      `binding-unresolved-observe-skipped` and never raises. At
      `enforce`/`only` the binding decides; an unresolvable binding raises
      `ContextStrategyNotResolved` when `blocks_on_unknown()`, else falls back to
      `STRATEGY_NAME` with reason `binding-unresolved-fallback-default` and
      `verdict` carrying the `ContextReleaseError.code`.
      — DoD: `tests/test_worker_isolation.py` and
      `tests/test_context_snapshot.py`'s import-direction/stdlib-only tests pass
      unchanged, proving `context_assembly`'s module-scope import graph is still
      stdlib-only; `tests/test_context_assembly.py:532
      test_module_import_is_stdlib_only` still passes with `yaml` in its
      forbidden list.

- [ ] 8. Implement the `observe` shadow pass in `assemble()` (`:1083`)
      (depends on 7). **Before** the `_COLLECTOR_ORDER` loop (`:1099`), call
      `resolve_strategy_for_run(execution.agent, config,
      environment=execution.environment)` and, when the returned strategy
      differs from `config.strategy`, rebuild both frozen dataclasses:
      `config = replace(config, strategy=effective)` and
      `assembly_input = replace(assembly_input, config=config)`. It must be
      before the collectors, not just before `run_pipeline`, because
      `collect_prior_proposal` reads `assembly_input.config.ranked` at `:821`.
      Then, after the authoritative `run_pipeline(candidates, config, now)` call
      (`:1106`) and only at `observe` with a bound strategy that differs from
      the authoritative one, run
      `run_pipeline(candidates, replace(config, strategy=bound), assembly_input.now)`
      on the same pre-pipeline candidate list — safe by `run_pipeline`'s own
      documented purity contract (`:1008-1016`, ADR 015 sec. 4's double-run
      requirement). Seal that outcome into a **local**, with the same
      `execution`, `retention`, `created_at` and `work_context` as the
      authoritative seal, solely to read its `snapshot_id`. Wrap the whole shadow
      pass in `try/except Exception` that records
      `RELEASE_REASON_OBSERVE_FAILED` and leaves the run untouched — `observe` is
      behaviour-neutral by definition. Leave `run_pipeline`'s `ContextStrategy`
      construction (`:1035-1053`) alone so `release_revision`/`content_hash`
      stay unset on every sealed snapshot.
      — DoD: the candidate snapshot never reaches `seal()`'s returned value,
      `AssemblyResult.snapshot`, `AssemblyResult.rendered` (`:1128-1130`) or
      `_persist_to_work_item_store` (`:1222`); a test asserts the authoritative
      snapshot's `content_hash` is byte-identical with the observe pass enabled
      and disabled, and a test asserts the persist client is called exactly once
      per run at `observe`.

- [ ] 9. Observability (depends on 8). Extend `AssemblyMetrics` (`:259`) and
      `to_log_dict()` (`:286`) with `release_mode: str = "off"`,
      `binding_revision: int | None = None`,
      `strategy_content_hash: str | None = None`,
      `override_active: bool = False`. Add `_emit_release_verdict` and
      `_emit_strategy_compare` beside `_emit_snapshot_answer` (`:1231-1239`),
      each a single `print("<PREFIX> " + json.dumps(line, sort_keys=True),
      flush=True)`. `CONTEXT_STRATEGY_RELEASE` is one resolution verdict per run,
      emitted unconditionally (at `off`: `mode="off"` and nulls), carrying
      `mode`, `agent`, `environment`, `strategy`, `version`, `content_hash`,
      `binding_revision`, `override_active`, `verdict`, `reason`.
      `CONTEXT_STRATEGY_COMPARE` is emitted only when a candidate `snapshot_id`
      exists and carries only `mode`, `authoritative_strategy`,
      `authoritative_version`, `authoritative_snapshot_id`, `bound_strategy`,
      `bound_version`, `bound_snapshot_id`, `binding_revision`. **Do not
      reimplement mctlhq/mctl-agents#526's evaluation metrics or counter-delta
      logic in this module** — no deltas, no ratios, no "which is better"
      verdict. When #526 yields an evaluation record/reference, include only that
      closed-vocabulary reference/verdict, added in Slice C.
      — DoD: a test asserts no `locator`, `selector` or payload byte can appear
      in either line, and a test proves release telemetry delegates evaluation
      semantics to #526 instead of maintaining a second metric implementation.

- [ ] 10. Reserve the new telemetry attribute names (depends on 9). Per
      `docs/observability/execution-traces.md` lines 13-16, any new `mctl.*`
      attribute must be listed there marked **proposed** and get a reservation PR
      against mctl-docs' `docs/reference/telemetry-attributes.md` before this
      issue closes. Add five rows to the attributes table (line 88,
      `| Attribute | Where | Status | Source |`) for
      `mctl.context.strategy.name`, `mctl.context.strategy.version`,
      `mctl.context.strategy.content_hash`, `mctl.context.binding.revision`,
      `mctl.context.release.mode`, with Where = the `CONTEXT_STRATEGY_RELEASE` /
      `CONTEXT_STRATEGY_COMPARE` lines and Source =
      `orchestrator/context_assembly.py`; add the same five names to the
      mctl-docs follow-up list (lines 266-271). Open the mctl-docs reservation PR
      and link it from issue #527; if repo access is unavailable, record the
      blocked follow-up as an issue comment rather than closing #527.
      — DoD: the attributes table lists all five as `proposed`, and the mctl-docs
      reservation PR (or the blocked-follow-up comment) is linked from this issue.

- [ ] 11. Republish the catalog and append a shadow binding revision
      (depends on 9). Tasks 7-9 edit `orchestrator/context_assembly.py`, a
      declared implementation file of **both** published versions
      (`IMPLEMENTATION_FILES_BY_STRATEGY`, `context_release.py:72-74`), so both
      `implementationHash` and `contentHash` drift and two committed tests fail.
      Run, on the final code:
      `python tools/context_release.py publish --strategy deterministic-fixed-order --version 1.0.0`,
      the same for `--strategy trust-freshness-ranked`, then
      `python tools/context_release.py promote --agent issue-investigator
      --environment shadow --strategy deterministic-fixed-order --version 1.0.0
      --promoted-by <commit author> --reason "republish pins after #527 Slice B"`.
      Never edit an existing revision in place — the history is append-only
      (ADR 019 sec. 2); `promote` appends the next revision. mctlhq/mctl-agents#526
      edits `context_assembly.py` in parallel: if it merged first, rebase, re-run
      both `publish` commands on the rebased head and let `promote` append on top
      of its revision; never hard-code a revision number. Do not create a
      `production` binding and do not bind `trust-freshness-ranked`.
      — DoD: `tests/test_context_release.py::test_published_catalog_hashes_are_not_drifted`,
      `::test_committed_shadow_binding_resolves` and
      `::test_committed_catalog_has_no_production_binding` all pass on the head
      commit; `config/context-strategies/bindings/shadow/issue-investigator.yaml`
      has exactly one more revision than on the base branch, and every earlier
      revision is byte-unchanged.

- [ ] 12. Document the operator surface (depends on 6). Add
      `# CONTEXT_RELEASE_ROLLOUT_MODE=off` and `# CONTEXT_RELEASE_REQUIRED=true`
      to `.env.example` beside the existing context block (lines 70-81), each
      with a one-line comment naming what it controls and what `off` means. In
      `docs/adr/019-context-strategy-release-contract.md`, leave sec. 4/5's text
      unchanged but note after the sec. 5 table that the compare line ships
      without counter deltas in Slice B, deferring them to
      mctlhq/mctl-agents#526 (the tension recorded in requirements.md).
      — DoD: `.env.example` documents both variables; ADR 019 sec. 5 no longer
      contradicts what the code emits.

- [ ] 13. Update the safety-invariant tests for the new module (depends on 6).
      Add `"context_rollout"` to the forbidden-substring set in
      `tests/test_context_snapshot.py:363
      test_context_release_is_not_imported_by_any_policy_module`, so the ladder
      can never become reachable from a policy path either, and extend
      `tests/test_context_assembly.py:560
      test_module_source_has_no_authorization_vocabulary` / `:572
      test_module_does_not_import_a_policy_or_permission_symbol` coverage to the
      new module.
      — DoD: both tests name `orchestrator/context_rollout.py` and fail if a
      policy-like module ever mentions it.

## Tests

Follow the in-repo precedents: `@pytest.fixture(autouse=True) def _clean_env(monkeypatch)`
calling `monkeypatch.delenv(..., raising=False)` for every switch
(`tests/test_lifecycle_rollout.py:14-17`), `capsys` for log-line assertions, and
`tests/test_context_assembly.py:36-85`'s `_assembly_input` / `_assemble` /
`_execution` builders. `tests/conftest.py` has no env fixture today; add the
autouse one locally in each new test module, not globally.

- [ ] T7. Ladder (`tests/test_context_rollout.py`, new): `off` is the default and
      every predicate is `False`; a subprocess importing
      `orchestrator.context_rollout` loads neither `yaml` nor
      `orchestrator.context_release`; `off` opens no catalog file (assert via a
      `resolve_strategy_for_run` call with a monkeypatched-to-raise
      `context_release` import, or by asserting `orchestrator.context_release`
      absent from `sys.modules` in a subprocess); `observe` runs two
      `run_pipeline` passes and lets `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY`
      decide the authoritative one; `enforce` lets the binding decide; `only`
      rejects a set `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` with
      `ContextStrategyNotResolved`; an unrecognised mode answers `off` and warns
      on stdout without raising; the stages are ordered, not independent flags;
      `at_least()` raises on an unknown stage.
- [ ] T8. Break-glass: at `enforce` with an unresolvable binding (the real
      default case — `AGENT_ENVIRONMENT=production` has no committed binding),
      `CONTEXT_RELEASE_REQUIRED` unset or `true` raises
      `ContextStrategyNotResolved`, and `=false` falls back to
      `deterministic-fixed-order` with reason
      `binding-unresolved-fallback-default` and a `verdict` drawn from
      `context_release.VERDICTS`. Also: below `enforce`,
      `CONTEXT_RELEASE_REQUIRED=true` changes nothing.
- [ ] T9. Observe isolation (the stage's whole safety claim): with
      `AGENT_ENVIRONMENT` **unset**, `CONTEXT_RELEASE_ROLLOUT_MODE=observe` and
      `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY=trust-freshness-ranked` (so the bound
      and authoritative strategies actually differ), the authoritative
      snapshot's `content_hash` and `snapshot_id` are byte-identical to the same
      inputs at `off`; `AssemblyResult.rendered` is unchanged; a fake work-item
      store client records exactly one call; the returned
      `AssemblyResult.snapshot` is the authoritative one and the candidate
      snapshot is never returned; and the pre-pipeline `candidates` list is
      observably unchanged after both passes (guards `run_pipeline`'s purity
      contract, `:1008-1016`). The `shadow` binding resolves (reason
      `observe-strategy-var-decides`, a non-null `binding_revision`) and the sealed
      snapshot's `execution.environment` is still `"production"`. Plus: a
      `seal()`/pipeline failure injected into the shadow pass leaves the run
      successful with reason `observe-pass-failed`.
- [ ] T10. Telemetry safety: neither `CONTEXT_STRATEGY_RELEASE` nor
      `CONTEXT_STRATEGY_COMPARE` can carry a `locator`, a `selector` or any
      payload-derived string — asserted recursively over the emitted dict with
      `tests/test_context_snapshot.py:262 _walk_keys`'s shape, plus the
      canary-string technique from `tests/test_context_assembly.py:288` (plant
      `CONTEXT-LEAK-CANARY` in a comment, assert it is absent from both lines
      while present in `rendered`). Also assert each line is exactly one line of
      output (no embedded newline) and parses as JSON with sorted keys.
- [ ] T11. Delegation: a module-source test over
      `orchestrator/context_assembly.py` asserting release telemetry does not
      maintain a second evaluation implementation — no `delta`/`ratio`/`score_diff`/
      `better`/`winner` vocabulary in the new emitters, no arithmetic between two
      `AssemblyMetrics`/`PipelineCounters` instances, and the compare line's key
      set is exactly the eight names task 9 lists.
- [ ] T12. Isolation: `tests/test_worker_isolation.py` passes unchanged, and
      `tests/test_context_assembly.py::test_module_import_is_stdlib_only` still
      forbids `yaml`, proving `orchestrator/context_assembly.py`'s module-scope
      imports are still stdlib-only after task 7's deferred imports.
- [ ] T13. `enforce` equivalence: an `enforce` run whose binding resolves to
      `trust-freshness-ranked` seals the byte-identical snapshot to a run with
      `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY=trust-freshness-ranked` at `off` —
      proving the substitution reaches the collectors (`:821`) and not only the
      pipeline. Requires a temporary binding fixture via
      `load_binding(..., bindings_dir=tmp_path)`-style injection or a
      monkeypatched `context_release.BINDINGS_DIR`; do **not** commit a
      `trust-freshness-ranked` binding to satisfy this.
- [ ] T14. Attribute guard: `orchestrator.tracing_sdk.key_allowed()` is `True`
      for all five reserved names (`mctl.context.strategy.name`, `.version`,
      `.content_hash`, `mctl.context.binding.revision`,
      `mctl.context.release.mode`), so a name reserved in the catalog is not
      silently dropped by the export guard's final-segment denylist
      (`orchestrator/redaction.py:26`).
- [ ] T15. Metrics shape: `AssemblyMetrics.to_log_dict()` at `off` carries
      `release_mode == "off"`, `binding_revision is None`,
      `strategy_content_hash is None`, `override_active is False`, and every
      pre-existing key is unchanged in name and value.
- [ ] T16. Catalog: `test_published_catalog_hashes_are_not_drifted` and
      `test_committed_shadow_binding_resolves` pass on the head commit (task 11),
      and `test_committed_catalog_has_no_production_binding` still passes.
- [ ] T17. Observe environment: at `observe`, `resolve_strategy_for_run` calls
      `context_release.resolve` with environment `"shadow"` for
      `environment="production"`, `"staging"` and unset; at `enforce` it passes
      the given environment through unchanged.

## Rollback

Three independent levers, in increasing blast radius. Every one of them is
available without a redeploy or a revert.

1. **Unset `CONTEXT_RELEASE_ROLLOUT_MODE`** (or set it to `off`). The ladder's
   default returns `off`, `resolve_strategy_for_run` returns
   `(config.strategy, None)` without importing `context_release`, no catalog file
   is opened, no shadow pass runs, and `AssemblyConfig.from_env()` decides exactly
   as it did before this change. Snapshots keep their bytes and `snapshot_id`s.
   Read fresh per call — the same property `_context_mode` and `_resolver_mode`
   rely on (`run_issue_investigator.py:157`) — so it takes effect on the next run.
2. **Step down one stage**, `only` -> `enforce` -> `observe` -> `off`, or set
   `CONTEXT_RELEASE_REQUIRED=false` to make an unresolvable binding
   non-blocking inside `enforce`/`only` without changing the stage. Use this when
   the catalog, not the code, is the problem.
3. **Unset `ISSUE_INVESTIGATOR_CONTEXT_MODE`** (or set it to `off`). The outer
   switch short-circuits `assemble_investigator_context` at `:1188`, so no
   assembly happens at all and the release ladder is inert whatever it is set to.
   This is the pre-#265 behaviour.

**Catalog rollback.** Task 11's appended revision N is undone by appending
N+1, not by deleting N:
`python tools/context_release.py rollback --agent issue-investigator
--environment shadow --to-revision <N-1> --promoted-by <author> --reason "..."`.
Note that after a code revert this will re-fail the drift guard, because
revision N-1's pins match the reverted code — which is the correct coupling: a
revert of tasks 7-9 and a rollback to revision N-1 belong in the same commit.

**Code revert.** `orchestrator/context_rollout.py` is new and is imported only
from inside `resolve_strategy_for_run`, so `git revert` of the Slice B commit
touches `orchestrator/context_assembly.py`,
`orchestrator/context_rollout.py`, `config/context-strategies/`,
`docs/observability/execution-traces.md`, `.env.example` and the test files, and
nothing else. No datastore, no mctl-api route, no Temporal workflow history and no
ArgoCD-managed manifest is involved. The mctl-docs reservation PR can be closed
independently; a reserved-but-unemitted attribute name is inert.
