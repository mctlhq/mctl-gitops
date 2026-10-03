# Design: issue-472-feat-context-platform-version-promote-ob

> **Correction 2026-09-27.** The first investigation assumed the evaluator
> side of #266 existed on `main`; it does not. The missing evaluator,
> fixtures, baseline and replay work is now mctlhq/mctl-agents#526.
> Production promotion is therefore fail-closed on #526 evidence. The work is
> also split into A/B/C; a single approval never authorizes the whole design.

## Current state

### Strategies exist, but only as module constants

`orchestrator/context_assembly.py` declares both strategies as literals:

```python
STRATEGY_NAME = "deterministic-fixed-order"      # :71
STRATEGY_VERSION = "1.0.0"                       # :72
RANKED_STRATEGY_NAME = "trust-freshness-ranked"  # :78
RANKED_STRATEGY_VERSION = "1.0.0"                # :79
RANKER_NAME = "trust-freshness-recency"          # :80
RANKER_VERSION = "1.0.0"                         # :81
STRATEGY_ENV_VAR = "ISSUE_INVESTIGATOR_CONTEXT_STRATEGY"   # :83
STRATEGIES = (STRATEGY_NAME, RANKED_STRATEGY_NAME)          # :84
```

Selection is one environment read in `AssemblyConfig.from_env()`
(`:229-238`), validated in `AssemblyConfig.__post_init__` (`:221-223`).
`AssemblyConfig.ranked` (`:225-227`) is the single branch point, consumed by
`run_pipeline` (`:1026`). The strategy's identity reaches the sealed document
as a `ContextStrategy` built inside `run_pipeline` (`:1035-1040` ranked,
`:1053` default) and copied onto `AssemblyMetrics.strategy_name`/
`strategy_version` (`:1146-1147`).

Three gaps follow directly:

1. **The version names no bytes.** `"1.0.0"` is a literal. Editing
   `rank_candidates` (`:493`), `detect_conflicts`, `flag_stale`,
   `apply_budget` or the ordering tables `_TRUST_ORDER`/`_FRESHNESS_ORDER`
   (`:93-94`) changes what the model sees while every snapshot keeps claiming
   `1.0.0`. The repository already knows this is wrong and already solved it
   once for a sibling resource: `resolver._model_policy_version()`
   (`resolver.py:866`) pins `config/model-policy.yaml` by "the declared schema
   `version:` plus a content hash, so a policy edit that changes model routing
   without bumping `version:` still changes the identifier a plan pins."
   Nothing equivalent exists for a context strategy.
2. **Selection has no environment, no revision and no history.** One process-
   wide env var decides for every run in the deployment. There is no record of
   who changed it, when, why, or what it was before.
3. **Rollback is "unset the variable".** Effective, but unaudited, and it
   cannot express "go back to the pair that was live on Tuesday".

### The precedents this design must mirror rather than reinvent

- **ADR 007 + `orchestrator/resolver.py`** already run exactly this lifecycle
  for agents: immutable published versions, one atomic per-environment
  binding, promote/deprecate/disable/rollback transitions
  (`docs/adr/007-agent-definition-execution-profile-contract.md:117-212`).
  `load_release_binding` (`resolver.py:768-862`) is the concrete loader: it
  checks `apiVersion`/`kind`, cross-checks that `metadata.environment` and
  `metadata.agent` agree with the path the file was read from (`:786-802`),
  **requires a `sha256:` content pin** and says in the error message why
  ("without it the definition half of this binding is unpinned", `:806-811`),
  refuses a non-`published` `registryLifecycle` (`:826-832`), and requires a
  positive-integer `bindingRevision` (`:834-836`).
- **Two four-stage rollout ladders**, `orchestrator/lifecycle/rollout.py` and
  `orchestrator/work_context/rollout.py`, share one vocabulary
  (`OFF/OBSERVE/ENFORCE/ONLY`), one `at_least()` helper, one "unrecognised
  value answers OFF and warns rather than raising" rule, and one break-glass
  split (`WORK_CONTEXT_REQUIRED` read only through `blocks_on_unknown()`).
  `work_context/rollout.py`'s docstring states the discipline explicitly: each
  switch has exactly one job and is read in exactly one module.
