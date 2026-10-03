# Publish and resolve v1alpha2 AgentDefinition + ExecutionProfile ReleaseBindings in the mctl-api registry

## Context

ADR 007 splits the agent-platform model into three layers: a canonical
`AgentDefinition` owned in `mctl-agents` Git, reviewed `ExecutionProfile`
drafts and `ReleaseBindingIntent` fixtures owned in `mctl-gitops` Git, and
immutable published versions plus per-environment `ReleaseBinding` history
owned by the mctl-api registry. The first two layers shipped
(mctl-agents#227, mctl-gitops#950). The third does not exist: today's
registry — `internal/agentregistry/store.go`, `internal/api/handlers_agent_registry.go`
and the `mctl_publish_agent_version` / `mctl_promote_agent` /
`mctl_resolve_agent` / `mctl_rollback_agent` MCP tools in
`internal/mcp/server.go` — versions a single agent image/release
(`agent_versions.image_repository` + `agent_releases.version`). It has no
notion of a definition version, an execution-profile version, a
compatibility range between them, or an atomic pair per environment, so it
cannot back `agents.mctl.ai/v1alpha2`.

Both downstream tracks are explicitly blocked on this layer:
`mctl-agents/orchestrator/resolver.py` refuses a `bindingSource: registry`
intent and keeps `ISSUE_INVESTIGATOR_RESOLVER_MODE=legacy`, and every
`ReleaseBindingIntent` in `platform-gitops/agent-platform/` is pinned to
`bindingSource: compatibility-fixture` / `promotable: false` because there
is nothing to reconcile into. This proposal extends the existing registry
in place — same Postgres pool, same package, same admin-gated REST +
MCP surfaces — rather than standing up a second release database, and
keeps every v1 image/release path byte-compatible for agents that have not
migrated.

## User stories

- AS a platform operator I WANT to publish an immutable `AgentDefinition`
  version with its source manifest provenance SO THAT every later execution
  can be traced back to an exact repo/path/gitSha/contentHash.
- AS a platform operator I WANT to publish an immutable `ExecutionProfile`
  version with its policy ceilings SO THAT runtime limits are versioned and
  reviewable instead of implicit in a CWFT.
- AS a platform operator I WANT to bind a compatible definition+profile pair
  to an environment as one append-only revision SO THAT "what is active"
  is a single atomic fact with full history.
- AS a release engineer I WANT publishing an incompatible, `deprecated` or
  `disabled` pair to fail with an actionable error SO THAT a bad binding
  never reaches an environment.
- AS a release engineer I WANT to roll back to an exact prior binding
  revision SO THAT recovery does not depend on guessing which pair was live.
- AS `mctl-agents` `orchestrator/resolver.py` I WANT a documented resolve
  response for `(agent, environment)` and for an explicit `name+version`
  pin SO THAT a `bindingSource: registry` intent resolves instead of being
  refused, and the resolved tuple can be recorded in the `ExecutionPlan`.
- AS a gitops reviewer I WANT a documented path where merging a
  `promotable: true`, `bindingSource: registry` intent drives a registry
  publish SO THAT the catalog stops being a fixture-only stand-in.
- AS an operator or agent I WANT `mctl_list_agents` / `mctl_get_agent` SO
  THAT I can read the catalog — owner, versions, lifecycle, active binding
  per environment — without querying Postgres by hand.

## Acceptance criteria (EARS)

Publishing versions

- WHEN an admin POSTs a definition version for an agent that already has an
  `agent_definitions` row THE SYSTEM SHALL store an immutable record holding
  the version, the full definition spec as JSON, `sourceManifest`
  (`repo`, `path`, `gitSha`, `contentHash`), the declared execution-profile
  compatibility range, the owner, and `lifecycle = published`, and return 201.
- WHEN an admin POSTs a definition version whose `(agent, version)` already
  exists THE SYSTEM SHALL reject it with 409 and change nothing.
- IF a definition version is POSTed without an owner, without a
  `sourceManifest.gitSha`, without a `sourceManifest.contentHash`, or without
  a parseable compatibility range THEN THE SYSTEM SHALL reject it with 400
  naming the specific missing or unparseable field.
- WHEN an admin POSTs an execution-profile version THE SYSTEM SHALL store an
  immutable record holding the profile name, version, the full profile spec
  as JSON, its source manifest provenance, the required policy ceiling
  fields, and `lifecycle = published`, and return 201.
- IF an execution-profile version is POSTed missing any required policy
  ceiling field THEN THE SYSTEM SHALL reject it with 400 listing every
  missing field in one response.
- WHEN an admin transitions a published definition or profile version to
  `deprecated` or `disabled` THE SYSTEM SHALL record the new lifecycle state,
  the actor and the reason, and SHALL leave the immutable spec untouched.
- IF a lifecycle transition is not one of `published -> deprecated`,
  `published -> disabled` or `deprecated -> disabled` THEN THE SYSTEM SHALL
  reject it with 409.

Creating bindings

- WHEN an admin creates a `ReleaseBinding` for `(agent, environment)` naming
  a published definition version and a published profile version whose
  version satisfies the definition's declared compatibility range THE SYSTEM
  SHALL append a new binding revision (monotonic per agent+environment)
  recording both exact versions, the resolved compatibility range,
  `bindingSource`, the intent reference when supplied, the actor, the reason
  and the creation time, and return 201 with the new revision.
- WHILE a binding revision exists THE SYSTEM SHALL never update or delete it;
  every change SHALL be a new appended revision.
- WHILE `(agent, environment)` has at least one binding revision THE SYSTEM
  SHALL derive the active binding as the highest revision and SHALL NOT
  store an `active` flag anywhere.
- IF the profile version does not satisfy the definition's compatibility
  range THEN THE SYSTEM SHALL reject the binding with 422, an
  `incompatible_profile` error code, and a body naming the definition
  version, the declared range and the offending profile version.
- IF either named version is `deprecated` or `disabled` THEN THE SYSTEM SHALL
  reject the binding with 422 and an error code of `version_deprecated` or
  `version_disabled`, naming which side failed.
- IF either named version does not exist THEN THE SYSTEM SHALL reject the
  binding with 404 naming the missing `name@version`.
- IF a binding is requested with `binding_source = compatibility-fixture`
  THEN THE SYSTEM SHALL reject it with 422 and an error explaining that
  fixture intents are non-promotable and that `registry` is the promotable
  source.
- IF `environment` is not one of the registry's known environments THEN THE
  SYSTEM SHALL reject the binding with 400, reusing
  `agentregistry.ErrInvalidEnvironment`.
- WHILE two binding creations for the same `(agent, environment)` run
  concurrently THE SYSTEM SHALL serialize them so that revision numbers stay
  gapless and no two revisions share a number.

Resolving and rolling back

- WHEN a caller resolves `(agent, environment)` THE SYSTEM SHALL return the
  active binding revision including both exact versions, both source
  manifests, the profile's policy ceilings, `bindingSource`, the revision
  number and `rollbackOf` linkage.
- WHEN a caller resolves an explicit definition `name+version` (optionally
  with an explicit profile version) THE SYSTEM SHALL return the same resolve
  envelope for that exact pin without consulting any environment.
- IF no binding revision exists for `(agent, environment)` THEN THE SYSTEM
  SHALL return 404 with an error distinguishing "agent unknown" from
  "agent known, no binding in this environment".
- WHEN an admin rolls back `(agent, environment)` to an exact prior revision
  THE SYSTEM SHALL append a new revision that copies that revision's
  definition/profile pair and sets `rollbackOf` to the revision it restored.
- IF a rollback names a revision that does not belong to that
  `(agent, environment)` THEN THE SYSTEM SHALL reject it with 404 and append
  nothing.
- WHEN a rollback target's definition or profile version has since become
  `disabled` THE SYSTEM SHALL reject the rollback with 422 rather than
  restoring a disabled pair.

Catalog, execution identity and compatibility

- WHEN a caller invokes `mctl_list_agents` THE SYSTEM SHALL return every
  registered agent with its owner, its definition- and profile-version
  counts, and its active binding per environment.
- WHEN a caller invokes `mctl_get_agent` THE SYSTEM SHALL return one agent's
  full catalog entry: owner, every definition version and profile version
  with per-version lifecycle state, and the active binding per environment.
- WHEN a DevLoopWorkflow records an execution THE SYSTEM SHALL accept and
  persist the resolved definition version, profile name, profile version and
  binding revision alongside the existing image/version fields, and SHALL
  return them from the executions list endpoint.
- WHILE an agent has no v1alpha2 definition version published THE SYSTEM
  SHALL keep `POST /api/v1/agents/{name}/versions`,
  `POST /api/v1/agents/{name}/releases` and
  `GET /api/v1/agents/{name}/resolve?environment=` behaving exactly as they
  do today, with unchanged request and response shapes.
- WHEN the registry starts against a database created before this change
  THE SYSTEM SHALL create the new tables and columns idempotently at
  startup without operator action and without touching existing rows.
- WHEN `issue-investigator` has been seeded THE SYSTEM SHALL expose a real
  published v1alpha2 definition+profile pair and one binding in at least the
  `shadow` environment.

## Out of scope

- `mctl_propose_agent`, `mctl_deprecate_agent` and other governed mutation
  operations (later Phase 3, depends on mctl-agents#242).
- Registry / operations UI in mctl-portal (Phase 4).
- Flipping `ISSUE_INVESTIGATOR_RESOLVER_MODE` to `declarative`, or migrating
  `implementer` / `shepherd` — separate mctl-agents issues.
- The mctl-gitops-side validator/README change making `bindingSource: registry`
  with `promotable: true` the supported path: this proposal only defines and
  documents the contract mctl-api enforces; the gitops PR is a follow-up.
- Producing the `ExecutionPlan` / trace attributes themselves (mctl-agents#196
  owns that); mctl-api only accepts, stores and returns the resolved tuple.
- Capability discovery / MCP gateway.
- Replacing Temporal, Argo, or the existing Postgres-backed registry;
  no second release database is introduced.
- Weighted/canary traffic splitting between two bindings.

## Open questions

- The exact required policy-ceiling field names on an `ExecutionProfile` come
  from the mctl-gitops#950 schemas, which are not visible from this clone.
  Proceeding with a single named constant
  (`agentregistry.RequiredProfilePolicyFields`) validated against the stored
  profile spec so the set can be corrected in one place when the schema is
  read during implementation.
- The compatibility-range grammar ADR 007 uses is unverified here. Proceeding
  with a strict subset — space/comma separated `>=`, `>`, `<=`, `<`, `=`
  comparators plus `^` and `~` over `MAJOR.MINOR.PATCH` — and rejecting
  anything else at publish time with a 400 rather than silently accepting a
  range that cannot be evaluated.
- Whether `ExecutionProfile` names are global or namespaced per agent. Taking
  them as global (`profile_name` is its own key space), which matches three
  shared profiles in `platform-gitops/agent-platform/`; a per-agent namespace
  can be layered on later without breaking stored rows.
- Whether gitops reconciliation should be push (mctl-gitops CI calls the API
  on merge) or pull (mctl-api polls the catalog). Proceeding with push,
  because mctl-api has no gitops write credential and `internal/gitops/reader.go`
  is read-only.
- The registry currently accepts only `production` and `shadow`
  (`agentregistry.EnvironmentProduction` / `EnvironmentShadow`). Keeping that
  set unchanged and seeding `issue-investigator` into `shadow`.
- Whether `mctl_list_agents` / `mctl_get_agent` should stay admin-only like
  the rest of the registry. Keeping admin-only for consistency with
  `requireAgentRegistryAdmin`; relaxing it is a separate policy decision.
