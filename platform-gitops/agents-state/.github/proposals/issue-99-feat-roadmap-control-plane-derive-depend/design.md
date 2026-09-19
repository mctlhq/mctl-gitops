# Design: issue-99-feat-roadmap-control-plane-derive-depend

## Current state

The roadmap control plane in this repository is a chain of pure derivations over two
inputs -- validated manifest bytes and one observed `GitHubGraphSnapshot`. There is no
`ready.py` and no readiness contract today.

Authored desired state

- `roadmap/schemas/epic-definition.schema.json` defines `EpicDefinition` v1alpha1.
  `$defs.workItem` requires `id`, `phase`, `required`, and optionally carries `issue`
  (`$defs.issueRef`), `parent`, `dependsOn` (array of local ids, `uniqueItems`) and
  `externalDependsOn` (array of `issueRef`). `additionalProperties: false` rejects
  authored `blocks`, `children` and `status`.
- `roadmap/scripts/validate.py` adds the semantic layer: unique ids, valid local
  references, acyclic parent and dependency graphs (`_cycle`), unique/globally unique
  bindings (`_document_bindings`, `corpus_errors`), `externalDependsOn` that truly
  points outside the epic, and `title`+`owner` on unbound items. `issue_key()` and
  `canonical_repository()` are the canonical `(repository, number)` normalizers.
- The corpus is `roadmap/epics/*.yaml`. Three manifests matter for the acceptance
  criteria: `lifecycle-ownership.yaml` (six required items; `guarded-recovery` depends
  on `ownership-inspection` `mctlhq/mctl-api#293`, `executor-fencing`
  `mctlhq/mctl-agents#352`, `ownership-reconciler` `mctlhq/mctl-agents#353`),
  `human-input.yaml` (required + optional items, an `externalDependsOn` on
  `mctlhq/mctl-telegram#443`, and an unbound `devloop-e2e`), and
  `unified-identity.yaml` (every item unbound, `principal-model` with no `dependsOn`).
- `roadmap/epics/roadmap-control-plane.yaml` already authors this issue as work item
  `ready-work-items` (`mctlhq/.github#99`, phase `waves`, required, `dependsOn:
  [reconciler, roadmap-health]`) with `epic-status-api` (`mctlhq/mctl-api#333`) and
  `governed-wave-start` (`mctlhq/mctl-api#334`) depending on it. Its success criteria
  already say "Dependency-aware readiness is derived from EpicDefinition and observed
  issue state, never from operator memory."

Observed state

- `roadmap/scripts/github_graph.py` holds the read half and no mutation primitive at
  all. `ObservedGraph` (frozen dataclass, line 165) carries `resolution`, `missing`,
  `observed`, `parents`, `children`, `blocked_by` and `states` --
  `states[resolved] = (state, stateReason)` only for issues whose state was actually
  captured, so "no entry" means unknown rather than open. `observed_graph()` normalizes
  a schema-valid snapshot; `snapshot_errors()`, `load_snapshot()`,
  `require_observations()`, `FixtureGraphSource` and `LiveGraphSource` are the source
  boundary.
- `roadmap/scripts/reconcile.py` builds `DesiredGraph` (`desired_graph()`, line 94):
  `bindings` (item id -> `IssueKey`), `unbound`, `hierarchy`, `dependencies`
  (`(item_id, child, blocker)` triples, already flattening `dependsOn` *and*
  `externalDependsOn`), `external_refs`, plus `authored_keys()` / `owned_keys()`.
  `validate_corpus()` / `load_corpus()` are the preflight, `_manifest_label()` the
  portable path renderer, `_build_source()` the `--snapshot` vs `--live` switch.

Derived projections

