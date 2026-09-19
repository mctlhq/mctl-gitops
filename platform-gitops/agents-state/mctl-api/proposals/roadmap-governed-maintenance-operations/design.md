# Design: governed roadmap maintenance operations

## Architecture boundary

This feature is a semantic control-plane surface, not a GitHub proxy.

```text
client / ChatGPT / agent
        ↓
mctl-api roadmap operation
        ↓
auth + policy + canonical target resolution
        ├── graph-owned change
        │      ↓
        │  RoadmapProposal / EpicDefinition PR
        │      ↓ exact merged revision + manifest-byte SHA-256
        │  mctl-agents deterministic apply (#68)
        │      ↓
        │    GitHub issue graph
        │
        └── Project-owned priority
               ↓
          narrow fixed Project mutation
               ↓
          Org Project #1
```

`EpicDefinition` remains the desired graph authority. Org Project #1 remains the priority/status authority for this slice. The operation layer never creates a third editable copy of either state.

## Concrete mctl-api change surface

The implementation is expected to reuse these existing paths rather than invent parallel control planes:

- `internal/operations/registry.go` / `registry_test.go` — semantic operation definitions, parameters, defaults and risk classification;
- `internal/operations/executor.go` — existing operation execution/idempotency conventions where applicable;
- `internal/api/handlers_write.go` — authenticated actor/RBAC/audit boundary for write operations;
- `internal/mcp/server.go` / `server_test.go` / `annotations_test.go` — MCP tool schema and annotation parity;
- `internal/api/router.go` — only if dedicated roadmap proposal/read routes are needed;
- `cmd/api/main.go` — wiring/config for Project identity, roadmap services/store and credentials;
- `internal/audit/logger.go`, `internal/audit/redact.go` and tests — semantic evidence without body/prompt leakage;
- `internal/roadmap/` — shared RoadmapProposal/target-resolution package once the substrate from `mctlhq/mctl-api#252` lands or is factored into the same implementation.

`mctlhq/mctl-api#252` is currently open. It is therefore a prerequisite/substrate for graph-owned proposal persistence, not an already-existing API. The implementation may land the common `internal/roadmap/` substrate first, but must not create a second approval store.

## Public semantic surface

Suggested request shapes:

```text
create_work_item(parent_ref, intent/title, required?, phase?)
update_work_item(work_item_ref, bounded_patch)
close_work_item(work_item_ref, expected_state?)
supersede_work_item(work_item_ref, successor_ref, expected_state?)
reparent_work_item(work_item_ref, new_parent_ref)
set_priority(roadmap_ref, priority, expected_priority?)
```

Inputs use roadmap refs/work-item IDs, not raw GitHub owner/repo/issue/project IDs. A compatibility path may accept a canonical mctlhq issue URL only when it resolves to a known roadmap binding; it must not broaden target authority.

Canonical GitHub issue identity follows the reconciler invariant from #67: owner/repository comparison is case-insensitive and issue number is numeric; authored casing is retained only for diagnostics/display.

`phase` is metadata. Neither create nor update nor reparent may infer dependencies from phase order, hierarchy order, or sibling order.

## Graph-owned mutations

Create/update/close/supersede/reparent first resolve the owning EpicDefinition and current observed RoadmapDiff. They create a reviewable desired-state change rather than executing GitHub writes immediately.

The proposal lifecycle must reuse the durable RoadmapProposal/hash model from `mctl-api#252` once available. Immutable proposal content and merged manifest identity are distinct concepts and use distinct hashes:

