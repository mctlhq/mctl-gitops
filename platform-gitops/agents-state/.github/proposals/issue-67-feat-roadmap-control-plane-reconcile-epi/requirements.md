# Read-only EpicDefinition reconciliation against the live GitHub graph

## Context

`roadmap/` in `mctlhq/.github` already holds the authored desired state for the
roadmap control plane: the `roadmap.mctl.ai/v1alpha1` `EpicDefinition` contract
(`roadmap/schemas/epic-definition.schema.json`), the first pilot manifest
(`roadmap/epics/human-input.yaml`), and an intentionally offline validator
(`roadmap/scripts/validate.py`) that checks structure and graph invariants but,
as its module docstring states, "performs no GitHub reads or writes". The
remaining half of the loop described in `roadmap/README.md` under "Planned
reconciliation boundary" is missing: nothing yet compares the authored graph
with what GitHub actually shows.

Issue #67 asks for the first read-only slice of that comparison: load validated
manifests, resolve the bound parent issue and every bound work-item issue, read
native GitHub sub-issue relationships and issue dependency relationships,
normalize them, and emit deterministic `RoadmapDiff` entries. No GitHub writes,
no issue creation, no Project field updates, no LLM interpretation. The value is
that drift between the manifest and the collaboration surface becomes a
machine-readable, reviewable artifact that `mctl-api` can later persist as
observed state — and that the detector proves it can report green before anyone
is allowed to wire up an apply path. `roadmap/README.md` already states the bar:
"A detector that can only report drift is as broken as a guard that can only
pass."

## User stories

- AS a roadmap owner I WANT a command that compares `roadmap/epics/*.yaml` with
  the live GitHub issue graph SO THAT I can see exactly which parent and
  dependency edges are missing or wrong without reading issue prose.
- AS a platform engineer I WANT the drift result emitted as stable, schema-valid
  JSON SO THAT `mctl-api` can later ingest it as observed/read-model state
  without re-deriving anything.
- AS a reviewer I WANT hierarchy drift and dependency drift kept in separate
  result types SO THAT a missing sub-issue link is never silently conflated with
  a missing `Depends on` edge.
- AS a security reviewer I WANT the reconciler to hold no GitHub write
  permission and to be provably GET-only SO THAT a bug in the detector cannot
  mutate the collaboration surface.
- AS a maintainer I WANT the detector mutation-tested in both directions against
  a captured graph snapshot SO THAT a converged epic stays green and every
  deliberately broken edge turns red.
- AS a CI operator I WANT the offline test path to need no network and no token
  SO THAT `.github/workflows/roadmap-validate.yml` keeps running with
  `permissions: {}`.

## Acceptance criteria (EARS)

- WHEN the reconciler is invoked with one or more `EpicDefinition` paths THE
  SYSTEM SHALL first run `validate.validate_document` (schema plus semantic
  layer) and SHALL refuse to reconcile any manifest that fails validation,
  reporting the validation failures unchanged.
- WHEN a validated manifest is reconciled THE SYSTEM SHALL derive the desired
  hierarchy edge set as: every bound work item without `parent` is a child of
  `spec.github.issue`, and every bound work item with `parent` is a child of the
  issue bound to that parent work item.
- WHEN a validated manifest is reconciled THE SYSTEM SHALL derive the desired
  dependency edge set from `workItems[].dependsOn` (resolved to the bound issue
  of the target work item) and `workItems[].externalDependsOn` (used verbatim),
  in the direction "this issue is blocked by that issue".
- WHILE deriving desired edges THE SYSTEM SHALL ignore `spec.phases` ordering
  entirely and SHALL NOT create any dependency edge from phase membership.
- WHEN the observed graph is read THE SYSTEM SHALL collect, for each referenced
  issue, its existence, its state, its native sub-issue parent, its native
  sub-issue children, and its `blocked_by` issue dependency relationships, and
  SHALL normalize every issue reference to a canonical `owner/repo#number` key
  with case-insensitive repository matching.
- WHEN a desired hierarchy edge has no matching observed sub-issue relationship
  THE SYSTEM SHALL emit a `HierarchyMissingParent` entry naming the work item,
  the child issue, and the expected parent issue.
- IF an observed child issue has a sub-issue parent other than the desired
  parent THEN THE SYSTEM SHALL emit a `HierarchyWrongParent` entry carrying both
  the expected and the observed parent.
- IF an issue observed as a sub-issue of a manifest-bound parent is not bound by
  any work item of that epic THEN THE SYSTEM SHALL emit a
  `HierarchyUnexpectedChild` entry.
- WHEN a desired dependency edge has no matching observed `blocked_by`
  relationship THE SYSTEM SHALL emit a `DependencyMissing` entry.
- IF an observed `blocked_by` relationship on a bound issue is not in the
  desired dependency edge set THEN THE SYSTEM SHALL emit a
  `DependencyUnexpected` entry.
- IF a bound issue cannot be resolved on GitHub (404, or resolvable only as a
  redirect/transfer to a different repository or number) THEN THE SYSTEM SHALL
  emit a `BindingIssueNotFound` or `BindingRedirected` entry and SHALL suppress
  every desired edge that depends on that binding rather than reporting those
  edges as missing.