- `roadmap/scripts/completion.py` is the closest prior art and the layer #99 must reuse
  rather than re-derive. `item_status(key, observed, unobserved, ambiguous)` returns the
  `(status, reason)` pairs in the README's completion table; `_DELIVERED = {None,
  "completed"}` and `_NOT_DELIVERED = {"not_planned", "duplicate"}` are the accepted
  completion reasons; `_colliding_bindings()` reproduces the reconciler's
  `BindingAmbiguous` rule; `compute()` sorts `workItems` by id and emits `blocking` as
  "required items not complete"; `consistency_errors()` is the semantic check a consumer
  runs on a block it did not compute.
- `roadmap/scripts/health.py` wires it together: `assess()` obtains the snapshot,
  computes `unobserved = keys - observed`, emits `ObservationMissing` diagnostics,
  diffs, then calls `completion.compute(loaded.document, graph, unobserved)`.
  `render()` collapses one document or emits a `RoadmapHealthList`. Exit codes
  `0/1/2/3/4` map to `healthy/drift/usage/invalid/observation_failed`.
- `roadmap/schemas/roadmap-health.schema.json` `$defs.completion` is the shape to
  mirror: `mode`, `status`, `required` counts, `blocking`, `items` with a **closed**
  `reason` enum (`closed`, `open`, `closed_not_planned`, `closed_duplicate`, `unbound`,
  `issue_not_found`, `unobserved`, `state_not_observed`,
  `closed_reason_unrecognized`, `binding_ambiguous`).
- Tests: `roadmap/tests/test_completion.py` derives its graphs from the manifest it is
  handed (`_required_bound`, `_close_required_except`, a local `_set_state`) precisely so
  new work items do not break old assertions. `roadmap/tests/mutations.py` holds pure
  deep-copy mutators (`ref`, `drop_dependency`, `mark_missing`, `redirect`,
  `add_second_parent`, ...). `.github/workflows/roadmap-validate.yml` runs validate,
  reconcile, health, plan/apply offline against fixtures with `permissions: {}` and never
  runs `--live`.

Gap: nothing joins `DesiredGraph.dependencies` with `completion.item_status` per item.
`completion.blocking` is "required and not complete" and is deliberately
dependency-blind.

## Proposed solution

Add one new pure module, one new schema and one new test module. Nothing existing
changes semantically.

### 1. `roadmap/schemas/roadmap-ready-set.schema.json`

A `oneOf` over `$defs.roadmapReadySet` and `$defs.roadmapReadySetList`, mirroring
`roadmap-health.schema.json`'s structure and reusing its `issueRef` shape.
`additionalProperties: false` everywhere.

```jsonc
{
  "apiVersion": "roadmap.mctl.ai/v1alpha1",
  "kind": "RoadmapReadySet",
  "epic": {"name": "lifecycle-ownership",
           "manifest": {"path": "roadmap/epics/lifecycle-ownership.yaml", "sha256": "<64 hex>"},
           "issue": {"repository": "mctlhq/.github", "number": 57}},
  "source": {"mode": "live-capture", "capturedAt": "...", "apiBase": "..."},
  "ready": ["guarded-recovery"],                       // sorted ids, the queue itself
  "summary": {
    "items":    {"ready": 1, "blocked": 0, "complete": 5, "unknown": 0},
    "required": {"ready": 1, "blocked": 0, "complete": 5, "unknown": 0}
  },
  "items": [
    {"id": "guarded-recovery", "phase": "operations", "required": true,
     "state": "ready",
     "completion": {"status": "incomplete", "reason": "open"},
     "issue": {"repository": "mctlhq/mctl-api", "number": 294},
     "dependsOn": ["ownership-inspection", "executor-fencing", "ownership-reconciler"],
     "blockers": []}
  ]
}
```

- `state` enum: `ready | blocked | complete | unknown`. The item's own completion axis is
  kept in a nested `completion: {status, reason}` whose `status` and `reason` enums are
  **copied verbatim** from `roadmap-health.schema.json` `$defs.completion`, so the two
  documents cannot drift apart in vocabulary and the readiness state is always traceable
  to the completion evidence that produced it.
- `dependsOn` and `externalDependsOn` echo the manifest in **authored order** (the only
  place authored order is preserved). `externalDependsOn` items are `issueRef`s.
- `blockers` entries are discriminated: `{"kind": "workItem", "id": ..., "status": ...,
  "reason": ...}` or `{"kind": "external", "issue": {...}, "status": ..., "reason": ...}`.
  No synthetic id is invented for an external issue. Sorted by `(kind, id or
  repository, number)`.
- `source` is **required**: a ready set without provenance is not evidence.
- `epic.issue` is present when the manifest binds a root, exactly as `health._epic()`
  does.

### 2. `roadmap/scripts/ready.py`

Pure core plus a CLI, structured like `health.py`.

```python
READY, BLOCKED, COMPLETE, UNKNOWN = "ready", "blocked", "complete", "unknown"

