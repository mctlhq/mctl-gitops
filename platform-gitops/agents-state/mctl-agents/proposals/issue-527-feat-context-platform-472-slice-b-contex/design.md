# Design: issue-527-feat-context-platform-472-slice-b-contex

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

## Current state

### What Slice A left on the image

`orchestrator/context_release.py` (821 lines, merged in `db32ddd` via PR #530) is
the loader/resolver for the committed context-strategy catalog. Its public
surface is `load_version`, `load_binding`, `load_binding_or_none`,
`resolve(agent, environment) -> ResolvedContextStrategy`, and the pure document
builders `promote()` / `rollback()`. Every failure is a `ContextReleaseError`
whose `.code` comes from the closed `VERDICTS` vocabulary
(`context_release.py:89-121`). Its own docstring states the position plainly:
"Nothing in `orchestrator/context_assembly.py` imports this module yet, and
nothing here changes what the investigator reads — the `off/observe/enforce/only`
rollout ladder and the `assemble()` wiring are Slice B."

The module is **not** stdlib-only. It imports `yaml` at module scope
(`context_release.py:44`) and imports four symbols from
`orchestrator.context_assembly` (`:46-51`) to build the module-level constants
`IMPLEMENTATION_FILES_BY_STRATEGY` (`:72-74`) and `_RANKER_BY_STRATEGY`
(`:79-81`). That direction matters for Slice B: it is why
`context_assembly` must import `context_release` from inside a function body, and
it is why importing `context_release` at `off` would drag `yaml` in.

The committed catalog is small and deliberately inert:

```
config/context-strategies/
  versions/deterministic-fixed-order/1.0.0.yaml   lifecycle: published, no ranker
  versions/trust-freshness-ranked/1.0.0.yaml      lifecycle: published, ranker trust-freshness-recency@1.0.0
  bindings/shadow/issue-investigator.yaml         revision 1 -> deterministic-fixed-order@1.0.0
```

There is no `bindings/production/` directory, and
`tests/test_context_release.py::test_committed_catalog_has_no_production_binding`
asserts that absence. There is no shadow binding for `trust-freshness-ranked`
either, even though that version lists `issue-investigator` under `spec.agents`.

Two committed-catalog guards run as ordinary pytest (nothing in `.github/`
invokes `tools/context_release.py`):
`test_published_catalog_hashes_are_not_drifted` (`tests/test_context_release.py:564`),
which recomputes both versions' `implementationHash` against the working tree and
fails with the exact repair command, and `test_committed_shadow_binding_resolves`
(`:580`), the `resolve` preflight that asserts `verdict == VERDICT_OK`.

### How the investigator picks a strategy today

`orchestrator/context_assembly.py` (1295 lines) is stdlib-only at module scope by
deliberate design — it imports only `orchestrator.context_snapshot` and
`orchestrator.temporal.issue_ref`, both stdlib-only themselves
(`context_assembly.py:22-27`, guarded by
`tests/test_context_assembly.py:532 test_module_import_is_stdlib_only` and
`tests/test_worker_isolation.py`).

Strategy selection is a single env-var read:
`AssemblyConfig.from_env()` (`:229-238`) reads
`ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` (constant `STRATEGY_ENV_VAR`, `:83`) into
`AssemblyConfig.strategy`, validated against `STRATEGIES = (STRATEGY_NAME,
RANKED_STRATEGY_NAME)` in `__post_init__` (`:221-223`). `AssemblyConfig.ranked`
(`:225-227`) is the derived predicate.

`run_pipeline(candidates, config, now)` (`:996-1080`) is the deterministic
selection pipeline and explicitly documents the property Slice B depends on:
"A pure function of its arguments — no collector, no I/O, no clock beyond `now` —
and it never mutates the `CandidateSource` objects it is given: every candidate is
copied before any stage rewrites it ... so the same input list can be run through
this function twice — once per strategy, as ADR 015 sec. 4's fixture contract
requires" (`:1008-1016`). `candidates = [copy.copy(c) for c in candidates]` at
`:1017` is the mechanism. It branches on `config.ranked` (`:1026`) and builds the
`ContextStrategy` identity for the sealed snapshot (`:1035-1040` ranked,
`:1053` default) — note it never sets `release_revision` or `content_hash`.

`assemble()` (`:1083-1153`) runs the five collectors in `_COLLECTOR_ORDER`
(`:856-862`), calls `run_pipeline` once (`:1106`), maps candidates to
`ContextSource`s (`:1112`), calls `seal()` (`:1114-1124`), builds `rendered`
(`:1128-1130`) and `AssemblyMetrics` (`:1132-1152`), and returns an
`AssemblyResult`. `seal()` (`context_snapshot.py:1244`) computes
`content_hash` over every field except `content_hash`, `snapshot_id` and
`created_at`, then `snapshot_id = "cs-" + content_hash[7:23]`.

**One collector is strategy-sensitive.** `collect_prior_proposal` (`:804-853`)
reads `assembly_input.config.ranked` at `:821`: under the ranked strategy it ages
the prior proposal by its `.status.yaml` `updated_at` instead of the retrieval
moment. Every other collector ignores the strategy. This is the single most
important constraint on where Slice B's substitution point can be.

`assemble_investigator_context()` (`:1156-1223`) is the feature-gated entry
point: it returns `None` at `mode == "off"`, otherwise builds the
`ExecutionCorrelation` via `build_execution_correlation()` (`:870-950`) — which
resolves `environment` from `AGENT_ENVIRONMENT`, defaulting to `"production"`
(`:909-911`) — creates the client only when `_work_context_active` says so
(`:1219`), calls `assemble()`, then calls `_persist_to_work_item_store`
(`:1222`).

### The deferred-import pattern to copy

Three functions at the bottom of `context_assembly.py` are the exact precedent
Slice B must follow:

```python
def _work_context_active(work_context):            # :1242
    from orchestrator.work_context import rollout
    from orchestrator.work_context.snapshots import is_store_execution
    ...
def _client(work_item_client):                     # :1253
    from orchestrator.work_context.client import WorkItemClient
def _persist_to_work_item_store(snapshot, client): # :1277
    from orchestrator.work_context import rollout
    from orchestrator.work_context.snapshots import SNAPSHOT_DIVERGED, persist
```

Note what `_work_context_active` imports unconditionally: the *rollout* module,
which is a dedicated stdlib-only file (`orchestrator/work_context/rollout.py`,
107 lines, imports `os` only). The heavy modules (`client`, `snapshots`) are
separate. `orchestrator/lifecycle/rollout.py` has the identical shape
(`LIFECYCLE_ROLLOUT_MODE`, `OFF/OBSERVE/ENFORCE/ONLY`, `_ORDER`, `mode()`,
`at_least()`, `computes_new_answer()`, `new_answer_may_veto()`,
`new_answer_decides()`, `blocks_on_unknown()`), and both carry the three-switch
RST table in their docstring.

### Structured log lines and telemetry safety

`_emit_snapshot_answer` (`:1231-1239`) is the one-line emitter shape:
`print("WORK_CONTEXT_SNAPSHOT " + json.dumps(line, sort_keys=True), flush=True)`.
`run_issue_investigator.py:2019` prints
`[context] context_assembly={json.dumps(result.metrics.to_log_dict(), sort_keys=True)}`.

`docs/observability/execution-traces.md` holds the attributes table
(`| Attribute | Where | Status | Source |`, line 88) where a name not yet in the
mctl-docs catalog is marked `**proposed**`; lines 13-16 state the rule ("They
need a reservation PR in mctl-docs before #195 can close") and lines 266-271 hold
the mctl-docs follow-up checklist. **There is no `mctl.context.*` row today.**
The export guard (`orchestrator/tracing_sdk.py:63 _ALLOWED_KEY`,
`orchestrator/redaction.py:26 _DENIED_KEY`) admits `mctl\.[a-z0-9_]+(\.[a-z0-9_]+)*`
and denies a key whose final dot-segment *is* `content`/`text`/`input`/... — so
`mctl.context.strategy.content_hash` (final segment `content_hash`) and
`mctl.context.*` (segment `context`, not `text`) both pass.

Leak tests: `tests/test_context_assembly.py:288
test_no_locator_selector_or_payload_leaks_into_metrics` plants a canary string in
a comment and asserts it never reaches the metrics line, with `:301` as the
positive control proving the canary *does* reach `rendered`.
`tests/test_context_snapshot.py:262 _walk_keys` is the recursive key walker, used
by `:272` and `:315`; `:363 test_context_release_is_not_imported_by_any_policy_module`
is the import-direction test that greps every policy-like module's text for the
substring `"context_release"`.

`tests/conftest.py` has no env-var fixture; `tests/test_lifecycle_rollout.py:14-17`
is the in-repo precedent (`@pytest.fixture(autouse=True) def _clean_env(monkeypatch)`
calling `monkeypatch.delenv(..., raising=False)`).

## Proposed solution

Four code changes, one catalog change, two doc changes.

### 1. `orchestrator/context_rollout.py` — the ladder (task 6)

A new module, stdlib-only (`import os` and nothing else), a byte-for-byte sibling
of `orchestrator/work_context/rollout.py`:

```python
OFF, OBSERVE, ENFORCE, ONLY = "off", "observe", "enforce", "only"
_ORDER = (OFF, OBSERVE, ENFORCE, ONLY)
ENV_VAR = "CONTEXT_RELEASE_ROLLOUT_MODE"
REQUIRED_ENV_VAR = "CONTEXT_RELEASE_REQUIRED"

def mode() -> str: ...                      # unrecognised -> OFF + one warn line, never raises
def at_least(stage: str) -> bool: ...       # ValueError on an unknown stage
def binding_is_observed() -> bool: return at_least(OBSERVE)
def binding_decides() -> bool: return at_least(ENFORCE)
def binding_is_sole_selector() -> bool: return at_least(ONLY)
def context_release_required() -> bool: ...  # false/no/0/off -> False, else True
def blocks_on_unknown() -> bool: return binding_decides() and context_release_required()
```

The docstring carries the three-switch table in `work_context/rollout.py`'s exact
RST shape, plus the reason codes below.

**Why a separate file rather than inside `context_release.py`.** Task 6 says
"add the rollout ladder to `orchestrator/context_release.py`", but task 7's and
T7's `off` requirement is "no import of `context_release`" and "imports no YAML".
`context_release.py` imports `yaml` at `:44` and pulls four symbols from
`context_assembly` at `:46-51` to build module-level constants, so importing it
at `off` violates T7 unless Slice A's constants are restructured into lazy
functions — a larger, riskier edit to just-merged code. Both existing ladders in
this repository already live in their own stdlib-only `rollout.py` beside the
heavy client module, and `_work_context_active` imports exactly that module
unconditionally while deferring `client`/`snapshots`. Following that precedent
satisfies every DoD literally; only the file name differs from the task text.
Recorded as the first open question in requirements.md.

### 2. `resolve_strategy_for_run` in `context_assembly.py` (task 7)

```python
RELEASE_REASON_OFF = "off-strategy-var-decides"
RELEASE_REASON_OBSERVE = "observe-strategy-var-decides"
RELEASE_REASON_BINDING = "binding-resolved"
RELEASE_REASON_OBSERVE_SKIPPED = "binding-unresolved-observe-skipped"
RELEASE_REASON_FALLBACK = "binding-unresolved-fallback-default"
RELEASE_REASON_OBSERVE_FAILED = "observe-pass-failed"
RELEASE_REASONS = frozenset({...})

class ContextStrategyNotResolved(RuntimeError):
    """The bound strategy could not be resolved at a stage where that blocks."""
    # sibling of SnapshotNotPersisted (:1226); defined here so context_assembly
    # never imports context_release at module scope to get an exception type.

@dataclass(frozen=True)
class StrategyResolution:
    mode: str
    reason: str
    bound_strategy: str | None
    bound_version: str | None
    binding_revision: int | None
    strategy_content_hash: str | None
    override_active: bool
    verdict: str | None

def resolve_strategy_for_run(
    agent: str, config: AssemblyConfig, *, environment: str | None = None
) -> tuple[str, StrategyResolution | None]:
```

Control flow:

- `from orchestrator import context_rollout` — a deferred import at the top of
  the body, stdlib-only, the same unconditional shape `_work_context_active`
  uses.
- `off`: `return (config.strategy, None)`. No `context_release` import, no YAML,
  no catalog file opened.
- past `off`: `from orchestrator import context_release` **inside the body**.
  The binding environment is `OBSERVE_ENVIRONMENT = "shadow"` at `observe`,
  whatever `environment` says; at `enforce`/`only` it is `environment`, which
  defaults to `os.getenv("AGENT_ENVIRONMENT", "production")`, matching
  `build_execution_correlation` (`:909-911`); `assemble()` passes
  `execution.environment` explicitly so the two can never disagree.
  `execution` itself is never rebuilt, so the sealed
  `execution.environment` is untouched at every stage.
- `only` + a non-empty `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` in the environment
  -> `ContextStrategyNotResolved`, message naming both the variable and the
  binding path. Checked before `resolve()`, so the error does not depend on the
  catalog being loadable.
- `resolve(agent, binding_environment)` inside `try/except context_release.ContextReleaseError`.
  - success at `observe`: `(config.strategy, StrategyResolution(reason=OBSERVE, bound_strategy=resolved.strategy, ...))`.
  - success at `enforce`/`only`: `(resolved.strategy, StrategyResolution(reason=BINDING, ...))`.
  - failure at `observe`: `(config.strategy, StrategyResolution(reason=OBSERVE_SKIPPED, bound_strategy=None, verdict=exc.code))`.
  - failure at `enforce`/`only`: raise `ContextStrategyNotResolved` when
    `blocks_on_unknown()`, else `(STRATEGY_NAME, StrategyResolution(reason=FALLBACK, verdict=exc.code))`.

The 2-tuple shape is exactly what task 7 specifies at `off`; the second element
carries everything tasks 8 and 9 need without a second lookup.

### 3. The observe shadow pass in `assemble()` (task 8)

Two insertion points, and the order between them is the design's whole point.

**Before the collector loop (`:1099`):**

```python
effective, resolution = resolve_strategy_for_run(
    execution.agent, config, environment=execution.environment
)
_emit_release_verdict(execution, config, effective, resolution)
if effective != config.strategy:
    config = replace(config, strategy=effective)
    assembly_input = replace(assembly_input, config=config)
```

`replace` comes from `dataclasses` (add it to the `:42` import); both
`AssemblyConfig` and `AssemblyInput` are frozen dataclasses. The substitution has
to happen here, not just before `run_pipeline`, because `collect_prior_proposal`
reads `config.ranked` at `:821`. Substituting later would produce a snapshot
neither pure strategy would ever produce: a prior proposal aged by retrieval time
but ranked by the ranker.

**After the authoritative `run_pipeline` (`:1106`):**

```python
observe_snapshot_id = None
if resolution is not None and resolution.bound_strategy not in (None, config.strategy) \
        and not context_rollout_decides:          # observe only, never enforce/only
    try:
        shadow = run_pipeline(candidates, replace(config, strategy=resolution.bound_strategy),
                              assembly_input.now)
        observe_snapshot_id = seal(
            execution=execution, strategy=shadow.strategy, budget=shadow.budget,
            retention=retention, created_at=_iso(assembly_input.now),
            work_context=work_context,
            sources=tuple(_to_context_source(c) for c in shadow.candidates),
            evidence_refs=(), conflicts=shadow.conflicts,
        ).snapshot_id
    except Exception as exc:
        observe_snapshot_id = None
        resolution = replace(resolution, reason=RELEASE_REASON_OBSERVE_FAILED)
```

Three properties, each one a DoD:

- `candidates` is the **pre-pipeline** list. `run_pipeline` copies it (`:1017`)
  and is documented pure (`:1008-1016`), so the second pass cannot see the
  first's rewrites, and the first pass's `outcome` is already materialised.
  `copy.copy` is shallow, but every field a stage rewrites is a scalar and `raw`
  is `bytes` (immutable), so a rebind on the copy cannot reach the original.
- The candidate snapshot is a **local**. Nothing assigns it to `snapshot`, to
  `AssemblyResult.snapshot`, to `rendered` (`:1128-1130`), or hands it to
  `_persist_to_work_item_store` (`:1222`, which takes `result.snapshot`). Only its
  `snapshot_id` string escapes, into the compare line.
- The `try/except` is load-bearing, not defensive noise: `observe` is
  behaviour-neutral by definition, so a `seal()` validation error or a pipeline
  bug in the candidate branch must not fail a run the authoritative pass already
  completed.

The authoritative seal (`:1114-1124`) is untouched, so at `off` and at `observe`
the authoritative `content_hash`/`snapshot_id` are byte-identical to today. At
`enforce`/`only` the authoritative bytes change only because the strategy
genuinely changed — which is the point of those stages.

`run_pipeline`'s `ContextStrategy` construction stays as it is, so
`release_revision`/`content_hash` remain unset on every sealed snapshot at every
stage. That keeps the fixture and every historical `snapshot_id` intact and keeps
ADR 009 amendment 2's population out of this slice (see requirements.md
Open questions).

### 4. Observability (task 9)

`AssemblyMetrics` (`:259`) gains four fields with `off`-safe defaults —
`release_mode: str = "off"`, `binding_revision: int | None = None`,
`strategy_content_hash: str | None = None`, `override_active: bool = False` —
each mirrored into `to_log_dict()` (`:286`). They are ids, a closed-vocabulary
mode, a hash and a bool: nothing payload-derived, so
`tests/test_context_assembly.py:288`'s canary test stays green by construction.

Two emitters beside `_emit_snapshot_answer` (`:1231`), each a single
`json.dumps(..., sort_keys=True)`:

```
CONTEXT_STRATEGY_RELEASE {"agent":..,"binding_revision":..,"content_hash":..,"environment":..,
   "mode":..,"override_active":..,"reason":..,"strategy":..,"verdict":..,"version":..}
CONTEXT_STRATEGY_COMPARE {"authoritative_snapshot_id":..,"authoritative_strategy":..,
   "authoritative_version":..,"binding_revision":..,"bound_snapshot_id":..,
   "bound_strategy":..,"bound_version":..,"mode":..}
```

RELEASE is emitted once per run, unconditionally (including at `off`, where
`mode` is `off` and everything binding-shaped is `null`) — one resolution verdict
per run, as ADR 019 sec. 5 requires. COMPARE is emitted only when a candidate
`snapshot_id` was actually produced.

The compare line carries **no counter deltas and no verdict about which strategy
is better**. Task 9 forbids reimplementing #526's evaluation metrics or
counter-delta logic here, and the two `snapshot_id`s plus the two identities are
exactly the join key #526's evaluator needs. A module-source test proves the
absence rather than trusting the reviewer: no `delta`/`better`/`score_diff`
vocabulary and no arithmetic over two `AssemblyMetrics` in this module.

### 5. Catalog republish (the task the issue's list omits)

Tasks 7-9 change `orchestrator/context_assembly.py`, which is a declared
implementation file of **both** published versions
(`IMPLEMENTATION_FILES_BY_STRATEGY`, `context_release.py:72-74`). So
`implementationHash` drifts for both, `contentHash` drifts with it (the
implementation block is inside the hashed spec), and two committed tests fail on
the merge commit: `test_published_catalog_hashes_are_not_drifted` (`:564`) and
`test_committed_shadow_binding_resolves` (`:580`, because revision 1 pins the old
hashes). The repair is the documented one, run twice, plus an **appended**
binding revision:

```
python tools/context_release.py publish  --strategy deterministic-fixed-order --version 1.0.0
python tools/context_release.py publish  --strategy trust-freshness-ranked    --version 1.0.0
python tools/context_release.py promote  --agent issue-investigator --environment shadow \
    --strategy deterministic-fixed-order --version 1.0.0 \
    --promoted-by <commit-author> --reason "republish pins after #527 Slice B"
```

`promote` appends the next revision — revision 2 if this slice merges first,
revision 3 if mctlhq/mctl-agents#526 (which also edits `context_assembly.py`)
already appended one; earlier revisions are never rewritten (ADR 019 sec. 2,
append-only). Run the commands on the final, rebased head. `promote`'s Slice A guard permits `shadow` only, which is the only
environment that has a binding — so this repair needs no change to `promote()`.
`publish` with no `--lifecycle` is a pure hash refresh by design
(`build_version_document`'s docstring, `:749-763`).

### 6. Docs (task 10 and the env surface)

- `docs/observability/execution-traces.md`: five new rows in the attributes table
  marked `**proposed**`, Where = `CONTEXT_STRATEGY_RELEASE` /
  `CONTEXT_STRATEGY_COMPARE` log lines (not a span yet — emitting them onto spans
  is #195), Source = `orchestrator/context_assembly.py`. Plus the five names added
  to the mctl-docs follow-up list at lines 266-271.
- mctl-docs reservation PR against `docs/reference/telemetry-attributes.md`,
  linked from issue #527.
- `.env.example`: `# CONTEXT_RELEASE_ROLLOUT_MODE=off` and
  `# CONTEXT_RELEASE_REQUIRED=true` beside the existing context block
  (lines 70-81).

## Alternatives

**A. Put the ladder inside `orchestrator/context_release.py` verbatim, and make
that module stdlib-only-importable.** This is the literal task text. It requires
moving `import yaml` into `_read_yaml_and_hash` (the precedent exists —
`orchestrator/capability.py` defers its own YAML import, asserted by
`tests/test_worker_isolation.py:104`) *and* deferring the
`from orchestrator.context_assembly import ...` at `:46-51`, which means turning
the module-level `IMPLEMENTATION_FILES_BY_STRATEGY` and `_RANKER_BY_STRATEGY`
dicts into lazily-built functions and updating every call site plus
`tools/context_release.py`. Dropped: it is a structural rewrite of code merged
days ago, it makes `context_release.py` a dual-purpose module (a switch nobody
else reads, plus a YAML loader), and it buys nothing the sibling module does not
already buy. Kept as the fallback if a reviewer insists on the literal path.

**B. Read `CONTEXT_RELEASE_ROLLOUT_MODE` directly in `context_assembly.py`'s
`off` fast path, then import the ladder past `off`.** Cheapest possible `off`
path and no new module. Dropped because it breaks the one rule both existing
ladders state explicitly and that task 6 restates: each switch is read in exactly
one module. Two readers of one variable is how a mode ends up meaning two
different things in one process.

**C. Run the observe pass end-to-end — a second collector run under the bound
strategy — instead of reusing the pre-pipeline candidate list.** This is the only
way to get a candidate `snapshot_id` that is a true counterfactual, because
`collect_prior_proposal` is strategy-sensitive (`:821`). Dropped: it doubles the
I/O of every observed run (a second repo walk, a second `.status.yaml` read),
`observe` is supposed to be behaviour- *and* cost-neutral, and the task text
explicitly specifies "the same pre-pipeline candidate list". The asymmetry is
documented in the module docstring and in requirements.md instead, so #526's
evaluator cannot mistake the candidate id for a full counterfactual.

**D. Persist or return the candidate snapshot so #526 can read the whole document
later.** Dropped hard: it would put a second snapshot into the work-item store for
one execution, which the store's insert-only divergence rule
(`_persist_to_work_item_store`, `:1277-1295`) is specifically built to refuse, and
it would make `observe` behaviour-affecting. The `snapshot_id` is a 19-character
content-addressed handle; #526's evaluator can recompute the document from a
fixture (ADR 015 sec. 4's double-run contract is exactly that).

## Platform impact

**Migrations.** None in any datastore. One catalog change: two republished
version documents and one appended binding revision (the next one, shadow). The
append is the audit trail; nothing is rewritten.

**Backward compatibility.** The default is `off` at every layer.
`CONTEXT_RELEASE_ROLLOUT_MODE` unset means no catalog file is opened,
`context_release` is never imported, `AssemblyConfig.from_env()` decides exactly
as today, and every sealed snapshot keeps its exact bytes and `snapshot_id` —
including the golden fixture, because `run_pipeline`'s `ContextStrategy`
construction is untouched. The only visible change at `off` is four new keys on
the `[context] context_assembly=` metrics line (`release_mode:"off"` and three
nulls/false) and one new `CONTEXT_STRATEGY_RELEASE` line per run. Neither is
parsed by anything today; `AssemblyMetrics.to_log_dict()` has no pinned-key-set
test (only `ContextSnapshot.to_log_dict()` does, at
`tests/test_context_snapshot.py:424-438`, and that one is not touched).

**The three switches interact, and the outer one wins.**
`ISSUE_INVESTIGATOR_CONTEXT_MODE=off` short-circuits
`assemble_investigator_context` at `:1188` before any of this runs, so the
release ladder is inert whatever it is set to. At
`ISSUE_INVESTIGATOR_CONTEXT_MODE=shadow`, `_assemble_context`
(`run_issue_investigator.py:2009-2013`) catches every exception and degrades to a
warning — so an `only`-mode override rejection or a break-glass failure downgrades
to "no snapshot this run", which is the correct fail-safe. At `=on` it re-raises
and fails the investigation. This is worth stating in the ladder docstring because
it means `CONTEXT_RELEASE_REQUIRED=true` only actually blocks a run when the
assembly pilot is at `on`.

**Resource impact.** At `off`: one extra `os.environ.get` and one extra
`json.dumps` of a nine-key dict per run. At `observe`: one extra `run_pipeline`
(pure, in-memory, over <= 100 candidates) and one extra `seal()` per run — no
network, no disk beyond the one catalog YAML pair `resolve()` reads, no second
collector pass. At `enforce`/`only`: the catalog read only. Nothing here touches
the long-lived Temporal worker's import graph.

**Risks and mitigations.**

| Risk | Mitigation |
|---|---|
| The candidate snapshot leaks into the prompt or the store, making `observe` behaviour-affecting | It is a local whose only escaping value is a `snapshot_id` string; T9 asserts byte-identical authoritative `content_hash` with and without the pass, unchanged `rendered`, and exactly one persist-client call per run |
| The new deferred import quietly makes `context_assembly` non-stdlib-only | `tests/test_worker_isolation.py` and `tests/test_context_assembly.py:532` run unchanged; T12 is exactly this assertion |
| `enforce` silently substitutes a strategy while the collectors still behave as the old one | The substitution happens before `_COLLECTOR_ORDER` and rebuilds `assembly_input` via `replace`; a test asserts an `enforce` run's snapshot equals a run with the same strategy set by env var |
| `observe` in production finds no binding because `AGENT_ENVIRONMENT` is `production` | `observe` resolves the `shadow` binding explicitly (`OBSERVE_ENVIRONMENT`); T9 runs with `AGENT_ENVIRONMENT` unset and asserts a resolved shadow binding and an unchanged sealed `execution.environment == "production"`. At `enforce`/`only`, a missing `production` binding is the fail-closed T8 path, by design |
| #526 and this slice both republish the catalog | Neither hard-codes a revision; the second to merge rebases, re-runs `publish` and appends the next revision (task 11) |
| The catalog drift guard fails the PR because the republish was forgotten | An explicit task with the exact two `publish` commands and the `promote` append; the guard's own failure message already prints the repair command |
| A new `mctl.*` attribute is dropped by the export guard | Checked against `redaction._DENIED_KEY`'s final-segment rule: `content_hash` is not `content`, `context` is not `text`; a unit test asserts `tracing_sdk.key_allowed()` is true for all five names |
| Slice B's telemetry grows a second evaluation implementation that then diverges from #526 | Task 9's explicit prohibition plus a module-source test asserting no counter-delta/scoring vocabulary and no arithmetic over two `AssemblyMetrics` in this module |
| The ladder module's name diverges from the merged task text | Documented as the first open question with the literal alternative (A) fully specified, so a reviewer can redirect in one comment |
