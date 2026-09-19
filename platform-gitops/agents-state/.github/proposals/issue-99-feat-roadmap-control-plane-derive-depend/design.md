# Design: issue-99-feat-roadmap-control-plane-derive-depend

## Current state

Everything relevant lives under `roadmap/` in `mctlhq/.github`. The pipeline is documented
in `roadmap/README.md` and implemented as small pure modules under `roadmap/scripts/`:

- `validate.py` — schema (`roadmap/schemas/epic-definition.schema.json`), per-manifest
  semantic checks (`semantic_errors()`: unique ids, valid local references, acyclic
  `parent` and `dependsOn` graphs, `externalDependsOn` truly external) and corpus checks
  (`corpus_errors()`: unique epic names, globally unique bindings). `issue_key()` is the
  shared `(repository, number)` normaliser; `RESERVED_WORK_ITEM_IDS = {"epic"}`.
- `github_graph.py` — read-only observation. `ObservedGraph` (line 165) is the normalized
  view: `resolution` (requested → resolved identity), `missing`, `observed`, `parents`,
  `children`, `blocked_by` and `states` (resolved key → `(state, stateReason)`; an issue
  with no entry had no state captured). `observed_graph()` builds it from a schema-valid
  `GitHubGraphSnapshot`; `FixtureGraphSource` replays one with
  `require_complete=False` for the health path; `LiveGraphSource` is GET-only and raises
  `WriteAttempted` before transmission on anything else.
- `reconcile.py` — `DesiredGraph` (line 60) with `bindings`, `unbound`, `hierarchy`,
  `dependencies`, `external_refs`, plus `owned_keys()` / `authored_keys()`.
  `desired_graph()` (line 94) already walks `dependsOn` and `externalDependsOn` and drops
  edges whose endpoints are unbound, because a relation needs two GitHub objects.
  `validate_corpus()`, `LoadedManifest` (document + digest of the exact validated bytes),
  `_manifest_label()` and `_build_source()` are the reusable CLI plumbing.
- `completion.py` — the completion contract. `item_status(key, observed, unobserved,
  ambiguous)` returns `(status, reason)` over the closed vocabulary documented in
  `roadmap/README.md` ("Completion"): `complete/closed`, `incomplete/open`,
  `incomplete/closed_not_planned`, `incomplete/closed_duplicate`, `incomplete/unbound`,
  `incomplete/issue_not_found`, `unknown/unobserved`, `unknown/state_not_observed`,
  `unknown/binding_ambiguous`, `unknown/closed_reason_unrecognized`.
  `_colliding_bindings()` computes the `BindingAmbiguous` key set; `consistency_errors()`
  is the semantic check a consumer runs on a block it did not compute.
- `health.py` — `assess()` observes one validated manifest, computes `unobserved` as
  `authored_keys() - snapshot.requested`, emits `ObservationMissing` diagnostics for those
  endpoints and hands the same `unobserved` set to `completion.compute()`. `evaluate()` is
  pure; `render()` collapses one document or emits a `RoadmapHealthList` ordered by
  manifest path; exit codes are `0/1/2/3/4`.

