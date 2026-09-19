# Requirements: governed roadmap maintenance operations

## Context

Roadmap Control Plane (`mctlhq/.github#66`) makes `EpicDefinition` the canonical desired graph, while Org Project #1 remains the source of truth for portfolio priority/status in the current slice. Read-only reconciliation `mctlhq/.github#67` is completed; `mctlhq/.github#68` owns deterministic governed graph apply and remains open.

The existing `mctl-api` write surface is centered on `internal/operations/registry.go`, `internal/operations/executor.go`, `internal/api/handlers_write.go`, `internal/mcp/server.go`, and audit under `internal/audit/`. `mctlhq/mctl-api#252` specifies the durable RoadmapProposal/hash workflow but is still open, so graph-owned roadmap mutations must depend on that substrate landing (or factor the same substrate into this implementation) rather than assume it already exists.

Portfolio hygiene needs a safe semantic mutation surface for routine work: create/close/supersede roadmap work, bounded updates, re-parenting, and portfolio priority changes. Exposing raw GitHub Issues/Projects write through MCP would bypass the control-plane invariants and make arbitrary repository/project targets caller-controlled.

## Goal

Expose narrow `mctl_roadmap_*` operations in `mctl-api` that resolve canonical targets server-side, route graph changes through reviewed EpicDefinition/RoadmapProposal state, route portfolio priority to the configured Org Project field, and preserve policy/approval/audit boundaries.

Candidate operations:

- `mctl_roadmap_create_work_item`
- `mctl_roadmap_update_work_item`
- `mctl_roadmap_close_work_item`
- `mctl_roadmap_supersede_work_item`
- `mctl_roadmap_reparent_work_item`
- `mctl_roadmap_set_priority`

Final names may follow existing mctl tool naming conventions, but no generic GitHub mutation tool is permitted.

## Acceptance criteria (EARS)

- WHEN a roadmap mutation is requested THE SYSTEM SHALL derive the authenticated actor from request context in `internal/api/handlers_write.go` or the equivalent dedicated handler and SHALL NOT accept caller-supplied actor/approver identity.
- WHEN a target epic/work item is supplied THE SYSTEM SHALL resolve its canonical roadmap/GitHub binding server-side using the same case-insensitive owner/repository + issue-number identity invariant as the `#67` reconciler and SHALL NOT accept arbitrary repository, Project, field, option, REST path, GraphQL fragment, or raw GitHub payload parameters.
- WHEN semantic operations are registered THE SYSTEM SHALL define their parameters/risk in `internal/operations/registry.go` and mirror the public MCP schema/annotations in `internal/mcp/server.go` with parity tests.
- WHEN the requested change alters EpicDefinition-owned graph state THE SYSTEM SHALL create a reviewable RoadmapProposal/EpicDefinition draft and SHALL NOT directly mutate GitHub from caller arguments.
- WHEN a graph proposal reaches its immutable reviewable/approved state THE SYSTEM SHALL NOT amend its publishable payload in place; a changed desired result SHALL create a new proposal/revision.
- WHEN graph apply becomes eligible THE SYSTEM SHALL bind execution to the exact merged manifest path, git revision, and SHA-256 of the exact EpicDefinition manifest bytes and SHALL delegate deterministic GitHub mutation to the `#68` mctl-agents boundary.
- WHEN RoadmapProposal content is hashed separately from the EpicDefinition manifest THE SYSTEM SHALL name and persist the hashes separately (`proposal_content_hash` vs exact-byte `manifest_sha256`) and SHALL NOT treat canonical-JSON and manifest-byte hashes as interchangeable.
- WHILE `mctlhq/.github#68` deterministic apply has not been implemented and proven THE SYSTEM SHALL keep graph create/update/close/supersede/reparent apply unavailable/fail closed; this gate SHALL NOT block the independent Project-owned priority operation.
- WHEN a work item is created or updated with a phase THE SYSTEM SHALL treat phase as metadata only and SHALL NOT infer dependency edges from phase order, parent order, or sibling order.
- WHEN a work item is re-parented THE SYSTEM SHALL validate the complete EpicDefinition corpus, reject parent/dependency cycles, and apply only the resulting deterministic diff.
- WHEN a required work item is requested to close/remove THE SYSTEM SHALL fail closed if the canonical manifest still requires it or if unresolved required dependents make the transition invalid.
- WHEN a work item is superseded THE SYSTEM SHALL require an explicit canonical successor reference and SHALL validate/rewrite desired-state relationships before the predecessor can reach a terminal state.
- WHEN a roadmap work item is created for a migrated epic THE SYSTEM SHALL require the corresponding EpicDefinition change to be merged first and SHALL bind issue materialization to that exact merged revision/manifest hash so retry cannot create an orphan issue outside desired state.
- WHEN portfolio priority is changed THE SYSTEM SHALL mutate only the configured Org Project #1 priority field and SHALL NOT add priority/status to EpicDefinition.
- WHEN priority is changed THE SYSTEM SHALL accept only configured canonical values (`P0`, `P1`, `P2`, `PARK`) and SHALL resolve Project/item/field/option IDs internally.
- WHEN a Project priority write is attempted THE SYSTEM SHALL serialize MCTL-originated writes for the canonical item, re-read the current value immediately before mutation, reject an `expected_priority` mismatch, perform the fixed server-side Project mutation, and re-read the result after mutation.
- WHEN GitHub Project v2 offers no server-side conditional-update primitive THE SYSTEM SHALL NOT claim atomic compare-and-set against concurrent human edits; audit/docs SHALL state that an external human edit racing between the final pre-write read and GitHub mutation cannot be prevented by the API.
- WHEN a mutation is retried/replayed THE SYSTEM SHALL be idempotent and SHALL NOT create duplicate issues, relations, Project updates, proposals, or audit effects.
- WHEN a consequential mutation requires policy/approval THE SYSTEM SHALL keep lifecycle ownership separate from authorization and SHALL execute only after the required decision is satisfied.
- WHEN any mutation completes THE SYSTEM SHALL audit actor, semantic operation, canonical roadmap target, resolved GitHub/Project target, exact proposal/manifest hashes when applicable, before/after Project value when applicable, policy/approval reference, workflow/activity id, and final outcome through the existing audit path under `internal/audit/`.
- WHEN audit/evidence is written THE SYSTEM SHALL NOT copy full issue bodies, prompts, or arbitrary user-provided GitHub payloads into telemetry.
- THE SYSTEM SHALL NOT expose generic `mctl_create_issue`, `mctl_update_issue`, raw GitHub REST, raw GitHub GraphQL, arbitrary issue-body replacement, or arbitrary Project-field mutation as part of this feature.

## Pilot acceptance evidence

The first release should prove the exact portfolio-hygiene cases that motivated the capability:

1. set `.github#57` to P0 and `#66/#18/#35/#42` to P1 through the Project-owned priority operation;
2. re-parent or correct stale roadmap graph relations only through reviewed/merged EpicDefinition change plus #68 apply;
3. supersede/close obsolete roadmap work without bypassing required-work/dependency/successor checks;
4. replay each mutation and prove no duplicate effective write.

## Non-goals

- Generic GitHub issue administration.
- Generic GitHub REST/GraphQL passthrough.
- Adding portfolio priority/status to EpicDefinition.
- Replacing GitHub Issues/Projects UI.
- Claiming atomic Project-v2 CAS against external human edits when GitHub exposes no conditional mutation.
- Applying graph changes before #68 is proven.
- Allowing an LLM to choose arbitrary mutation targets after approval.
