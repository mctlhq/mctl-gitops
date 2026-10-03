# Design: issue-283-feat-agent-platform-publish-and-resolve

## Current state

### Storage

`internal/agentregistry/store.go` is a single `Store` around a `pgxpool.Pool`.
`NewStore` executes one `agentRegistrySchema` string of
`CREATE TABLE IF NOT EXISTS` statements at startup — there is no migration
tool in this repo. `internal/alerts/store.go:59-61` and
`internal/audit/postgres.go:44-46` extend their schemas with
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` appended to the same string, which
is the established pattern for evolving a table in place.

Four tables exist today:

- `agent_definitions (name PK, description, owner, created_at, archived_at)`
- `agent_versions (id, agent FK, version, manifest_json, git_sha,
  image_repository, image_digest, prompt_hash, created_at, created_by,
  UNIQUE(agent, version))` — immutable, `PublishVersion` never overwrites.
- `agent_releases (agent, environment, version, status, traffic_weight,
  updated_at, updated_by, PK(agent, environment))` — mutable, one row per
  pair, `active` is stored.
- `agent_promotions` — append-only audit of release changes, with
  `from_version`, `to_version` and a `rollback_of` self-reference.
- `agent_executions` — one row per DevLoopWorkflow step, carrying `version`
  and `image_ref` only.

`Store.promote` (store.go:337) is the shared write path behind
`PromoteRelease` and `Rollback`. It opens a transaction, takes
`pg_advisory_xact_lock(hashtext(agent + "/" + environment))` (an advisory
lock rather than a row lock, because `agent_releases` may have no row yet),
resolves the target version through a callback, verifies the version exists,
reads the current release as `from_version`, upserts `agent_releases`, and
inserts the `agent_promotions` audit row — all in one transaction. Rollback
is "whatever the latest promotion row says was here before", i.e. one step
back, not an exact revision. That is exactly the primitive the v1alpha2
contract needs replaced by exact-revision rollback.

### HTTP surface

`internal/api/handlers_agent_registry.go` holds every handler. They share
`requireAgentRegistryAdmin` (handlers_agent_registry.go:90), which returns
503 when `h.opts.AgentRegistry == nil`, 401 without a user and 403 for a
non-admin. Responses go through `writeJSON` / `writeError`
(`internal/api/handlers_read.go:850-858`); `writeError` emits only
`{"error": "<message>"}` — there is no machine-readable error code today.
`PublishAgentVersion` already does content validation in the handler
(`isBareImageRepository`, handlers_agent_registry.go:52, added after an
incident where a doubled tag produced `InvalidImageName`).

Routes are registered in `internal/api/router.go:321-333`:

```
r.Post("/agents", h.CreateAgentDefinition)
r.Post("/agents/{name}/versions", h.PublishAgentVersion)
r.Get("/agents/{name}/versions", h.ListAgentVersions)
r.Post("/agents/{name}/releases", h.UpdateAgentRelease)
r.Get("/agents/{name}/resolve", h.ResolveAgentRelease)
r.Post("/agents/executions", h.RecordAgentExecution)
r.Get("/agents/executions", h.ListAgentExecutions)
```

The comment at router.go:327-331 already anticipates this issue: it notes
that no 2-segment `GET /agents/{name}` exists yet, and that chi's radix tree
would still prefer the static `executions` segment if one were added — which
is precisely the route `mctl_get_agent` needs.

### MCP surface

`internal/mcp/server.go:169-176` registers the seven registry tools
(`toolCreateAgent`, `toolPublishAgentVersion`, `toolListAgentVersions`,
`toolResolveAgent`, `toolPromoteAgent`, `toolRollbackAgent`,
`toolListAgentExecutions`). Each is a thin `apiGet` / `apiPostJSON` wrapper
over the REST route above. `agentRegistryEnvironmentEnum`
(server.go:2962) mirrors the two store environments. Three test contracts
constrain any tool change:

- `internal/mcp/server_test.go:173` asserts an exact tool count (74 today).
- `internal/mcp/annotations_test.go` requires every `NewTool` call to declare
  readOnly/destructive/idempotent hints, requires `recordedHints` to have one
  entry per tool, and pins the exact read-only set
  (`TestReadOnlyToolsAreTheRecordedSet`).
- `internal/mcp/portal_allowlist_test.go` requires every registered tool to
  appear in `docs/portal-allowlist.json` with an explicit decision.

### Wiring and tests

`cmd/api/main.go:214-234` builds the store from `AGENT_REGISTRY_DB_URL`,
falling back to `AUDIT_DB_URL`; a nil store degrades the endpoints to 503
rather than failing startup. Postgres-backed tests
(`internal/agentregistry/store_test.go:26-56`,
`internal/api/handlers_agent_registry_test.go:32-40`) skip unless
`TEST_DATABASE_URL` is set, and truncate every registry table in
setup/cleanup. `go.mod` carries no semver library and no
`golang.org/x/mod`.

Nothing in the repo mentions `v1alpha2`, `ReleaseBinding`, `ExecutionProfile`
or `agent-platform`: this is a greenfield layer inside an existing package.

## Proposed solution

### Shape

Extend `internal/agentregistry` in place — same package, same pool, same
schema string — with new v1alpha2 tables and a parallel set of methods. No
existing table, column, method, route, response shape or MCP tool changes
behaviour. New code lands in new files so the diff is reviewable:

- `internal/agentregistry/v1alpha2_types.go` — the new record structs.
- `internal/agentregistry/v1alpha2_store.go` — publish/bind/resolve/rollback.
- `internal/agentregistry/semver.go` — the compatibility-range evaluator.
- `internal/api/handlers_agent_platform.go` — the new handlers.
- `internal/mcp/server.go` — new tool constructors next to the existing ones.
- `docs/agent-platform-registry.md` — the consumer and gitops contract.

### Schema (appended to `agentRegistrySchema`)

```sql
CREATE TABLE IF NOT EXISTS agent_definition_versions (
    id            SERIAL PRIMARY KEY,
    agent         TEXT NOT NULL REFERENCES agent_definitions(name),
    version       TEXT NOT NULL,
    api_version   TEXT NOT NULL DEFAULT 'agents.mctl.ai/v1alpha2',
    spec_json     JSONB NOT NULL,
    owner         TEXT NOT NULL,
    source_repo   TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    source_git_sha       TEXT NOT NULL,
    source_content_hash  TEXT NOT NULL,
    profile_range TEXT NOT NULL,          -- declared ExecutionProfile compatibility
    lifecycle     TEXT NOT NULL DEFAULT 'published',
    lifecycle_reason TEXT NOT NULL DEFAULT '',
    lifecycle_at  TIMESTAMPTZ,
    lifecycle_by  TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL,
    created_by    TEXT NOT NULL DEFAULT '',
    UNIQUE (agent, version)
);