# Reasons that are observed evidence of undelivered work. Only these make a
# dependent BLOCKED; every other non-complete reason is indeterminate.
BLOCKING_REASONS = frozenset({"open", "closed_not_planned", "closed_duplicate"})

def compute(document, observed, unobserved=frozenset()) -> dict   # pure
def consistency_errors(block) -> list[str]                        # pure
def assess(path, loaded, source_adapter, *, corpus=None) -> dict   # reads via adapter
def main(argv=None) -> int                                         # CLI
```

`compute()` algorithm, in order:

1. `ambiguous = completion.colliding_bindings(spec["workItems"], observed, unobserved)`
   -- the existing `_colliding_bindings` promoted to a public name with
   `_colliding_bindings = colliding_bindings` kept as an alias so no existing caller or
   test changes.
2. For every work item, `status, reason = completion.item_status(key, observed,
   unobserved, ambiguous)`. This is the single source of the completion axis; #99 adds no
   second interpretation of GitHub state.
3. Classify each item id into one of three predecessor contributions:
   `SATISFIED` (status `complete`), `BLOCKING` (status `incomplete` and reason in
   `BLOCKING_REASONS`), `INDETERMINATE` (everything else: `unbound`, `issue_not_found`,
   `unobserved`, `state_not_observed`, `binding_ambiguous`,
   `closed_reason_unrecognized`).
4. For external references, evaluate `completion.item_status(external_key, observed,
   unobserved, ambiguous)` on the `IssueKey` directly -- legal because
   `DesiredGraph.authored_keys()` already includes `external_refs`, so `reconcile.py`,
   `health.py` and this module all observe the same key set and an unobserved external
   issue lands in `unobserved` and classifies `INDETERMINATE`.
5. Assign the item's `state`:
   - own contribution `SATISFIED` -> `complete`, `blockers: []`;
   - own contribution `INDETERMINATE` -> `unknown`, `blockers: []` (the reason is on
     `completion.reason`; this is the unbound / unobserved / ambiguous / not-found item
     itself, so no predecessor is blamed);
   - own contribution `BLOCKING` -> look at predecessors: any `BLOCKING` predecessor ->
     `blocked`; else any `INDETERMINATE` predecessor -> `unknown`; else -> `ready`.
     `blockers` lists exactly the non-`SATISFIED` predecessors.
   Only one hop is needed: `validate.semantic_errors` already rejects dependency cycles,
   and a `complete` predecessor's own history is not evidence about this item.
6. Emit `items` sorted by id (same key `completion.compute` uses), `ready` as the sorted
   ids of `state == "ready"`, and `summary` counts over all items and over
   `required: true` items.

Purity is the same as `completion.py`: no I/O, no clock, no randomness, no absolute
path. Nothing about DevLoop, Temporal, Argo or ownership is an argument, so #95 runtime
state cannot leak in by construction.

`assess()` reuses `health.assess()`'s observation contract verbatim -- `FixtureGraphSource`
with `require_complete=False`, `github_graph.snapshot_errors()`, `unobserved = keys -
observed(requested)`, `observed_graph()` -- then calls `compute()` and validates the
document against `roadmap-ready-set.schema.json` plus `consistency_errors()` before
returning it. A source-level failure (`ObservationError`, `SnapshotIncomplete`,
`SnapshotInvalid`, `OSError`) prints to stderr and exits 4 without emitting a document,
because the schema requires `source`.

`main()` mirrors `reconcile.py`/`plan.py` flags: positional manifests, `--corpus`
(default `roadmap/epics`, always validated in full before any network call),
`--schema`, `--ready-schema`, `--snapshot`, `--live`, `--capture` (implies `--live`),
`--api-base`, `--output`. Exit codes: `0` a ready set was produced, `2` usage/IO,
`3` desired state invalid (nothing observed), `4` some state could not be observed.
Readiness states never change the exit code, exactly as completion does not change
`health.py`'s.

`render()` collapses a single document or emits `RoadmapReadySetList` ordered by manifest
path, copied from `health.render()`.

### 3. Reuse edits (small, behaviour-preserving)

- `completion.py`: rename `_colliding_bindings` -> `colliding_bindings`, keep the old
  name as an alias. No logic change; `test_completion.py` keeps passing untouched.
- `roadmap/tests/mutations.py`: add two pure helpers --
  `set_state(snapshot, issue, state, reason)` (the deep-copy version of
  `test_completion._set_state`, so `test_ready.py` does not copy it) and
  `synthetic_snapshot(document, states)`, which builds a converged
  `GitHubGraphSnapshot` for any manifest from `reconcile.desired_graph()` and always
  stamps `source.mode: synthetic-fixture`. That is how the `lifecycle-ownership` and
  `unified-identity` acceptance criteria get graphs without hand-editing a capture, and
  the mode stamp makes it impossible for a test graph to claim to be live evidence.
- `.github/workflows/roadmap-validate.yml`: add offline `ready.py` steps beside the
  existing health steps (human-input converged fixture, and the two immutable live
  captures) plus an inline assertion that the emitted `kind` is `RoadmapReadySet` and
  that `ready` equals the ids of the `ready` items. `--live` still never runs in CI and
  `permissions: {}` is unchanged.
- `roadmap/README.md`: a `## Readiness` section between `## Completion` and
  `## Dogfood: epic #66` documenting the state table, the precedence rule, the
  `blocked` vs `unknown` split and the CLI, and a `ready.py` line in the `## Layout`
  tree.