- **`run_pipeline` was already extracted to be run twice.** ADR 015 sec. 4
  required it and its docstring says so: "A pure function of its arguments —
  no collector, no I/O, no clock beyond `now` — and it never mutates the
  `CandidateSource` objects it is given... so the same input list can be run
  through this function twice — once per strategy" (`context_assembly.py:1008-1016`).
  The observe stage of this design is that sentence's first production caller.
- **Optional-field growth on a sealed document is precedented.** ADR 009
  amendment 1 added `conflicts` as an optional field that `to_dict()` omits
  when empty and that enters `content_hash` only when non-empty
  (`context_snapshot.py:866-867`, `:1202-1206`), so every pre-amendment
  snapshot kept its `snapshot_id`.
- **Length-prefixed multi-file hashing is precedented.**
  `tools/publish_agent_release.py`'s `prompt_hash` is "sha256 over each prompt
  source, in sorted order by its identifier, as length-prefixed
  `<len>\n<identifier><len>\n<file bytes>` pairs", with a written rationale for
  why plain concatenation is ambiguous.
- **`ContextStrategy` is the snapshot field to extend** — `name`, `version`,
  `ranker_name`, `ranker_version`, with `to_dict`/`from_dict` and strict
  unknown-key rejection (`context_snapshot.py:649-678`).

## Proposed solution