CREATE TABLE IF NOT EXISTS agent_profile_versions (
    id            SERIAL PRIMARY KEY,
    profile       TEXT NOT NULL,
    version       TEXT NOT NULL,
    spec_json     JSONB NOT NULL,
    owner         TEXT NOT NULL,
    source_repo   TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    source_git_sha      TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    lifecycle     TEXT NOT NULL DEFAULT 'published',
    lifecycle_reason TEXT NOT NULL DEFAULT '',
    lifecycle_at  TIMESTAMPTZ,
    lifecycle_by  TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL,
    created_by    TEXT NOT NULL DEFAULT '',
    UNIQUE (profile, version)
);

CREATE TABLE IF NOT EXISTS agent_release_bindings (
    id                  SERIAL PRIMARY KEY,
    agent               TEXT NOT NULL REFERENCES agent_definitions(name),
    environment         TEXT NOT NULL,
    revision            INTEGER NOT NULL,
    definition_version  TEXT NOT NULL,
    profile             TEXT NOT NULL,
    profile_version     TEXT NOT NULL,
    profile_range       TEXT NOT NULL,    -- range as it read at bind time
    binding_source      TEXT NOT NULL,    -- 'registry' | 'manual'
    intent_repo         TEXT NOT NULL DEFAULT '',
    intent_path         TEXT NOT NULL DEFAULT '',
    intent_git_sha      TEXT NOT NULL DEFAULT '',
    rollback_of         INTEGER REFERENCES agent_release_bindings(id),
    reason              TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL,
    created_by          TEXT NOT NULL DEFAULT '',
    UNIQUE (agent, environment, revision),
    FOREIGN KEY (agent, definition_version)
        REFERENCES agent_definition_versions(agent, version),
    FOREIGN KEY (profile, profile_version)
        REFERENCES agent_profile_versions(profile, version)
);
CREATE INDEX IF NOT EXISTS agent_release_bindings_current
    ON agent_release_bindings (agent, environment, revision DESC);

ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS definition_version TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS profile            TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS profile_version    TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS binding_revision   INTEGER;
```

Key properties:

- **Append-only, derived active.** There is no `agent_release_bindings.active`
  column and no per-environment "current" row. The active binding is
  `ORDER BY revision DESC LIMIT 1`, exactly as ADR 007 requires. A rollback is
  a new revision whose `rollback_of` points at the restored row's `id` —
  reusing the linkage idea already present in `agent_promotions.rollback_of`
  but pointing at an exact revision instead of "one step back".
- **`agent_definitions` stays the parent.** One agent name, two version
  namespaces (v1 `agent_versions`, v1alpha2 `agent_definition_versions`).
  That is what "extend the registry, not create a second release database"
  means concretely, and it lets `mctl_get_agent` show both.
- **Immutability with a lifecycle side-channel.** `spec_json` and all
  provenance columns are write-once; only `lifecycle*` columns may change,
  and only along `published -> deprecated -> disabled`.

### Write path

`Store.CreateBinding(ctx, req)` mirrors `Store.promote`'s transaction shape,
which is the part of the existing code most worth copying:

1. `BEGIN`, then `pg_advisory_xact_lock(hashtext(agent + "/" + environment))`
   — same key construction as store.go:347, so a v1 promotion and a v1alpha2
   bind for the same pair cannot interleave either.
2. Load the definition version and the profile version `FOR SHARE`, failing
   with `ErrDefinitionVersionNotFound` / `ErrProfileVersionNotFound` (404) if
   absent, `ErrVersionDeprecated` / `ErrVersionDisabled` (422) if their
   lifecycle is not `published`.
3. Evaluate the definition's `profile_range` against the profile version via
   `semver.Satisfies`; `ErrIncompatibleProfile` (422) otherwise.
4. Reject `binding_source = compatibility-fixture` (422) — the registry is
   the mirror of the gitops validator's non-promotable rule.
5. `SELECT COALESCE(MAX(revision), 0) + 1` for the pair and insert. The
   advisory lock makes this gapless; `UNIQUE(agent, environment, revision)`
   is the belt-and-braces backstop.
6. `COMMIT`, return the stored row.

`RollbackBinding(ctx, agent, env, revision, reason, actor)` runs the same
transaction, loads the target revision (404 if it is not that pair's), re-runs
steps 2-3 against its pair (so a since-`disabled` version cannot be restored),
and appends a copy with `rollback_of = target.id`.

Idempotency: unlike `promote`, re-binding the pair that is already active is
**not** silently collapsed into a no-op. It appends a revision. The no-op
special case in `promote` (store.go:381-399) exists because `Rollback` reads
`from_version` off the latest audit row and a same-version row would poison
it; exact-revision rollback has no such coupling, and an append-only ledger
should record every publish (including a gitops re-merge of the same intent).

### Compatibility ranges

`go.mod` has no semver dependency. `internal/agentregistry/semver.go` adds a
~120-line evaluator over a deliberately narrow grammar: `MAJOR.MINOR.PATCH`
versions, and ranges built from space/comma-separated `>=`, `>`, `<=`, `<`,
`=` comparators plus `^` and `~`. `ParseRange` returns an error for anything
else, and publishing a definition whose `profile_range` fails to parse is a
400 — a range that cannot be evaluated must never reach bind time, where
failing open would be the dangerous outcome.

### REST surface

New routes, added in `internal/api/router.go` next to the existing block:

```
GET    /api/v1/agents                                  -> ListAgents
GET    /api/v1/agents/{name}                           -> GetAgent
POST   /api/v1/agents/{name}/definition-versions       -> PublishDefinitionVersion
GET    /api/v1/agents/{name}/definition-versions       -> ListDefinitionVersions
POST   /api/v1/agents/{name}/definition-versions/{version}/lifecycle
POST   /api/v1/agent-profiles/{profile}/versions       -> PublishProfileVersion
GET    /api/v1/agent-profiles/{profile}/versions       -> ListProfileVersions
POST   /api/v1/agent-profiles/{profile}/versions/{version}/lifecycle
POST   /api/v1/agents/{name}/bindings                  -> CreateBinding
GET    /api/v1/agents/{name}/bindings                  -> ListBindings (history)
GET    /api/v1/agents/{name}/bindings/resolve          -> ResolveBinding
GET    /api/v1/agents/{name}/bindings/{revision}       -> GetBinding
POST   /api/v1/agents/{name}/bindings/rollback         -> RollbackBinding
```

All reuse `requireAgentRegistryAdmin`. `GET /agents/{name}` is the 2-segment
route router.go:327-331 warned about; the static `"/agents/executions"` route
still wins in chi's radix tree, and a router test pins that so nobody has to
re-derive it.

`ResolveBinding` accepts **either** `?environment=production` (active binding
for that pair) **or** `?definition_version=1.4.0[&profile_version=2.1.0]`
(explicit pin, no environment consulted), satisfying the issue's "resolvable
by `name+version` and by `(agent, environment)`". Both return the same
envelope:

```json
{
  "apiVersion": "agents.mctl.ai/v1alpha2",
  "agent": "issue-investigator",
  "environment": "shadow",
  "revision": 3,
  "definition": {
    "version": "1.4.0", "lifecycle": "published", "owner": "mctl-agents",
    "sourceManifest": {"repo": "...", "path": "...", "gitSha": "...", "contentHash": "..."},
    "spec": { }
  },
  "profile": {
    "name": "standard-investigate", "version": "2.1.0", "lifecycle": "published",
    "sourceManifest": { }, "spec": { }
  },
  "compatibility": {"range": ">=2.0.0 <3.0.0", "satisfied": true},
  "bindingSource": "registry",
  "intent": {"repo": "...", "path": "...", "gitSha": "..."},
  "rollbackOf": null,
  "createdAt": "...", "createdBy": "..."
}
```

This is the object `docs/agent-platform-registry.md` freezes as the
consumer contract for `orchestrator/resolver.py`: the fields it copies into
the `ExecutionPlan` are `agent`, `environment`, `revision`,
`definition.version`, `profile.name`, `profile.version` and
`definition.sourceManifest.gitSha`.

Because `writeError` only emits `{"error": ...}`, a sibling helper
`writeErrorCode(w, status, code, message, details)` is added in
`internal/api/handlers_read.go` next to it, emitting
`{"error", "code", "details"}`. `writeError` is untouched, so no existing
response body changes. Codes: `incompatible_profile`, `version_deprecated`,
`version_disabled`, `version_not_found`, `fixture_not_promotable`,
`missing_policy_fields`, `invalid_range`, `invalid_lifecycle_transition`.

### Execution identity

`recordExecutionRequest` (handlers_agent_registry.go:65) gains optional
`definition_version`, `profile`, `profile_version`, `binding_revision`
fields; `AgentExecution` and `RecordExecution` gain the matching columns.
All default to empty/NULL, so the existing
`orchestrator/temporal/activities/state.py` caller keeps working unchanged
until mctl-agents starts sending them. `ListExecutions` returns them, which
is how "resolved versions appear in execution identity, not only in registry
rows" is verifiable from mctl-api's side; the trace attributes themselves
stay mctl-agents#196's job.

### MCP surface

Seven new tools registered in the `// Agent registry` block of
`internal/mcp/server.go:169-176`:

| Tool | Route | Hints |
| --- | --- | --- |
| `mctl_publish_agent_definition_version` | POST definition-versions | mutating, non-destructive, non-idempotent |
| `mctl_publish_agent_profile_version` | POST profile versions | mutating, non-destructive, non-idempotent |
| `mctl_set_agent_version_lifecycle` | POST .../lifecycle | mutating, destructive, non-idempotent, `confirm` |
| `mctl_bind_agent_release` | POST bindings | mutating, destructive, non-idempotent, `confirm` |
| `mctl_rollback_agent_binding` | POST bindings/rollback | mutating, destructive, non-idempotent, `confirm` |
| `mctl_list_agents` | GET /agents | read-only |
| `mctl_get_agent` | GET /agents/{name} | read-only |

`mctl_resolve_agent` is **extended**, not duplicated: an optional
`api_version` argument (enum `v1`, `v1alpha2`, default `v1`) selects between
`/resolve?environment=` and `/bindings/resolve?...`, plus optional
`definition_version` / `profile_version` for the explicit pin. An existing
caller that passes only `agent_name` + `environment` sees byte-identical
behaviour. The `confirm` gate copies `requireConfirm` as used by
`toolPromoteAgent` / `toolRollbackAgent`.

Three test contracts must be updated in the same PR: the tool count at
`server_test.go:173` (74 -> 81), `recordedHints` and the pinned read-only set
in `annotations_test.go` (add `mctl_list_agents`, `mctl_get_agent`), and
`docs/portal-allowlist.json` (every new tool gets an explicit entry; all seven
default to `enabled: false`, matching `mctl_create_agent` and the rest of the
registry family, which the portal does not expose).