### 4. Why this shape

- **Separate document, separate script.** Readiness has a different consumer
  (`mctl-api#333`/`#334`) and a different failure model from health. A new file cannot
  change `RoadmapHealth` states, precedence, diagnostics or exit codes, which is an
  explicit acceptance criterion.
- **One interpretation of GitHub state.** Readiness delegates every "is this delivered"
  decision to `completion.item_status`. Adding a second closed-reason table would be the
  exact drift the manifest model exists to prevent.
- **Authored edges only.** `dependsOn` / `externalDependsOn` come from the manifest;
  `ObservedGraph.blocked_by` is deliberately unused here. Observed edge drift is
  `reconcile.py`'s `DependencyMissing` / `DependencyUnexpected` job, and a ready set that
  fell back to observed edges would silently use a graph nobody reviewed.
- **Unbound is never ready.** The single strongest safety property for #334: a wave
  launcher can trust `state: ready` to imply a bound, observed, incomplete issue.

## Alternatives

1. **Extend `RoadmapHealth` with a `readiness` block** (like `completion`). Rejected:
   it edits `roadmap-health.schema.json` and every consumer of that contract, couples the
   readiness state to health precedence and exit codes, and contradicts "RoadmapHealth
   semantics and precedence remain unchanged". It also forces readiness to be recomputed
   on every health call even when a caller only wants drift.