- `proposal_content_hash`: deterministic canonical JSON hash over the immutable review payload (the #252 contract);
- `manifest_sha256`: SHA-256 of the exact EpicDefinition YAML bytes that are merged and later reconciled/applied (the #67/#68 contract).

The proposal payload identifies at least:

- semantic operation;
- canonical epic/work-item IDs;
- exact current manifest path/revision/`manifest_sha256`;
- proposed resulting manifest bytes or deterministic patch plus resulting `manifest_sha256`;
- `proposal_content_hash` for the immutable review payload;
- expected observed graph snapshot/reference where available;
- rationale/actor metadata outside the immutable publishable payload as appropriate.

A draft may be regenerated before it becomes reviewable. Once READY/reviewable/approved, publishable content is immutable; a changed desired result creates a new proposal/revision.

For issue materialization, approval alone is not authority. The EpicDefinition change must be merged first, and apply must bind to that exact merged revision + exact-byte `manifest_sha256`. After merge, `#68` owns deterministic apply in `mctl-agents`; no LLM participates in apply.

## Close and supersede semantics

Closing and superseding are separate semantic operations.

Before close:

1. load and validate the full EpicDefinition corpus;
2. inspect required/optional status and authored dependents;
3. reject if desired state still requires the work item or unresolved required dependents make closure inconsistent;
4. require any necessary desired-state manifest change to merge first;
5. only then allow #68 to project the permitted terminal state.

Supersede additionally requires an explicit canonical `successor_ref`. The desired graph must be reviewed/merged with any required relation changes before the predecessor reaches terminal state. A prose-only "superseded by" note is not authoritative.

## Reparent semantics

Reparent changes only authored hierarchy. It must never infer dependencies from the new phase/parent. Full-corpus validation runs before approval and again before apply. Cycle/conflict detection fails closed.

## Priority mutation

Priority is intentionally outside EpicDefinition. `set_priority` is a narrowly configured Project mutation:

- Project owner/number configured server-side (`mctlhq`, Project #1 initially);
- field resolved by configured stable name/id;
- allowed logical values mapped server-side to Project option IDs;
- target Project item resolved from the canonical roadmap GitHub issue binding;
- MCTL-originated writes for one canonical item serialized with the existing operation/idempotency mechanism or a dedicated per-item lock;
- if `expected_priority` is supplied, re-read immediately before write and reject mismatch;
- perform a fixed server-side Project mutation (GraphQL document/variables are implementation-owned, never caller supplied);
- re-read after write and persist before/after/result evidence;
- retry is idempotent/no-op when the requested logical value is already present.

GitHub Project v2 does not expose an atomic conditional-update precondition for the field mutation. Therefore this feature does **not** promise true compare-and-set against an external human edit racing between the final read and mutation. Serialization prevents concurrent MCTL writers; pre/post reads detect many conflicts/drift, and the audit record makes the remaining external-race window explicit. The API must not advertise stronger semantics than GitHub provides.

## Idempotency and concurrency

Graph operations derive a deterministic idempotency key from semantic target + immutable proposal hash + resulting merged revision/manifest hash + operation kind. Replays return the existing proposal/workflow/result.

Priority operations derive their key from canonical Project item + requested logical priority + caller-visible idempotency/revision context. MCTL writers are serialized per canonical target; repeated identical requests produce one effective mutation/result.

Graph apply verifies the exact approved proposal, exact merged manifest bytes/hash and current binding state before mutation.

## Security

Initial release is admin-only unless a pre-existing roadmap-maintainer permission can be reused without widening authority.

Explicitly forbidden in public tool schemas:

- arbitrary owner/repo/project IDs;
- arbitrary issue numbers not resolvable from canonical bindings;
- raw REST path/method/body;
- raw GraphQL/query/variables;
- arbitrary Project field/option IDs;
- caller-supplied authenticated actor/approver;
- generic issue-body replacement.

## Audit/evidence

Reuse the existing audit path under `internal/audit/` and execution/evidence correlation. Record semantic data and stable references, not sensitive/free-form payload duplication.

For Project priority writes: actor, roadmap ref, canonical GitHub issue ref, Project item, previous/requested/observed-after logical priority, expected value if supplied, workflow/run/result and whether pre/post verification observed a conflict/drift.

For graph changes: actor, proposal id, `proposal_content_hash`, manifest path, before/after exact-byte `manifest_sha256`, merged git revision, resulting RoadmapDiff/apply workflow, touched GitHub refs, conflict/no-op/result.

## Dependencies and rollout

- Satisfied prerequisite: `.github#67` completed read-only reconciliation on 2026-09-16.
- Graph writes depend on `.github#68` deterministic apply being implemented and proven.
- Graph proposal persistence depends on the shared RoadmapProposal substrate specified by `mctl-api#252`; it is open and must land/be factored first.
- Project-owned priority does not depend on #68 and may ship first behind admin/policy gates.

Rollout order:

1. implement `mctl_roadmap_set_priority` with narrow fixed Project mutation, truthful concurrency semantics, idempotency and audit;
2. land/reuse the #252 RoadmapProposal substrate;
3. add graph semantic request/preview generation with no GitHub apply;
4. bind exact proposal hash + exact merged manifest-byte hash to the EpicDefinition PR/merge lifecycle;
5. enable create/update/close/supersede/reparent only after #68 apply is proven;
6. run the portfolio-hygiene pilot and retain evidence.

## Failure semantics

Suggested structured errors:

- `ROADMAP_TARGET_NOT_FOUND`
- `ROADMAP_TARGET_AMBIGUOUS`
- `ROADMAP_NOT_MIGRATED`
- `ROADMAP_HASH_MISMATCH`
- `ROADMAP_GRAPH_CONFLICT`
- `ROADMAP_REQUIRED_WORK`
- `ROADMAP_DEPENDENT_WORK`
- `ROADMAP_SUCCESSOR_REQUIRED`
- `ROADMAP_CYCLE`
- `PROJECT_ITEM_NOT_FOUND`
- `PROJECT_PRIORITY_CONFLICT`
- `PROJECT_PRIORITY_VERIFY_FAILED`
- `ROADMAP_MUTATION_NOT_ENABLED`
- `NOT_ADMIN`

## Rollback

Tool registration can be disabled without changing GitHub state. Project writes are individually audited/reversible. Graph mutations remain recoverable by reverting the reviewed EpicDefinition revision and running deterministic reconciliation/apply; no separate mutable roadmap desired-state database is introduced.