### GitOps reconciliation contract

Push, not pull: a merged, reviewed PR in `mctl-gitops` whose
`ReleaseBindingIntent` carries `bindingSource: registry` and
`promotable: true` triggers that repo's CI to call
`POST /api/v1/agents/{name}/bindings` with the intent's file path, repo and
merge SHA in the `intent` block. mctl-api stays the authority for what is
active; gitops is the review gate. mctl-api enforces the other half by
rejecting `bindingSource: compatibility-fixture` at bind time, so the two
validators cannot drift into disagreeing. `docs/agent-platform-registry.md`
writes this down, including the payload mapping from intent YAML to request
JSON; the `scripts/validate-agent-platform.py` and README change is the
follow-up PR in mctl-gitops.

### Seeding `issue-investigator`

`scripts/seed-agent-platform.sh` (next to the existing
`scripts/portal-allowlist-apply.sh`) publishes a definition version and a
profile version for `issue-investigator` from JSON files and binds them in
`shadow`. `shadow`, not `production`: the live dev-loop pipeline resolves
`production`, and the resolver is still in `legacy` mode, so a shadow binding
gives mctl-agents something real to resolve against with zero blast radius.

## Alternatives

**A new `internal/agentplatform` package with its own store and pool.**
Cleaner separation of the v1 and v1alpha2 models, and no risk of touching
`promote`. Dropped: it is the "second release database" both ADR 007's
lifecycle-authority table and the mctl-gitops#950 non-goals forbid, it would
duplicate `agent_definitions` as a parent, it doubles the Postgres pool for
one logical registry, and `mctl_get_agent` would have to join across two
stores to answer one question.

