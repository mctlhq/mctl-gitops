# Design: issue-67-feat-roadmap-control-plane-reconcile-epi

## Current state

`mctlhq/.github` has no application code beyond the roadmap control plane and
the shared review workflows. The full file list relevant to this issue:

```text
roadmap/README.md
roadmap/requirements.txt                      # jsonschema==4.25.1, PyYAML==6.0.2
roadmap/schemas/epic-definition.schema.json   # v1alpha1 authored contract
roadmap/epics/human-input.yaml                # first pilot manifest
roadmap/scripts/validate.py                   # offline schema + semantic validator
roadmap/tests/test_validate.py                # unittest suite
.github/workflows/roadmap-validate.yml        # CI, permissions: {}
```

What exists today:

- `roadmap/schemas/epic-definition.schema.json` defines the authored contract
  with `additionalProperties: false` everywhere, an `issueRef` `$def`
  (`repository` matching `^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$`, integer
  `number >= 1`), and a `workItem` that may carry `issue`, `parent`,
  `dependsOn` (local ids), and `externalDependsOn` (issue refs). Reverse
  relations (`blocks`, `children`, `status`) are rejected structurally — see
  `test_reverse_relation_is_not_authored` in `roadmap/tests/test_validate.py`.
- `roadmap/scripts/validate.py` layers schema validation (`schema_errors`),
  per-manifest semantics (`semantic_errors`: unique ids, valid references,
  acyclic `parent` and `dependsOn` graphs via the iterative `_cycle` helper,
  unique local bindings, `externalDependsOn` may not point at a locally bound
  issue, unbound items require `title` and `owner`), and corpus invariants
  (`corpus_errors`: unique `metadata.name`, globally unique issue bindings).
  Useful reusable primitives already present: `_issue_key`, `_document_bindings`,
  `_manifest_paths`, `validate_document`, and the exit-code convention in
  `main` (0 pass, 1 validation failure, 2 usage/IO error).
- `roadmap/epics/human-input.yaml` binds epic root `mctlhq/.github#42` and five
  bound work items across four repositories (`mctl-agents#333`, `mctl-api#261`,
  `mctl-telegram#571`, `mctl-portal#124`, `mctl-docs#106`), one external
  dependency (`mctl-telegram#443`), and one deliberately unbound item
  (`devloop-e2e`). No work item uses `parent`, so every bound item is a direct
  child of the epic root today.
- `.github/workflows/roadmap-validate.yml` runs on `roadmap/**` changes with
  top-level `permissions: {}`, installs `roadmap/requirements.txt`, runs the
  validator over `roadmap/epics`, and runs `unittest discover -s roadmap/tests`.
  The checkout action is SHA-pinned, matching the hardening conventions
  documented in `.github/workflows/claude-review.yml`.
- `roadmap/README.md` already specifies the target boundary (manifest →
  validation → `RoadmapReconcileWorkflow` → live GitHub graph read →
  deterministic `RoadmapDiff` → `mctl-api` observed/read model), the
  source-of-truth rules (authored `parent`/`dependsOn`, derived
  `children`/`blocks`), the separation of hierarchy from dependency, the "no LLM
  in the apply path" rule, the requirement that the manifest hash is carried
  into audit/evidence, and the both-directions mutation-test bar.

What is missing is exactly the middle of that pipeline: there is no code that
reads GitHub, no observed-state model, no `RoadmapDiff` contract, and no
fixtures.

## Proposed solution

Add a read-only reconciler alongside the existing validator, in the same
directory, with the same stdlib-first, offline-by-default posture.

New files:

```text
roadmap/schemas/github-graph-snapshot.schema.json  # observed-graph capture contract
roadmap/schemas/roadmap-diff.schema.json           # RoadmapDiff output contract
roadmap/scripts/github_graph.py                    # graph sources (fixture + live, GET-only)
roadmap/scripts/reconcile.py                       # desired/observed normalization + diff + CLI
roadmap/fixtures/human-input/converged.json        # captured converged snapshot of the pilot
roadmap/tests/test_reconcile.py                    # mutation tests, both directions
roadmap/tests/mutations.py                         # deterministic snapshot mutators
```

Modified: `.github/workflows/roadmap-validate.yml` (one extra step running the
reconciler over the committed snapshot in fixture mode; `permissions: {}` and
the absence of any token stay unchanged). `roadmap/README.md` gains a
"Reconciliation" section. `roadmap/requirements.txt` is unchanged — the
reconciler uses only `json`, `hashlib`, `urllib.request`, plus the already
pinned `jsonschema` and `PyYAML`.

### Layer 1 — desired graph (`reconcile.py`)

`desired_graph(document) -> DesiredGraph` runs only on a document that already
returned `[]` from `validate.validate_document`, so it may assume ids are
unique, references resolve, and the graphs are acyclic. It produces:

- `bindings: dict[str, IssueKey]` — work-item id to canonical issue key, reusing
  `validate._issue_key` for extraction and normalizing `repository` with
  `str.lower()` for comparison while retaining the authored spelling for output.
