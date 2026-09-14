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
        │      ↓ exact hash/revision
        │  mctl-agents deterministic apply (#68)
        │      ↓
        │    GitHub issue graph
        │
        └── Project-owned priority
               ↓
          deterministic Project mutation
               ↓
          Org Project #1
```

`EpicDefinition` remains the desired graph authority. Org Project #1 remains the priority/status authority for this slice. The operation layer never creates a third editable copy of either state.

## mctl-api surface

Add a roadmap maintenance package beside the existing roadmap proposal API, reusing authenticated actor context, operation registry, risk classification, audit, rate limiting, and Temporal/workflow submission patterns.

Suggested semantic request shapes:

```text
create_work_item(parent_ref, intent/title, required?, phase?)
update_work_item(work_item_ref, bounded_patch)
close_work_item(work_item_ref, expected_state?)
reparent_work_item(work_item_ref, new_parent_ref)
set_priority(roadmap_ref, priority, expected_priority?)
```

Inputs use roadmap refs/work-item IDs, not raw GitHub owner/repo/issue/project IDs. A compatibility path may accept a canonical mctlhq issue URL only when it resolves to a known roadmap binding; it must not broaden target authority.

## Graph-owned mutations

Create/update/close/reparent operations first resolve the relevant EpicDefinition and current observed RoadmapDiff. They then create a reviewable desired-state change rather than executing GitHub writes immediately.

For v1, reuse/extend the existing RoadmapProposal persistence/hash workflow from `mctl-api#252` rather than inventing a second approval store. The proposal payload should identify:

- semantic operation;
- canonical epic/work-item IDs;
- exact current manifest revision/hash;
- proposed manifest patch/result hash;
- expected observed graph revision/snapshot identity where available;
- rationale/actor metadata outside the immutable publishable payload as appropriate.

After review/approval and merge, `#68` owns deterministic apply in mctl-agents. No LLM participates in apply.

## Priority mutation

Priority is intentionally outside EpicDefinition. Implement `set_priority` as a narrowly configured Project mutation:

- Project owner/number configured server-side (`mctlhq`, Project #1 initially);
- field resolved by configured stable name/id;
- allowed values mapped server-side to Project option IDs;
- target Project item resolved from the canonical roadmap GitHub issue binding;
- read current value before write;
- enforce `expected_priority` / compare-and-set semantics;
- fail `409`/structured conflict when a human changed the field concurrently;
- use a minimal worker credential with only the required Project write capability;
- do not expose raw GraphQL in the MCP contract.

If GitHub requires GraphQL internally for Project v2, the GraphQL document is a fixed server implementation detail, never caller-provided.

## Close semantics

Closing is not equivalent to deleting a node. Before a migrated work item can close/supersede:

1. load/validate the full EpicDefinition corpus;
2. inspect required/optional status and dependent authored edges;
3. reject if the current desired graph still requires the work item in a way that makes closure inconsistent;
4. require the reviewed manifest change first when desired state must change;
5. only then let deterministic reconciliation project the terminal state/metadata allowed by #68.

## Reparent semantics

Reparent changes only authored hierarchy. It must never infer dependencies from the new phase/parent. Full-corpus validation runs before approval and again before apply. Cycle/conflict detection fails closed.

## Idempotency and concurrency

Every operation gets a deterministic idempotency key derived from semantic target + approved revision/hash + operation kind. Replays return the existing proposal/workflow/result.

Project writes use compare-and-set against the observed value. Graph apply verifies the exact approved manifest revision/hash and current binding state before mutation.

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

Reuse the operation audit path and execution/evidence correlation. Record semantic data and stable references, not sensitive/free-form payload duplication.

For Project priority writes: actor, roadmap ref, GitHub issue ref, Project item, previous/next logical priority, workflow/run/result.

For graph changes: actor, proposal id, manifest path, before/after hash, approved hash, resulting RoadmapDiff/apply workflow, touched GitHub refs, conflict/no-op/result.

## Dependencies and rollout

- Hard gate: `.github#67` must prove read-only reconciliation first.
- Graph writes depend on `.github#68` deterministic apply.
- Reuse `mctl-api#252` proposal/hash concepts where compatible.
- Do not block the read-only `#67` implementation on this proposal.

Rollout order:

1. priority operation (Project-owned, narrow independent mutation) behind admin/policy gate;
2. graph semantic request/preview path with no apply;
3. integrate exact-hash RoadmapProposal/EpicDefinition PR flow;
4. enable create/update/reparent/close only after #68 apply is proven;
5. run the portfolio-hygiene pilot and retain evidence.

## Failure semantics

Suggested structured errors:

- `ROADMAP_TARGET_NOT_FOUND`
- `ROADMAP_TARGET_AMBIGUOUS`
- `ROADMAP_NOT_MIGRATED`
- `ROADMAP_HASH_MISMATCH`
- `ROADMAP_GRAPH_CONFLICT`
- `ROADMAP_REQUIRED_WORK`
- `ROADMAP_DEPENDENT_WORK`
- `ROADMAP_CYCLE`
- `PROJECT_ITEM_NOT_FOUND`
- `PROJECT_PRIORITY_CONFLICT`
- `ROADMAP_MUTATION_NOT_ENABLED`
- `NOT_ADMIN`

## Rollback

Tool registration can be disabled without changing GitHub state. Project writes are individually auditable/reversible. Graph mutations remain recoverable by reverting the reviewed EpicDefinition revision and running deterministic reconciliation; no separate mutable roadmap database is introduced.