**Overload the existing `agent_versions` / `agent_releases` tables with
nullable v1alpha2 columns.** Smallest schema footprint, one publish endpoint.
Dropped: `agent_releases` is PK'd on `(agent, environment)` and mutated in
place, which is structurally incompatible with an append-only ledger where
`active` is derived; exact-revision rollback has nothing to point at; and
every v1 invariant (`image_repository` bare-repo rule, one version per
release) would become conditionally-applicable, which is how the doubled-tag
incident behind `isBareImageRepository` happens again.

**Adopt `github.com/Masterminds/semver/v3` for range evaluation.** Correct,
complete, battle-tested. Dropped for now: this repo keeps a deliberately thin
direct-dependency list (17 direct modules, no semver library, not even
`golang.org/x/mod`), and the range grammar actually used by ADR 007 is not yet
confirmed. A ~120-line evaluator with an explicit reject-on-unknown-syntax
rule is easy to delete in favour of the library later; the reverse (loosening
a permissive library's behaviour after bindings exist) is not. Recorded as an
open question in requirements.md.

**Pull-based gitops reconciliation (mctl-api watches the catalog).**
Attractive because it keeps the registry self-healing. Dropped:
`internal/gitops/reader.go` is a read-only clone-and-parse path with no
webhook or poll loop for `platform-gitops/agent-platform/`, mctl-api has no
write credential to record reconciliation results back, and the reviewed-PR
merge is already the human gate ADR 007 wants to be the trigger.

## Platform impact

**Migrations.** Three `CREATE TABLE IF NOT EXISTS` and four
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` appended to `agentRegistrySchema`,
applied at startup by `NewStore`, matching the alerts/audit precedent. All
new columns have defaults, so the ALTERs are metadata-only on Postgres 11+
and do not rewrite `agent_executions`. No data backfill: v1 rows keep meaning
exactly what they mean.

**Backward compatibility.** No existing route, request field, response field,
store method signature or MCP tool argument changes. `mctl_resolve_agent`
gains an optional argument whose default reproduces today's behaviour.
`orchestrator/temporal/activities/registry.py` and `state.py` keep working
untouched. An agent with no v1alpha2 definition version simply has empty
v1alpha2 sections in `mctl_get_agent`.

**Resource impact.** A handful of small tables and one extra index; the
registry database is already provisioned and shares `AUDIT_DB_URL` by
default. Resolve is a single indexed `ORDER BY revision DESC LIMIT 1` plus
two version lookups; it is called once per workflow step, not per request.
`spec_json` blobs are JSONB and bounded by the size of a definition/profile
manifest.

**Risks and mitigations.**

- *Concurrent binds producing duplicate or gapped revisions.* Mitigated by
  the same per-`(agent, environment)` advisory lock `promote` already uses,
  plus `UNIQUE(agent, environment, revision)`; covered by a concurrency test.
- *Compatibility evaluator disagreeing with mctl-gitops'
  `validate-agent-platform.py`.* Two implementations of one grammar is real
  drift risk. Mitigated by rejecting unparseable ranges at publish time
  (fail closed), by freezing the supported grammar in
  `docs/agent-platform-registry.md`, and by a table-driven test whose cases
  are copied into the gitops follow-up PR.
- *Registry and gitops disagreeing about what is active.* Mitigated by making
  the registry authoritative in the doc and storing the `intent` repo/path/SHA
  on every binding, so any binding can be traced to the merge that caused it.
- *MCP tool-count creep.* Seven new tools push the server to 81; the pinned
  count, annotation record and portal allowlist all fail the build if the PR
  forgets one, which is the intended forcing function.
- *Accidentally binding to `production` while the resolver is in legacy mode.*
  Mitigated by seeding `shadow` only and by the `confirm` gate on
  `mctl_bind_agent_release`.
- *A disabled version being restored by rollback.* Mitigated by re-running
  the full lifecycle and compatibility validation inside the rollback
  transaction rather than blindly copying the target row.
