# Requirements: governed roadmap maintenance operations

## Context

Roadmap Control Plane (`mctlhq/.github#66`) makes `EpicDefinition` the canonical desired graph, while Org Project #1 remains the source of truth for portfolio priority/status in the current slice. `mctlhq/.github#68` owns deterministic governed apply after read-only reconciliation `#67` is proven.

Portfolio hygiene still needs a safe semantic mutation surface for routine work: create/close roadmap work, update bounded roadmap metadata, re-parent work items, and change portfolio priority. Exposing raw GitHub Issues/Projects write through MCP would bypass the control-plane invariants and make arbitrary repository/project targets caller-controlled.

## Goal

Expose narrow `mctl_roadmap_*` operations in `mctl-api` that resolve canonical targets server-side, route graph changes through the reviewed EpicDefinition/RoadmapProposal path, route portfolio priority to the configured Org Project field, and preserve policy/approval/audit boundaries.

Candidate operations:

- `mctl_roadmap_create_work_item`
- `mctl_roadmap_update_work_item`
- `mctl_roadmap_close_work_item`
- `mctl_roadmap_reparent_work_item`
- `mctl_roadmap_set_priority`

Final names may follow existing mctl tool naming conventions, but no generic GitHub mutation tool is permitted.

## Acceptance criteria (EARS)

- WHEN a roadmap mutation is requested THE SYSTEM SHALL derive the authenticated actor from request context and SHALL NOT accept caller-supplied actor/approver identity.
- WHEN a target epic/work item is supplied THE SYSTEM SHALL resolve its canonical roadmap/GitHub binding server-side and SHALL NOT accept arbitrary repository, Project, field, option, REST path, GraphQL fragment, or raw GitHub payload parameters.
- WHEN the requested change alters EpicDefinition-owned graph state THE SYSTEM SHALL produce or amend a reviewable RoadmapProposal/EpicDefinition change and SHALL NOT directly mutate GitHub from caller arguments.
- WHEN graph apply becomes eligible THE SYSTEM SHALL bind execution to the exact reviewed manifest path, git revision, and content hash and SHALL delegate deterministic GitHub mutation to the `#68` mctl-agents boundary.
- WHILE `mctlhq/.github#67` has not proven converged→drift→restored-green reconciliation THE SYSTEM SHALL keep graph mutation operations unavailable/fail closed.
- WHEN a work item is re-parented THE SYSTEM SHALL validate the complete EpicDefinition corpus, reject parent/dependency cycles, and apply only the resulting deterministic diff.
- WHEN a required work item is requested to close/remove THE SYSTEM SHALL fail closed if the canonical manifest still requires it or if unresolved required dependents make the transition invalid.
- WHEN a roadmap work item is created for a migrated epic THE SYSTEM SHALL make the reviewed manifest/proposal authoritative before issue creation so retry cannot create an orphan issue outside desired state.
- WHEN portfolio priority is changed THE SYSTEM SHALL mutate only the configured Org Project #1 priority field and SHALL NOT add priority/status to EpicDefinition.
- WHEN priority is changed THE SYSTEM SHALL accept only configured canonical values (`P0`, `P1`, `P2`, `PARK`, or their server-side mapped Project option values) and SHALL resolve Project/item/field/option IDs internally.
- WHEN a Project field mutation is attempted THE SYSTEM SHALL compare the observed current value with the expected value/revision and SHALL return a conflict rather than silently overwrite a concurrent human edit.
- WHEN a mutation is retried/replayed THE SYSTEM SHALL be idempotent and SHALL NOT create duplicate issues, relations, Project updates, or audit effects.
- WHEN a consequential mutation requires policy/approval THE SYSTEM SHALL keep lifecycle ownership separate from authorization and SHALL execute only after the required decision is satisfied.
- WHEN any mutation completes THE SYSTEM SHALL audit actor, semantic operation, canonical roadmap target, resolved GitHub/Project target, exact manifest revision/hash when applicable, before/after Project value when applicable, policy/approval reference, workflow/activity id, and final outcome.
- WHEN audit/evidence is written THE SYSTEM SHALL NOT copy full issue bodies, prompts, or arbitrary user-provided GitHub payloads into telemetry.
- THE SYSTEM SHALL NOT expose generic `mctl_create_issue`, `mctl_update_issue`, raw GitHub REST, raw GitHub GraphQL, arbitrary issue-body replacement, or arbitrary Project-field mutation as part of this feature.

## Pilot acceptance evidence

The first release should prove the exact portfolio-hygiene cases that motivated the capability:

1. set `.github#57` to P0 and `#66/#18/#35/#42` to P1 through the Project-owned priority operation;
2. re-parent or correct stale roadmap graph relations only through reviewed EpicDefinition change/apply;
3. supersede/close obsolete roadmap work without bypassing required-work/dependency checks;
4. replay each mutation and prove no duplicate effective write.

## Non-goals

- Generic GitHub issue administration.
- Generic GitHub REST/GraphQL passthrough.
- Adding portfolio priority/status to EpicDefinition.
- Replacing GitHub Issues/Projects UI.
- Applying graph changes before #67 is proven.
- Allowing an LLM to choose arbitrary mutation targets after approval.