2. **Compute readiness in `mctl-api` (#333) from the health document.** Rejected: the
   health document does not carry `dependsOn`, so mctl-api would have to parse
   `roadmap/epics/*.yaml` itself -- a second implementation of the DAG in another
   language, with no shared fixtures and no way to keep the closed reason vocabulary in
   step. The derivation belongs next to `completion.py`; #333 consumes the published
   document.
3. **Derive readiness from the observed `blocked_by` graph instead of the manifest.**
   Rejected: it inverts the source-of-truth rule in `roadmap/README.md`
   ("`dependsOn` is authored; `blocks` is derived"), and the first live run against #66
   proved exactly why -- three authored dependencies existed only as issue prose and were
   absent from the live graph. A readiness queue built on the observed graph would have
   called blocked work ready.
4. **Full transitive closure, marking an item ready only when its entire ancestor set is
   complete.** Rejected as redundant: a `complete` predecessor's own predecessors say
   nothing about this item, the authored graph is already acyclic, and closure would make
   one `unknown` leaf paint every descendant `unknown` -- destroying the queue's
   usefulness without adding a fact.

## Platform impact

- **Migrations.** None. No schema is modified, no persisted artifact is rewritten, no
  GitOps values change. The additions are two new files under `roadmap/`, one new test
  module, two new test helpers, a public alias in `completion.py`, README text and CI
  steps.
- **Backward compatibility.** `RoadmapDiff`, `RoadmapHealth`, `RoadmapApplyPlan` and
  `RoadmapApplyResult` documents and exit codes are untouched; `test_reconcile.py`,
  `test_health.py`, `test_completion.py`, `test_plan.py` and `test_apply.py` must pass
  unmodified, which is the regression proof. `RoadmapReadySet` is v1alpha1 and additive:
  a consumer that does not know it is unaffected.
- **Write safety.** `ready.py` imports `completion`, `github_graph`, `reconcile` and
  `validate` and never `github_apply`. It is a read-only projection; the four-endpoint
  write allow-list and its `MutationRefused` guard are not touched.
- **Resource impact.** Offline evaluation is a few milliseconds over an already-loaded
  snapshot. A `--live` run reads exactly `DesiredGraph.authored_keys()` -- the same GET
  set `health.py` already issues, no new endpoint and no GraphQL. CI adds ~4 offline
  invocations.
- **Risks and mitigations.**
  - *Readiness and completion drift apart.* Mitigated by delegating to
    `completion.item_status` and copying the `status`/`reason` enums into the new schema,
    plus a test asserting the ready set's per-item `completion` block equals the
    corresponding `completion.compute()` entry for the same inputs.
  - *An operator reads `ready` as "safe to launch" for an unbound item.* Mitigated by the
    invariant that `unbound` is `unknown`, a dedicated `unified-identity` /
    `principal-model` test, and a `consistency_errors()` rule that rejects any `ready`
    item whose own reason is not in `BLOCKING_REASONS`.
  - *Optional items quietly excluded from a wave that actually depends on them.*
    Mitigated by scoring optional items exactly like required ones and by the
    `human-input` `portal-card` / `docs` tests; the `required` flag is exposed per item so
    filtering is the caller's explicit choice.
  - *Partially observed snapshot read as a shorter queue.* Mitigated by emitting the
    affected items as `unknown` and exiting 4, never omitting them, and by a test that a
    snapshot missing one predecessor turns its dependent `unknown` rather than `ready`.
  - *Non-determinism creeping in.* Mitigated by a byte-identity test over shuffled
    `spec.workItems` order and shuffled snapshot `issues` order, and by adding no clock
    or random value (only the snapshot's own `capturedAt` is copied as provenance).
  - *A synthetic test graph mistaken for evidence.* Mitigated by
    `mutations.synthetic_snapshot()` hard-coding `source.mode: synthetic-fixture`, which
    `github-graph-snapshot.schema.json` already keeps distinct from `live-capture`.