A new ADR (`docs/adr/019-context-strategy-release-contract.md` — 019 is the
next free number: 016 is the shepherd merge-approval ADR from
mctlhq/mctl-agents#524, and 017/018 are on `main`) plus four code surfaces. Nothing changes
behaviour until an operator moves one environment variable.

### 1. `ContextStrategyVersion` — an immutable, content-pinned version

Committed at `config/context-strategies/versions/<name>/<version>.yaml`,
alongside `config/model-policy.yaml`:

```yaml
apiVersion: context.mctl.ai/v1alpha1
kind: ContextStrategyVersion
metadata:
  name: trust-freshness-ranked
  version: 1.0.0
spec:
  lifecycle: published            # published | deprecated | disabled
  ranker:
    name: trust-freshness-recency
    version: 1.0.0
  implementation:
    files:                        # hashed, sorted, length-prefixed
      - orchestrator/context_assembly.py
      - orchestrator/context_snapshot.py
    implementationHash: "sha256:..."
  contentHash: "sha256:..."       # over this document minus contentHash
  agents: [issue-investigator]
```

`implementationHash` is the load-bearing field and the direct answer to gap 1:
it is what makes `1.0.0` name bytes. It uses
`tools/publish_agent_release.py`'s exact length-prefixed encoding, for the
reason stated there — plain concatenation lets text move between one file's
path and the next file's content without changing the digest.

`spec.lifecycle` reuses ADR 007's registry-version vocabulary and its rules
verbatim (`007-...:193-197`): `deprecated` still resolves for existing
bindings but may not be newly promoted; `disabled` does not resolve at all.

### 2. `ContextStrategyBinding` — atomic, append-only, per (agent, environment)

Committed at `config/context-strategies/bindings/<environment>/<agent>.yaml`,
laid out like `CATALOG_RELEASES_DIR / environment / f"{agent}.yaml"`
(`resolver.py:772`) so the path/metadata cross-check is the same check:

```yaml
apiVersion: context.mctl.ai/v1alpha1
kind: ContextStrategyBinding
metadata:
  agent: issue-investigator
  environment: shadow
spec:
  history:
    - revision: 1
      strategy: deterministic-fixed-order
      version: 1.0.0
      contentHash: "sha256:..."
      implementationHash: "sha256:..."
      promotedBy: "<github-login>"
      promotedAt: "2026-09-27T00:00:00Z"
      reason: "inert shadow baseline: today's default, made explicit"
      evidence: {kind: none, ref: null, evaluatorVersion: null}
```

The active entry is the highest `revision`; history is never rewritten. A
promotion appends; a rollback appends a revision that copies an exact prior
revision's `(strategy, version, contentHash, implementationHash)` and records
`rollbackOf: <revision>`. This is ADR 007's "rollback restores the exact
previous compatible tuple and records a new binding revision, preserving
history" (`007-...:163-166`) and matches the platform's own
`rollback_agent_binding` semantics: an exact revision, "never a guess at one
step back".

The `evidence` block is the release-side seam to the evaluation contract.
The missing implementation from #266 is now mctlhq/mctl-agents#526.
`evidence.kind: none` is legal only for `shadow`; production accepts only
`context-eval` evidence naming the exact strategy/version/contentHash/
implementationHash. The newest observation must be no older than **7 days**,
must represent at least **3 consecutive observe-mode investigations**, and none
may carry `hash-mismatch`. Missing, stale, insufficient or mismatched evidence
fails closed. Passing this validation never promotes automatically: the binding
revision still arrives through a reviewed commit. The 7-day window and the
3-run minimum are **v1 promotion policy constants**, named as such in ADR 019
and changed only by amending it: release policy, not a property of the
evaluator.

### 3. `orchestrator/context_release.py` — loader, resolver, rollout ladder

One new module. It parses YAML like every other catalog in the repo
(`resolver._read_yaml_and_hash`, `manifest.load`), which means it cannot be
imported at module scope by `orchestrator/context_assembly.py`: that module is
stdlib-only on purpose ("Stdlib only, deliberately... so this module stays
importable by whatever imports the issue-investigator's pure helpers without
pulling in `claude_agent_sdk`", `context_assembly.py:22-27`), and
`tests/test_worker_isolation.py` plus `tests/test_context_snapshot.py`'s
import-direction test keep that honest for the 256Mi worker of ADR 008.

The resolution is the deferred import this very file already uses three times
for exactly this reason — `_work_context_active`, `_client` and
`_persist_to_work_item_store` all do `from orchestrator.work_context import
...` *inside the function body* (`context_assembly.py:1243`, `:1256`,
`:1287`), and `manifest._parse_fields_v1alpha2` defers its `resolver` import to
break a cycle. `context_release` is imported the same way, inside the one
function that consults the ladder, and only when the mode is past `off`. At
`off` — the default — the module is never imported, so the stdlib-only import
graph is unchanged and the isolation tests keep passing untouched.

Reading and hashing use `resolver._read_yaml_and_hash`'s discipline: parse and
hash **the same bytes**, because a pin that can describe different content than
was parsed "is not a weaker guarantee, it is the absence of one".

Public surface:

- `load_version(name, version) -> ContextStrategyVersion` — apiVersion/kind
  allow-list, lifecycle check, `contentHash` recomputation,
  `implementationHash` recomputation against the files in the running image.
  Every failure is a raise naming the file and the fix, in
  `load_release_binding`'s style.
- `load_binding(agent, environment) -> ContextStrategyBinding` — path/metadata
  cross-check, monotonic gapless revision check, active-revision selection.
- `resolve(agent, environment) -> ResolvedContextStrategy` — the frozen result
  carrying `strategy`, `version`, `ranker_name`, `ranker_version`,
  `content_hash`, `implementation_hash`, `release_revision`, `environment`,
  `verdict`. Fails closed on a disabled version or a hash mismatch.
- `promote(binding, ...) -> ContextStrategyBinding` and
  `rollback(binding, revision, ...) -> ContextStrategyBinding` — pure
  functions returning the next document. They never write; the CLI writes.

A sibling `orchestrator/context_release/rollout`-shaped section in the same
module (kept in one file because it is small, unlike the two package-level
ladders) implements the ladder:

| `CONTEXT_RELEASE_ROLLOUT_MODE` | Behaviour |
|---|---|
| `off` (default) | No binding is loaded. `AssemblyConfig.from_env()` unchanged. Byte-for-byte today. |
| `observe` | Binding resolved and logged. The bound strategy runs as a **second, non-authoritative** `run_pipeline` pass over the same candidate list; the env var still decides what the model reads. |
| `enforce` | The binding selects the authoritative strategy. An unresolvable binding blocks when `CONTEXT_RELEASE_REQUIRED` (default true), else falls back to `deterministic-fixed-order` with a logged reason code. |
| `only` | As `enforce`, and a set `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` is a hard error, so the env var can never silently shadow the binding. |

`mode()` answers `off` and warns on an unrecognised value, never raising —
copied from `work_context/rollout.py:mode()`, for its stated reason (a typo in
a gitops env map must not crash the investigator).

### 4. Wiring: `assemble()` gains one optional shadow pass

`context_assembly.assemble()` (`:1083`) changes in three bounded ways:

1. Before the pipeline, `resolve_strategy_for_run()` decides `config.strategy`
   from the ladder instead of assuming `AssemblyConfig.from_env()`'s value,
   and returns the `ResolvedContextStrategy | None` so the caller can log it.
2. At `observe`, after the authoritative `run_pipeline` call (`:1106`), a
   second `run_pipeline(candidates, replace(config, strategy=bound), now)`
   runs on the same pre-pipeline candidate list. This is free of I/O and
   collector cost by construction — `run_pipeline` copies its candidates and
   touches nothing else. Its `PipelineOutcome` is locally sealed only to
   obtain its `snapshot_id`. `CONTEXT_STRATEGY_COMPARE` carries correlation
   and identity only (active/candidate strategy identity, binding revision and
   snapshot ids); evaluation metrics and verdicts come from #526 rather than
   being reimplemented here. The candidate is **never** persisted, rendered or
   returned: only `outcome` reaches `seal()`, `AssemblyResult.rendered`
   (`:1128-1130`) and `_persist_to_work_item_store` (`:1222`), whose
   insert-only store would correctly refuse a second document for the same
   execution anyway.
3. `AssemblyMetrics` gains `release_mode`, `binding_revision`,
   `strategy_content_hash` and `override_active`; `to_log_dict()` (`:286`)
   carries them. Counts, ids and hashes only — ADR 015 sec. 3's rule is
   unchanged.

### 5. Durable provenance: ADR 009 amendment 2

`ContextStrategy` (`context_snapshot.py:649`) gains two optional fields,
`release_revision: int | None` and `content_hash: str | None`, following
amendment 1's rule exactly: `to_dict()` omits them when unset, they enter the
snapshot's `content_hash` only when present, and `from_dict` accepts but does
not require them. Consequences, all intended:

- Every snapshot sealed at mode `off` — including
  `tests/fixtures/context/investigator-snapshot.json` and every snapshot
  already persisted under #431/#490 — keeps its exact bytes and
  `snapshot_id`. The golden-fixture test is the proof, and it must pass
  unchanged.
- A snapshot sealed under a binding is durably attributable to that binding
  revision in the `execution-record`-class store, not only in
  `telemetry`-class logs that expire first (ADR 009 sec. 7).

This is the only part of ADR 009 this proposal touches, and it is the one part
sec. 6 explicitly permits ("a future ... pair can be added as optional fields
without an `apiVersion` bump"). The field shape/owner table, the hash rule, the
lifecycle, the boundary table and the vocabularies are untouched.

### 6. `tools/context_release.py` — the operator CLI

Mirrors `tools/publish_agent_release.py`'s shape (argparse, `--dry-run`,
writes files, prints what it did):

- `publish --strategy NAME --version X.Y.Z` — writes/refreshes a version
  document with freshly computed hashes.
- `promote --agent A --environment E --strategy N --version V --reason R
  [--evidence-kind K --evidence-ref REF]` — appends a revision.
- `rollback --agent A --environment E --to-revision N --reason R` — appends a
  restoring revision.
- `resolve --agent A --environment E` — prints what a run would resolve,
  including every check that passed. This is also the CI preflight.

Because the catalog is in-repo, every one of these is a reviewed commit: the
promoter identity is the commit author and the audit trail is git history,
which is exactly ADR 007's "Git/GitOps owns reviewed draft definitions and
desired catalog state" while "what actually ran" stays with the snapshot and
the execution record (`007-...:213-224`).

### 7. CI guard

`.github/workflows/pr-validation.yml` already runs pytest, ruff and mypy. A
test — not a new workflow — recomputes every published version's
`implementationHash` and fails with the exact `tools/context_release.py
publish` command when a change to `orchestrator/context_assembly.py` did not
come with a republished version. This is the mechanism that makes version
identity un-driftable; without it the whole scheme is decoration.

## Delivery slices

This proposal's `tasks.md` is **Slice A only**. Slice B is
mctlhq/mctl-agents#527 and Slice C is mctlhq/mctl-agents#528, because one
DevLoop approval runs the implementer over the whole `tasks.md`.

- **Slice A — inert contract/catalog.** ADR 019, ADR 009 optional provenance
  fields, strategy-version catalog, shadow-only binding, release loader/CLI and
  CI drift guard. It changes no runtime selection.
- **Slice B — rollout wiring/observation.** Does **not** depend on #526. Adds
  off/observe/enforce/only resolution, the `observe` shadow pass and release
  telemetry. `observe` changes nothing the model reads, seals or persists, and
  it has to exist before the evaluator and the gate so there is something to
  measure. Slice B creates no production binding; with only the shadow binding
  from Slice A, a production resolution at `enforce`/`only` is unresolvable
  and takes the documented `CONTEXT_RELEASE_REQUIRED` path.
- **Slice C — production gate and operator lifecycle.** **Hard dependency on
  mctlhq/mctl-agents#526** (merged and on the running image), after
  republishing any whole-file `implementationHash` #526 invalidates. Adds
  production evidence validation against #526's records, the soak gate (the v1
  policy constants: 3 consecutive observe-mode runs, <= 7 days old, exact
  identity match), production promotion, and the runbook/docs. Each slice gets
  its own review/approval.

The ladder is therefore `A: contract -> B: observe machinery -> #526:
evaluator -> C: production gate -> production promotion`.

## Alternatives

1. **New mctl-api tables and routes (`ContextStrategyVersion`,
   `ContextStrategyBinding`) mirroring the agent registry, promoted by an MCP
   call.** Rejected for v1 on two grounds the repository has already written
   down. First, a binding that can move independently of the image would
   select a version whose implementation is not in the running worker — the
   floating-half failure `resolver.py:806-811` and ADR 007 sec. 4 describe for
   an unpinned `definition.version`, reintroduced deliberately. Second, ADR 015
   rejected a new mctl-api table for evaluation records because "the durable
   artefact already exists; a stored record would be a derived duplicate that
   can silently disagree with its source" — the same argument applies to a
   strategy version whose implementation lives in this repo. Named as the
   follow-up once the in-repo catalog is proven, at which point the version
   document is what mctl-api ingests.
2. **Keep the env var and give it a richer grammar
   (`ISSUE_INVESTIGATOR_CONTEXT_STRATEGY=trust-freshness-ranked@1.1.0`).**
   Cheapest option, and it is what this proposal replaces. Rejected: it still
   has no revision history, no prior-revision rollback target, no promoter, no
   reason, no evidence link — and the version string still names no bytes, so
   gap 1 survives untouched. It also cannot express "observe a candidate
   against the active one", because there is only one slot.
3. **Fold the strategy into the existing `ExecutionProfile` and promote it
   through the agent `ReleaseBinding` that already exists.** Attractive
   because the machinery is built. Rejected: ADR 007 fixes what a profile
   version bump means ("model, skills, tools, permissions/policy, budget,
   timeout, runtime, approval, or evidence", `007-...:241-243`); adding
   context assembly would make one revision mean two unrelated things and
   force a full agent re-promotion for a ranking tweak. ADR 009 sec. 1 also
   assigns `strategy` to the assembler, not to the plan, and its Alternative 1
   already rejected merging runtime context into `ExecutionPlan`.
4. **Derive the version entirely from the implementation hash — no human
   semver.** Rejected: an identity no one can read in a changelog or an
   incident review, and it makes every comment or whitespace edit an automatic
   "promotion" with no human decision anywhere. The chosen design keeps the
   semver as the human handle and the hash as the pin, which is precisely
   `resolver._model_policy_version()`'s existing compromise.

## Platform impact

- **Migrations:** none. No mctl-api table, no route, no GitOps schema change,
  no agent manifest change. New files under `config/context-strategies/`, one
  new orchestrator module, one new tool, one new ADR.
- **Backward compatibility:** default `off` means the investigator's observable
  behaviour, its prompt bytes and its snapshot ids are unchanged until an
  operator sets one variable. `ContextStrategy`'s two new fields are optional
  and omitted-when-unset, so every persisted snapshot and the committed golden
  fixture keep their identity; a document written by an older producer still
  parses, and a document carrying the new keys parses on a reader that knows
  them. `from_dict`'s unknown-key rejection means an *older* reader will refuse
  a *newer* document — acceptable and consistent with amendment 1, and the
  reason the ladder is rolled out reader-first.
- **Resource impact:** at `observe`, one extra `run_pipeline` pass plus one
  extra `seal()` per investigation. Both are pure CPU over an in-memory list
  already bounded by `AssemblyConfig.max_candidates` (100) and `max_bytes`
  (120k); no collector re-runs, no `gh` call, no clone, no store round trip.
  The measurable effect is on `assembly_latency_ms`, which the compare line
  reports for both passes so the cost is visible rather than assumed. At
  `enforce`/`only` the cost is one YAML read and two sha256 computations per
  run, cached per process.
- **Risks and mitigations:**
  - *Implementation-hash churn.* Whole-file hashing means a comment edit in
    `context_assembly.py` fails the CI guard. Mitigated by the guard printing
    the exact republish command, and by the honest framing: over-reporting
    change is the fail-safe direction. Per-function hashing is a follow-up.
  - *A binding names a version the running image does not implement.*
    Mitigated by resolving the `implementationHash` against the files in the
    image and failing closed, plus `tools/context_release.py resolve` as a CI
    preflight on the same commit.
  - *Promotion without valid evidence.* Production accepts only #526
    `context-eval` evidence whose strategy/version/content/implementation
    identity matches exactly, whose newest observation is <= 7 days old, and
    which covers >= 3 consecutive observe-mode investigations with no
    `hash-mismatch`. Missing/stale/mismatched evidence fails closed; promotion
    is still a reviewed commit rather than an automatic metric action.
  - *The observe pass changes what the model reads.* This is the failure that
    would invalidate the whole stage. Mitigated structurally — the second
    outcome is bound to a local name and never reaches `seal()`'s return,
    `AssemblyResult.rendered` or `_persist_to_work_item_store` — and by a test
    asserting the authoritative snapshot is byte-identical with and without
    the observe pass enabled.
  - *A second snapshot is persisted for one execution.* Mitigated by never
    calling `_persist_to_work_item_store` for the candidate pass; the store's
    insert-only divergence refusal (`context_assembly.py:1277-1294`) is the
    backstop, not the plan.
  - *Promotion cannot be reversed quickly because it is a release.* Mitigated
    by the two-tier rollback: `CONTEXT_RELEASE_ROLLOUT_MODE=off` is an instant,
    no-deploy break-glass, and the audited exact-revision rollback follows.
  - *A binding or score drifts onto an authorization path.* Mitigated by
    restating ADR 009 sec. 5 in the new ADR and extending the existing
    field-name and import-direction tests in `tests/test_context_snapshot.py`
    to cover `orchestrator/context_release.py`.
- **Security:** no new secret, no new network call, no new credential. The
  catalog is non-sensitive configuration; the log lines carry ids, versions,
  hashes and counts only. Nothing in this proposal grants, widens or is read
  by any permission decision.
