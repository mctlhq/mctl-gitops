# Read-only EpicDefinition reconciliation against the live GitHub graph

## Context

Issue #67 adds the observed-state half of the roadmap control plane: deterministic comparison of validated `EpicDefinition` manifests against native GitHub issue hierarchy and dependency relations. This slice is read-only, emits a stable `RoadmapDiff`, does not interpret issue prose, and must prove both green and red detector directions before any apply path exists.

## User stories

- AS a roadmap owner I WANT a command that compares `roadmap/epics/*.yaml` with the live GitHub graph SO THAT parent/dependency drift is explicit.
- AS a platform engineer I WANT stable schema-valid JSON SO THAT `mctl-api` can later persist observed state without re-deriving the graph.
- AS a reviewer I WANT hierarchy, dependency, and binding drift kept separate SO THAT unrelated failure families are never conflated.
- AS a security reviewer I WANT the live adapter to be structurally GET-only SO THAT the detector cannot mutate GitHub.
- AS a maintainer I WANT a synthetic converged fixture plus mutation tests SO THAT green → red → restored-green behaviour is deterministic and offline.

## Acceptance criteria (EARS)

- WHEN one or more manifests are selected for reconciliation THE SYSTEM SHALL first load and validate the **entire canonical corpus** under `roadmap/epics/` (or an explicitly supplied test corpus root), running schema + per-manifest validation and existing corpus invariants before any GitHub read. Selecting one manifest SHALL NOT narrow corpus-wide uniqueness checks. Duplicate `metadata.name` or duplicate GitHub issue bindings anywhere in the corpus SHALL exit 2 with zero network calls.
- WHEN GitHub issue identity is compared during Phase-0 validation THE SYSTEM SHALL canonicalize the repository component case-insensitively for root bindings, work-item bindings, `externalDependsOn`, and corpus-wide ownership. Case variants such as `mctlhq/mctl-api#261` and `MCTLHQ/MCTL-API#261` SHALL identify the same GitHub issue. Authored spelling MAY be retained for diagnostics, but MUST NOT affect ownership/equality decisions.
- WHEN two authored bindings differ only by repository casing THE SYSTEM SHALL reject them as a duplicate binding before any GitHub read; WHEN `externalDependsOn` differs only by casing from a locally bound issue THE SYSTEM SHALL reject it and require local `dependsOn`.
- WHEN a validated manifest is reconciled THE SYSTEM SHALL derive desired hierarchy as `(parent, child)` and dependencies as `(blocked, blocker)` from `dependsOn` and `externalDependsOn`; phase order SHALL NOT create edges.
- WHEN live state is read THE SYSTEM SHALL use GitHub REST GET endpoints only: issue GET, `/parent`, `/sub_issues`, and `/dependencies/blocked_by`; GraphQL is out of scope for this slice.
- ANY attempted non-GET method or request body SHALL fail before transmission.
- WHEN an authored issue resolves to a different canonical repository/number THE SYSTEM SHALL emit exactly one `BindingRedirected`, preserve requested and resolved identities, and use the **resolved canonical key** for hierarchy/dependency comparison. Redirect alone SHALL NOT suppress relations or create cascaded relation drift.
- IF a bound issue cannot be resolved THE SYSTEM SHALL emit `BindingIssueNotFound` and suppress dependent hierarchy/dependency comparisons.
- IF a binding or parent observation is ambiguous THE SYSTEM SHALL emit `BindingAmbiguous` and suppress dependent relation comparisons for that endpoint.
- WHEN hierarchy differs THE SYSTEM SHALL emit `HierarchyMissingParent` or `HierarchyWrongParent`.
- WHEN an observed child is not owned by the manifest THE SYSTEM SHALL emit informational `HierarchyUnexpectedChild` and SHALL NOT change exit 0 by itself. It is informational in severity, not optional in emission: the reconciler always reports it, and the exit code ignores it.
- WHEN dependency state differs THE SYSTEM SHALL emit `DependencyMissing` or `DependencyUnexpected`.
- WHEN a work item is intentionally unbound THE SYSTEM SHALL emit informational `BindingUnbound`, derive no edge through it, and SHALL NOT change exit 0 by itself.
- WHEN reconciliation completes THE SYSTEM SHALL emit `apiVersion: roadmap.mctl.ai/v1alpha1`, `kind: RoadmapDiff`, exact manifest-byte SHA-256, source metadata, per-family counts, and separate `binding`, `hierarchy`, and `dependency` collections.
- SERIALIZATION SHALL be deterministic: stable collection ordering, no generated timestamp/random value in the diff, byte-identical JSON for identical manifest + snapshot bytes.
- FIXTURE mode SHALL distinguish immutable live captures from synthetic green test fixtures. Synthetic fixtures SHALL NOT claim a live capture timestamp.
- WHEN the Human Input synthetic converged fixture is reconciled THE SYSTEM SHALL report zero drift-severity entries and exit 0.
- WHEN one parent edge, dependency edge, binding, or redirect mapping is deliberately mutated THE SYSTEM SHALL report only the expected drift; restoring the mutation SHALL return to green.
- WHEN roadmap files change in CI THE SYSTEM SHALL run only offline fixture-based reconciliation under existing `permissions: {}`.

## Out of scope

- Any GitHub mutation or auto-remediation.
- Persisting `RoadmapDiff` in `mctl-api`.
- A runtime `RoadmapReconcileWorkflow` in `mctl-agents`.
- Critical-path/progress scoring or LLM interpretation of issue prose.
- Migrating additional epics.

## Resolved design decisions

- **Parent endpoint verified:** GitHub documents `GET /repos/{owner}/{repo}/issues/{issue_number}/parent` as the REST **Get parent issue** endpoint with `Issues: read` permission.
- **Corpus scope:** reconciliation targets may be a subset, but corpus invariants always run against the full canonical `roadmap/epics/` corpus (or explicit test corpus root) before live access.
- **Canonical issue identity:** repository identity is case-insensitive everywhere an authored GitHub issue key participates in Phase-0 validation or Phase-1 reconciliation. The validator and reconciler MUST use the same canonical key so global ownership cannot pass validation and later collapse onto one observed GitHub entity.
- **Redirect semantics:** `BindingRedirected` is binding drift; relations are then compared using the resolved canonical key. Redirect alone never suppresses relations.
- **Suppression:** only unresolved/ambiguous bindings and intentionally unbound desired work suppress dependent comparisons.
- **Fixture provenance:** live capture and synthetic converged fixture are separate artifact classes.