- `hierarchy: set[tuple[IssueKey, IssueKey]]` as `(parent, child)` — a bound item
  with no `parent` yields `(spec.github.issue, item.issue)`; a bound item with
  `parent` yields `(bindings[item.parent], item.issue)`.
- `dependencies: set[tuple[IssueKey, IssueKey]]` as `(blocked, blocker)` — from
  `dependsOn` resolved through `bindings` and from `externalDependsOn` verbatim.
- `suppressed: list[Suppression]` — every edge that could not be derived because
  one endpoint is an unbound work item. `spec.phases` is read only to carry the
  phase label into entry payloads; it never produces an edge, which the
  `test_phase_order_is_not_a_dependency` test locks in.

### Layer 2 — observed graph (`github_graph.py`)

One provider-neutral `GraphSnapshot` shape, validated against
`github-graph-snapshot.schema.json`:

```json
{
  "apiVersion": "roadmap.mctl.ai/v1alpha1",
  "kind": "GitHubGraphSnapshot",
  "capturedAt": "2026-09-01T00:00:00Z",
  "issues": [
    {"repository": "mctlhq/.github", "number": 42, "found": true,
     "state": "open", "title": "...",
     "parent": null,
     "subIssues": [{"repository": "mctlhq/mctl-agents", "number": 333}],
     "blockedBy": [], "blocking": []}
  ]
}
```

Two sources implement the same `fetch(refs) -> GraphSnapshot` protocol:

- `FixtureGraphSource(path)` loads a committed snapshot. Used by every test and
  by CI. No network, no token.
- `LiveGraphSource(token, api_base)` resolves each referenced issue with a
  batched GraphQL query for existence/state/`parent`/`subIssues`, then a REST
  `GET /repos/{owner}/{repo}/issues/{number}/dependencies/blocked_by` per issue
  for dependency edges. Every request goes through one `_get(url, ...)` helper
  that hardcodes `method="GET"` and raises `WriteAttempted` if any caller passes
  another method or a body — a structural, testable guarantee rather than a
  convention. It also supports `--capture <path>`, writing a snapshot for
  offline replay, which is how the converged fixture is produced and refreshed.

Normalization happens once, in `observed_graph(snapshot)`: lowercase repository
keys, sort every relation list, drop self-edges, and collapse duplicate
relations. Anything the snapshot reports as `found: false` becomes a binding
entry and marks that issue key as unresolvable.

### Layer 3 — diff (`reconcile.py`)

`diff(desired, observed) -> RoadmapDiff` returns three separate collections, per
the issue's requirement that hierarchy and dependency drift stay distinct:

| collection | type | emitted when |
| --- | --- | --- |
| `binding` | `BindingIssueNotFound` | bound issue absent from the observed graph |
| `binding` | `BindingRedirected` | issue resolves to a different repo/number |
| `binding` | `BindingAmbiguous` | issue observed with more than one parent, or a binding with multiple candidates |
| `binding` | `BindingUnbound` (info) | work item has no `issue`; carries `title`/`owner` |
| `hierarchy` | `HierarchyMissingParent` | desired `(parent, child)` not observed |
| `hierarchy` | `HierarchyWrongParent` | child observed under a different parent |
| `hierarchy` | `HierarchyUnexpectedChild` (info) | observed child of a bound parent that no work item binds |
| `dependency` | `DependencyMissing` | desired `(blocked, blocker)` not observed |
| `dependency` | `DependencyUnexpected` | observed `blockedBy` on a bound issue with no desired counterpart |

Binding entries are computed first and any desired edge touching an unresolvable
or suppressed endpoint is dropped from the hierarchy/dependency comparison, so a
single missing issue produces one binding entry instead of a cascade of fake
hierarchy and dependency drift.

Determinism is a hard requirement, so: sets are converted to sorted lists by
`(type, subject, object)`; no `datetime.now()` anywhere (`capturedAt` is copied
from the snapshot, never generated); `json.dumps(..., sort_keys=True,
indent=2)`; and the document carries `manifest.sha256` computed over the exact
manifest bytes, satisfying the README rule that the manifest revision/hash is
carried into evidence. `test_output_is_byte_stable` asserts two runs produce
identical bytes.

### Layer 4 — CLI and CI

`python roadmap/scripts/reconcile.py roadmap/epics --snapshot
roadmap/fixtures/human-input/converged.json [--output diff.json]` mirrors
`validate.py`'s argument handling (reusing `validate._manifest_paths`) and its
exit codes: 0 converged, 1 drift, 2 usage/IO/validation error. `--live` selects
`LiveGraphSource` and is never used by this repository's CI. The workflow gains:

```yaml
      - name: Reconcile pilot epic against captured graph
        run: >-
          python3 roadmap/scripts/reconcile.py roadmap/epics/human-input.yaml
          --snapshot roadmap/fixtures/human-input/converged.json
```