- IF the same issue is observed as a sub-issue of more than one parent, or one
  manifest binding resolves to more than one candidate issue THEN THE SYSTEM
  SHALL emit a `BindingAmbiguous` entry.
- WHEN a work item carries no `issue` binding THE SYSTEM SHALL emit an
  informational `BindingUnbound` entry carrying its `title` and `owner`, and
  SHALL NOT derive any edge from or to that work item.
- WHILE producing results THE SYSTEM SHALL keep hierarchy, dependency, and
  binding entries in separate, separately-typed collections of the emitted
  `RoadmapDiff` document.
- WHEN the reconciler finishes THE SYSTEM SHALL emit a `RoadmapDiff` JSON
  document (`apiVersion: roadmap.mctl.ai/v1alpha1`, `kind: RoadmapDiff`) that
  validates against a committed JSON Schema and carries the epic name, the
  manifest path, the SHA-256 of the exact manifest bytes, the graph source mode,
  per-family entry counts, and the entry collections.
- WHILE serializing the `RoadmapDiff` THE SYSTEM SHALL sort every entry
  collection by a deterministic key and SHALL NOT embed wall-clock timestamps,
  random values, or map iteration order, so that two runs over identical inputs
  produce byte-identical output.
- WHEN the same manifest and the same graph snapshot are reconciled twice THE
  SYSTEM SHALL produce byte-identical `RoadmapDiff` output.
- WHILE reading the live graph THE SYSTEM SHALL issue only HTTP GET requests and
  SHALL raise rather than perform any other HTTP method, and SHALL require only
  read scopes (`contents: read`, `issues: read`).
- WHEN the reconciler is run against a converged captured snapshot of the
  `human-input` pilot THE SYSTEM SHALL report zero drift entries and exit 0.
- WHEN exactly one parent edge, one dependency edge, or one issue binding is
  mutated in that snapshot THE SYSTEM SHALL report drift in the corresponding
  family, leave the other families unchanged, and exit 1.
- WHEN a mutated snapshot is restored to its original content THE SYSTEM SHALL
  again report zero drift entries.
- IF invocation is malformed (unreadable manifest, unreadable snapshot, missing
  credentials in live mode) THEN THE SYSTEM SHALL exit 2, distinct from the
  drift exit code 1 and the converged exit code 0, matching the existing
  `roadmap/scripts/validate.py` exit-code convention.
- WHEN roadmap files change in a pull request THE SYSTEM SHALL have its offline
  fixture-based tests executed by `.github/workflows/roadmap-validate.yml`
  without network access, without any GitHub token, and with `permissions: {}`
  preserved.

## Out of scope

- Any GitHub mutation: creating, editing, linking, or closing issues;
  adding/removing sub-issues or dependencies; updating Project fields.
- Creating issues for unbound work items (only reported, never created).
- Persisting the `RoadmapDiff` in `mctl-api` or exposing an API endpoint; this
  slice only guarantees the payload contract is stable enough to persist later.
- A `RoadmapReconcileWorkflow` in `mctl-agents`; only the reusable detector and
  its CLI land here.
- Critical-path, ready/blocked counts, and completion percentage derivation
  (`completion.mode: allRequired` evaluation) — observed issue state is
  collected and reported but not scored.
- LLM-based interpretation of issue titles, bodies, or `Depends on` prose
  sections; only native sub-issue and issue-dependency relations are read.
- Treating `spec.phases` order as dependency edges.
- Migrating additional epics (for example Enterprise MCP) onto `EpicDefinition`.

## Open questions

- Native issue dependencies are a comparatively new GitHub surface and are
  primarily exposed through REST (`/repos/{owner}/{repo}/issues/{number}/
  dependencies/blocked_by`) rather than a stable GraphQL field. The proposal
  isolates both reads behind one adapter and pins the snapshot schema to a
  provider-neutral shape; if the GraphQL surface is available for both
  relations at implementation time, the adapter should prefer a single batched
  GraphQL query for cost. Decided default: GraphQL for sub-issues, REST for
  dependencies, both GET-only.
- The issue does not say whether an observed sub-issue of the epic root that is
  not in the manifest is drift or acceptable human activity. Decided default:
  report it as `HierarchyUnexpectedChild` (informational severity) so the signal
  exists without implying a future deletion.
- The issue does not specify how cross-repository reads authenticate. Decided
  default: live mode reads a token from the environment and is never run from
  this repository's `permissions: {}` CI; only the offline snapshot path runs in
  CI here.
- Whether the captured snapshot of the pilot should be committed as a golden
  fixture or re-captured on demand. Decided default: commit one converged
  snapshot under `roadmap/fixtures/` as the single source of truth and derive
  every mutated variant from it in tests, so the mutation pairs cannot drift
  apart.
- Whether `RoadmapDiff` needs severity levels beyond the entry type. Decided
  default: each entry carries a fixed `severity` field (`drift` or `info`) so
  the later `mctl-api` read model does not have to hardcode a type list.