What does not exist today: any consumer of `DesiredGraph.dependencies` for readiness.
`completion.compute()` sorts work items by `id` and classifies each in isolation; its
`blocking` list is "required items not complete", with no edge traversal at all
(`roadmap/scripts/completion.py:197`). `roadmap/epics/roadmap-control-plane.yaml` already
authors this work as the `ready-work-items` item in the `waves` phase, bound to
`mctlhq/.github#99` and depending on `reconciler` (#67) and `roadmap-health` (#83), with
`epic-status-api` (mctl-api#333) and `governed-wave-start` (mctl-api#334) depending on it.
`roadmap/fixtures/roadmap-control-plane/live-capture.json` observes #67, #68 and #83
closed as `completed` and #85, #99, #333, #334 open — so #99 is genuinely the next ready
item of its own epic, which makes this feature its own best dogfood.

Fixtures available today: `human-input/converged-fixture.json` (synthetic, all eight
issues open), `roadmap-control-plane/live-capture.json` and
`claude-remote-inbound-channels/live-capture.json`. There is none for
`lifecycle-ownership` or `unified-identity`. CI (`.github/workflows/roadmap-validate.yml`)
runs validate, reconcile, health, plan, apply and the unittest suite entirely offline with
`permissions: {}`.

## Proposed solution

Add a fourth derived projection beside diff, health and completion, in the same shape as
the existing ones: a pure module, a published schema, a thin CLI, a semantic
consistency checker, and offline fixtures.

### New files

```text
roadmap/schemas/roadmap-ready-set.schema.json   RoadmapReadySet | RoadmapReadySetList
roadmap/scripts/ready.py                        pure compute() + CLI
roadmap/tests/test_ready.py                     semantics, determinism, mutation cases
roadmap/fixtures/lifecycle-ownership/converged-fixture.json   synthetic, all open
roadmap/fixtures/unified-identity/root-only-fixture.json      synthetic, root only
```

### The projection

`ready.compute(document, observed, unobserved=frozenset()) -> dict` mirrors
`completion.compute()`'s signature exactly, so `health.assess()`'s existing call site is
the template: it already has a validated `document`, an `ObservedGraph` and the
`unobserved` key set.

Step 1 — reuse completion, do not fork it. Ambiguous bindings come from the existing
`completion._colliding_bindings()`, promoted to a public `completion.colliding_bindings()`
(the private name kept as an alias so nothing else moves). Each work item's own status is
`completion.item_status(key, observed, unobserved, ambiguous)`. The readiness module
therefore contains no GitHub state vocabulary of its own: `_DELIVERED`/`_NOT_DELIVERED`
stay in one file, and a future change to the completion contract cannot leave the two
projections disagreeing about whether an issue is done.

Step 2 — map completion status onto a readiness verdict. The readiness axis splits
`completion.item_status()`'s results into three classes:

| completion status/reason | readiness treatment |
| --- | --- |
| `complete/closed` | `state: complete`, `reason: closed`, no blockers |
| `incomplete/open`, `incomplete/closed_not_planned`, `incomplete/closed_duplicate` | own state proven incomplete → evaluate predecessors |
| `incomplete/unbound` | `state: unknown`, `reason: unbound` |
| `incomplete/issue_not_found` | `state: unknown`, `reason: issue_not_found` |
| any `unknown/*` | `state: unknown`, same reason verbatim |

The two deliberate divergences from the completion axis are `unbound` and
`issue_not_found`: completion calls them `incomplete` because absence of a delivered issue
is evidence the work is not done, while readiness calls them `unknown` because the issue
invariant is explicit — "Unbound work items are never reported `ready`; they are
`unknown/unbound`". Each item echoes its `completion: {status, reason}` block verbatim, so
the divergence is visible in the artifact rather than hidden in code, and a consumer can
cross-check a ready set against a `RoadmapHealth` completion block field by field.

Step 3 — evaluate predecessors for items whose own state is proven incomplete. The
predecessor set of item `i` is the authored `dependsOn` ids plus the authored
`externalDependsOn` refs — nothing else. Hierarchy (`parent`, observed `subIssues`) and
phase order create no edges, per `roadmap/README.md` ("Hierarchy and dependency are
deliberately separate"), and observed `blocked_by` edges are not consulted either: those
are the *observed* graph the reconciler compares against, not a dependency source. Each
predecessor is scored with the same `completion.item_status()` — an internal one on its
own binding (so an unbound predecessor is `unknown`, not silently skipped as
`desired_graph()` does for drift purposes), an external one on its `issueRef` directly.
Then:

```text
any predecessor status == incomplete  -> blocked  (reason dependency_incomplete)
else any predecessor status == unknown -> unknown  (reason dependency_unknown)
else                                   -> ready    (reason dependencies_complete)
```

`blocked` outranks `unknown` because an observed-incomplete predecessor *proves*
non-executability, exactly as `completion.compute()` lets a certain `incomplete` outrank
an `unknown`. An item with no predecessors is vacuously `ready`. Transitivity needs no
closure walk: if A is open then B is `blocked`, and B being open makes C `blocked` in the
same pass — direct-edge evaluation is already transitively correct.

`blockers` lists every predecessor whose status is not `complete`, each as
`{kind: internal, id, status, reason}` or `{kind: external, issue, status, reason}`.
Complete predecessors are omitted; a `ready` or `complete` item therefore always carries
`blockers: []`.

### Document shape

```yaml
apiVersion: roadmap.mctl.ai/v1alpha1
kind: RoadmapReadySet
epic:
  name: lifecycle-ownership
  manifest: {path: roadmap/epics/lifecycle-ownership.yaml, sha256: <64 hex>}
  issue: {repository: mctlhq/.github, number: 57}
source: {mode: live-capture, capturedAt: ..., apiBase: ...}   # copied verbatim
summary: {ready: 1, blocked: 2, complete: 3, unknown: 0}       # all items
required: {total: 6, ready: 1, blocked: 2, complete: 3, unknown: 0}
ready: [guarded-recovery]                                      # sorted ids, any optionality
items:
  - id: guarded-recovery
    required: true
    state: ready
    reason: dependencies_complete
    issue: {repository: mctlhq/mctl-api, number: 294}
    completion: {status: incomplete, reason: open}
    dependsOn: [ownership-inspection, executor-fencing, ownership-reconciler]
    externalDependsOn: []
    blockers: []
```

Ordering: `items` sorted by `id` (as `completion.compute()` does), `blockers` sorted by
`(kind, id or repository, number)`, `ready` sorted. `dependsOn` and `externalDependsOn`
keep authored order — the single contract-explicit exception the issue allows, because
they are an echo of authored input rather than a derived set. Nothing carries a timestamp
of its own; the only time in the document is the snapshot's `capturedAt`, copied as
provenance, exactly as `RoadmapDiff` does.

`ready.consistency_errors(document)` is the semantic layer JSON Schema cannot express,
modelled on `completion.consistency_errors()`: summary and `required` counts must equal
the items; `ready` must be exactly the `ready`-state ids; a `ready`/`complete` item must
have no blockers; a `blocked` item must have at least one `incomplete` blocker; an
`unknown` item must have either an own-unknown `reason` or at least one `unknown` blocker;
an item with `state: ready` must carry an `issue`; every blocker must name an id present
in that item's `dependsOn` or a ref present in its `externalDependsOn`. Schema plus this
function is the "reject internally contradictory ready sets" acceptance criterion.

### CLI

`ready.py` copies `health.py`'s `main()` structure: positional manifests, `--corpus`
(always fully validated first, never narrowed by selection), `--schema`, `--ready-schema`,
`--snapshot` / `--live` (mutually exclusive), `--capture`, `--api-base`, `--output`.
Observation reuses `reconcile._build_source()` and the `FixtureGraphSource(...,
require_complete=False)` path so an unobserved endpoint degrades into per-item `unknown`
instead of aborting. Exit codes reuse health's space: `0` every item classified with no
`unknown`, `1` at least one `unknown`, `2` usage/IO, `3` manifest or corpus invalid, `4`
observation failure or unusable snapshot. The emitted document is validated against its
own schema and against `consistency_errors()` before it is returned, as `apply.py` does
with `RoadmapApplyResult`.

### Why runtime state cannot enter

The only two inputs are validated `EpicDefinition` bytes and a `GitHubGraphSnapshot`.
`roadmap/schemas/github-graph-snapshot.schema.json` is `additionalProperties: false` and
has no field in which a DevLoop or Temporal state could be expressed, so "changing only
runtime state does not change the ready set" is a property of the input vocabulary, not a
promise. The test suite asserts it that way rather than by mutating a field that cannot
exist.

### Documentation and CI

`roadmap/README.md` gains a "Readiness" section after "Completion": the state table, the
precedence rule, the two deliberate divergences from the completion axis, and the CLI.
`.github/workflows/roadmap-validate.yml` gains offline steps that run `ready.py` against
the human-input synthetic fixture and against the epic #66 live capture, asserting
`human-input-core` and `ready-work-items` respectively — the same dogfood pattern the
health steps already use, with no token and no `--live`.

## Alternatives

1. **Extend the `completion` block with `ready`/`blocked` fields inside `RoadmapHealth`.**
   Cheapest to write and needs no new CLI. Dropped: `roadmap-health.schema.json` is
   `additionalProperties: false`, so every field added is a breaking contract change for
   existing consumers, and the issue requires "RoadmapHealth/completion behavior is
   unchanged". It would also fuse two axes the README keeps separate — an epic can be
   healthy and blocked, or drifted with ready work — and force every health consumer to
   pay for DAG evaluation it did not ask for.

2. **Derive readiness from the observed `blocked_by` graph instead of authored
   `dependsOn`.** Tempting because `ObservedGraph.blocked_by` is already normalized and
   would cover dependencies nobody wrote into a manifest. Dropped: it inverts the
   source-of-truth rule the whole directory rests on ("`dependsOn` is authored; `blocks`
   is derived"), and it makes readiness change when somebody clicks a button in the GitHub
   UI. Worse, it is unsound in exactly the case that matters — an unauthored observed edge
   is `DependencyUnexpected` drift, and treating drift as a dependency would let a bad
   edge block a wave with no reviewable record. The observed graph stays what the
   reconciler compares against.

3. **Emit a full transitive closure with wave numbers (`wave: 0,1,2`).** Would directly
   answer "what can I start next, and then what". Dropped: it is ordering/selection, which
   the issue lists as a non-goal ("Selecting priority between independent ready items"),
   and a wave index is unstable under `unknown` — an unbound predecessor makes every
   downstream depth meaningless, so the number would have to be `null` exactly where the
   graph is most interesting. Direct blockers plus the full item list let a client compute
   any closure it wants, deterministically.

4. **Put readiness in mctl-api instead of this repo.** Dropped: the manifest, the schemas
   and the deterministic evaluators live here and are validated by this repo's CI;
   mctl-api#333 is a consumer of a published contract, not the place to re-derive it. A
   second implementation of the DAG rules is the drift this epic exists to remove.

## Platform impact

- **Migrations.** None. No manifest field is added, so `epic-definition.schema.json` is
  untouched and every existing `roadmap/epics/*.yaml` keeps validating unchanged. No
  stored state, no database, no Vault entry, no service deployment.
- **Backward compatibility.** `RoadmapHealth`, `RoadmapDiff`, `RoadmapApplyPlan` and
  `RoadmapApplyResult` documents and exit codes are unchanged. The only edit to an
  existing module is promoting `completion._colliding_bindings()` to a public name with
  the private alias retained; `completion.compute()` and `consistency_errors()` keep
  identical behaviour, and the existing `test_completion.py` suite is the regression proof.
- **New public contract.** `roadmap-ready-set.schema.json` becomes a published
  `v1alpha1` contract that mctl-api#333 and #334 will read. It is `additionalProperties:
  false` throughout with closed `state` and `reason` vocabularies, so no issue title, body
  or comment text can be written into it — the same containment rule
  `roadmap-apply-result.schema.json` holds.
- **Resource impact.** Offline runs are pure CPU over a parsed snapshot. `--live` issues
  exactly the reads `reconcile.py` already issues, through the same GET-only client; no
  new endpoint and no write primitive is introduced. CI grows by two short offline steps.
- **Risks and mitigations.**
  - *Readiness and completion drift apart over time.* Mitigated by construction: both call
    `completion.item_status()`, each item echoes its completion block, and a test asserts
    every item's echoed block equals `completion.compute()`'s entry for the same id.
  - *An operator reads `unknown` as "probably fine" and starts work anyway.* Mitigated by
    the exit code (`1` on any `unknown`) and by every `unknown` naming its evidence; the
    README states plainly that `unknown` is never a weaker `ready`.
  - *A hand-authored fixture is mistaken for evidence.* Both new fixtures use
    `source.mode: synthetic-fixture`; the snapshot schema's `oneOf` forbids a synthetic
    fixture from claiming a `capturedAt`, so promotion to evidence is structurally
    impossible.
  - *Ambiguous or redirected bindings silently credited.* `completion.item_status()`
    already returns `unknown/binding_ambiguous` for collisions, and this module passes the
    same `ambiguous` set through; a test covers the redirected and ambiguous cases using
    the existing `mutations.redirect()` and `mutations.add_second_parent()` mutators.
  - *The lifecycle-ownership fixture rots as that epic grows.* The test derives its
    expectations from the manifest it loads (the pattern `test_completion.py` adopted in
    `_close_required_except`), not from a hard-coded item list.