which keeps `permissions: {}` and requires no secret. The `unittest discover`
step picks up `roadmap/tests/test_reconcile.py` automatically.

### Mutation testing

`roadmap/tests/mutations.py` provides pure functions over a loaded snapshot:
`drop_parent_edge(snapshot, child)`, `drop_dependency_edge(snapshot, blocked,
blocker)`, `rebind_issue(snapshot, old, new)`. Tests derive every red case from
the single committed converged snapshot, assert the expected family turns red
while the other families stay empty, then assert the restored copy compares
equal to the original object and reconciles green again. Committing one snapshot
rather than N mutated files makes it impossible for the green and red fixtures to
drift apart.

## Alternatives

1. **Extend `validate.py` with an optional GitHub mode.** Rejected: the
   validator's contract is that it is offline and read-only for both network and
   filesystem (`roadmap/README.md`: "The validator is intentionally offline and
   read-only"), and `.github/workflows/roadmap-validate.yml` runs it on every
   roadmap PR with `permissions: {}`. Mixing a network path into it would put a
   token requirement onto a workflow that deliberately has none. A separate
   `reconcile.py` that imports `validate` keeps one validation implementation
   without weakening that boundary.

2. **Read the observed graph live in CI instead of from a captured snapshot.**
   Rejected for this slice: the pilot spans five repositories, so CI would need
   a cross-repo read token, and the tests would become non-deterministic (the
   real `human-input` graph is not converged today and changes whenever a human
   edits an issue). The snapshot source makes "converged fixture returns no
   drift" a real, stable assertion; `--live` remains available for operators and
   for the later `RoadmapReconcileWorkflow` in `mctl-agents`.

3. **Implement the reconciler in `mctl-agents` (TypeScript/Python workflow code)
   straight away.** Rejected as premature: the desired-state derivation depends
   on manifest semantics that live here and are already covered by
   `roadmap/tests/test_validate.py`, and the issue explicitly scopes this to a
   read-only detector with machine-readable output. Keeping the detector next to
   the contract lets `mctl-agents` later import or shell out to a proven,
   version-pinned artifact instead of re-deriving the graph rules.

4. **Reconstruct dependencies from `Depends on` prose in issue bodies.**
   Rejected: an explicit non-goal of the issue ("LLM-based interpretation of
   issue prose"), and non-deterministic by construction. Only native sub-issue
   and issue-dependency relations are read.

## Platform impact

- **Migrations:** none. No schema in `roadmap/schemas/epic-definition.schema.json`
  changes, `roadmap/epics/human-input.yaml` is untouched, and no data store is
  involved. Two new schemas are added for new artifacts only.
- **Backward compatibility:** `validate.py` keeps its current public functions
  and exit codes; `reconcile.py` imports them rather than forking them. Existing
  CI steps are unchanged; one step is added. `RoadmapDiff` and
  `GitHubGraphSnapshot` are introduced at `v1alpha1`, so later shape changes are
  permitted under the same alpha contract that `EpicDefinition` already uses.
- **Dependencies / resource impact:** no new pip dependency. Fixture-mode
  reconciliation is pure CPU over a handful of issues — CI cost is under a
  second. Live mode is O(issues) requests: one batched GraphQL query plus one
  REST call per issue (7 issues for the pilot), well inside rate limits.
- **Security:** the reconciler needs `contents: read` and `issues: read` only,
  and never receives a write-capable token in this repository. The GET-only
  guard in `github_graph._get` is enforced in code and asserted by a test, so
  "no GitHub write permission is required" is verifiable rather than asserted.
  Manifest content is untrusted only insofar as it is reviewed via PR; issue
  titles fetched from GitHub are treated as opaque data, are never interpolated
  into shell commands (all HTTP goes through `urllib.request`, no `gh` subprocess
  and no `run:` interpolation), and the existing `issueRef.repository` pattern
  already rejects shell-like values — see
  `test_repository_ref_rejects_shell_like_or_spacey_values`.
- **Risks and mitigations:**
  - *GitHub's sub-issue / issue-dependency API shape changes or differs from
    what is assumed.* Mitigated by isolating every API detail in
    `github_graph.LiveGraphSource` behind the provider-neutral snapshot schema;
    the detector, the diff contract, and all tests are unaffected by an adapter
    rewrite.
  - *False drift from repository name casing or from issues transferred between
    repositories.* Mitigated by canonical lowercase keys and by explicit
    `BindingRedirected` handling instead of silent mismatch.
  - *A cascade of misleading entries when one issue is unreachable.* Mitigated
    by computing binding entries first and suppressing dependent edges.
  - *The captured fixture rots against reality.* Accepted for this read-only
    slice and mitigated by `--capture`, which regenerates the snapshot in one
    command; the fixture's job is to prove detector behaviour, not to mirror
    live state.
  - *Someone later adds an apply path on top of this output.* Mitigated by
    keeping write capability entirely absent from the module and by the
    both-directions mutation tests that `roadmap/README.md` makes a
    precondition for enabling writes.
