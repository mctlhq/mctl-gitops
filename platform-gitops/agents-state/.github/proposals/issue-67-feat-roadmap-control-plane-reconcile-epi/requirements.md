# Read-only EpicDefinition reconciliation against the live GitHub graph

## Context

`roadmap/` in `mctlhq/.github` already contains the authored desired-state contract for the roadmap control plane: `roadmap.mctl.ai/v1alpha1` `EpicDefinition`, the Human Input pilot manifest, and the intentionally offline validator. What is missing is the observed-state half of the loop: deterministic comparison of the validated manifest against the native GitHub issue graph.

Issue #67 asks for that first read-only slice. The implementation must resolve bound issues, read native sub-issue and issue-dependency relationships, normalize them, and emit a stable `RoadmapDiff`. It must not mutate GitHub, must not interpret issue prose, and must prove both green and red detector directions before any apply path exists.

## User stories

- AS a roadmap owner I WANT a command that compares `roadmap/epics/*.yaml` with the live GitHub graph SO THAT parent/dependency drift is explicit.
- AS a platform engineer I WANT stable schema-valid JSON SO THAT `mctl-api` can later persist observed state without re-deriving the graph.
- AS a reviewer I WANT hierarchy, dependency, and binding drift kept separate SO THAT unrelated failure families are never conflated.
- AS a security reviewer I WANT the live adapter to be structurally GET-only and require read scopes only SO THAT the detector cannot mutate GitHub.
- AS a maintainer I WANT a committed synthetic converged fixture plus mutation tests SO THAT green → red → restored-green behaviour is deterministic and offline.

## Acceptance criteria (EARS)

- WHEN one or more `EpicDefinition` manifests are selected THE SYSTEM SHALL run schema + per-manifest validation and SHALL also run the existing corpus invariants across the selected set before any GitHub read. Duplicate `metadata.name` or duplicate GitHub issue bindings across manifests SHALL fail reconciliation with exit 2.
- WHEN a validated manifest is reconciled THE SYSTEM SHALL derive desired hierarchy as `(parent, child)`: a bound item without `parent` is a child of `spec.github.issue`; a bound item with `parent` is a child of the issue bound to that parent work item.
- WHEN a validated manifest is reconciled THE SYSTEM SHALL derive desired dependencies as `(blocked, blocker)` from `dependsOn` and `externalDependsOn`.
- WHILE deriving desired edges THE SYSTEM SHALL ignore `spec.phases` ordering and SHALL NOT create dependencies from phase membership.
- WHEN live observed state is read THE SYSTEM SHALL use GitHub REST **GET** endpoints only: issue GET for existence/state and redirect detection, `/parent`, `/sub_issues`, and `/dependencies/blocked_by`. The implementation SHALL NOT use GraphQL in this slice because the read-only contract is defined as HTTP GET-only.
- WHILE reading live state THE SYSTEM SHALL require only `contents: read` and `issues: read`; any attempted non-GET method or request body SHALL fail before transmission.
- WHEN an issue GET follows or reports a transfer/redirect to a different canonical repository/number THE SYSTEM SHALL emit `BindingRedirected`, preserving the requested and resolved identities.
- WHEN a desired hierarchy edge is absent THE SYSTEM SHALL emit `HierarchyMissingParent`; IF the child is observed under a different parent THE SYSTEM SHALL emit `HierarchyWrongParent`.
- IF an observed sub-issue of a manifest-bound parent is not bound by the manifest THE SYSTEM SHALL emit informational `HierarchyUnexpectedChild`.
- WHEN a desired dependency is absent THE SYSTEM SHALL emit `DependencyMissing`; IF an observed `blocked_by` relation has no authored counterpart THE SYSTEM SHALL emit `DependencyUnexpected`.
- IF a bound issue cannot be resolved THE SYSTEM SHALL emit `BindingIssueNotFound` and SHALL suppress hierarchy/dependency comparisons that depend on that unresolved binding.
- IF one binding resolves ambiguously, or the observed graph assigns one child to more than one parent, THE SYSTEM SHALL emit `BindingAmbiguous`.
- WHEN a work item is intentionally unbound THE SYSTEM SHALL emit informational `BindingUnbound` carrying its `title` and `owner`, SHALL derive no edge through it, and SHALL NOT change exit 0 by itself.
- WHEN reconciliation completes THE SYSTEM SHALL emit `apiVersion: roadmap.mctl.ai/v1alpha1`, `kind: RoadmapDiff`, with epic name, manifest path, SHA-256 of the exact manifest bytes, source metadata, per-family counts, and separately typed `binding`, `hierarchy`, and `dependency` collections.
- WHILE serializing results THE SYSTEM SHALL sort all collections deterministically, SHALL NOT add wall-clock timestamps or random values, and SHALL produce byte-identical JSON for identical manifest bytes + snapshot bytes.
- WHEN fixture mode is used THE SYSTEM SHALL distinguish **captured live evidence** from **synthetic test fixtures**. A hand-adjusted converged fixture SHALL be marked `source.mode: synthetic-fixture` and SHALL NOT claim a live `capturedAt` timestamp. If derived from a real capture it MAY carry `source.derivedFrom` pointing at that immutable capture artifact.
- WHEN live capture mode writes a snapshot THE SYSTEM SHALL mark it `source.mode: live-capture` and include the actual capture timestamp and API base. Live captures SHALL NOT be silently hand-edited and still presented as captured evidence.
- WHEN the Human Input synthetic converged fixture is reconciled THE SYSTEM SHALL report zero drift-severity entries and exit 0.
- WHEN exactly one parent edge, dependency edge, or issue binding is mutated THE SYSTEM SHALL report drift only in the corresponding family and exit 1.
- WHEN each mutation is restored THE SYSTEM SHALL again exit 0.
- IF invocation is malformed, a manifest/snapshot is unreadable, credentials are absent in live mode, or validation/corpus validation fails THE SYSTEM SHALL exit 2.
- WHEN roadmap files change in CI THE SYSTEM SHALL run only offline fixture-based reconciliation under `.github/workflows/roadmap-validate.yml`, preserving `permissions: {}` and requiring no token.

## Out of scope

- Any GitHub mutation, issue creation, sub-issue/dependency apply, Project field update, or auto-remediation.
- Persisting `RoadmapDiff` in `mctl-api` or exposing a platform API in this slice.
- A `RoadmapReconcileWorkflow` in `mctl-agents`; this issue lands only the reusable detector/CLI and contracts.
- Critical-path/progress scoring, `completion.mode` evaluation, or LLM interpretation of issue prose.
- Treating phase order as dependencies.
- Migrating additional epics.

## Resolved design decisions

- Live transport: REST GET-only for issue, parent, sub-issues, and blocked-by reads; no GraphQL in this slice.
- Validation: selected manifests must pass both `validate_document` and the existing corpus invariants before any live access.
- Fixtures: keep provenance explicit. A synthetic converged fixture is test input, not live evidence; if a real capture is retained, it is a separate immutable artifact.
- Unexpected children are informational so humans can see them without implying a future delete.
- Each diff entry carries fixed severity `drift` or `info` so later consumers do not need a hard-coded type list.
