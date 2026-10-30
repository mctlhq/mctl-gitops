# Design: issue-748-feat-mcp-read-only-agent-asset-index-and

## Current state

Registry (PostgreSQL), `internal/agentregistry`
- `v1alpha2_types.go`: `DefinitionVersion`, `ProfileVersion` (`SpecJSON` is opaque JSON), `ReleaseBinding`, `ResolvedBinding` with `Definition`, `Profile` (lifecycle, spec), and `Compatibility`.
- Errors: `ErrBindingNotFound`, `ErrDefinitionVersionNotFound`, `ErrProfileVersionNotFound` (v1alpha2), and `ErrDefinitionNotFound` (`store.go:34`).
- `RequiredProfilePolicyFields` (`:95`) is `maxTokens/maxToolCalls/timeoutSeconds`. That is not the gitops profile schema, so a DB profile spec may not carry every field the checks need.
- `v1alpha2_store.go`: `ResolveBinding` (`:716`), `ResolveExplicit` (`:757`) and `ListCatalog` (`:900`). `CreateBinding` refuses deprecated or disabled versions (`:401`); rollback may restore a deprecated one (`:416`, `:627`).

API
- `internal/api/router.go:126`: `Options.AgentRegistry *agentregistry.Store` is a concrete type, nil when no DB.
- `router.go:58`: `GitReader GitReader` is an interface, in `interfaces.go:37`, with `ListPlatformSkills`, `GetPlatformPolicy` and so on. Fakes implementing it live in `internal/api/smoke_test.go` and `build_repo_gate_internal_test.go`.
- `handlers_agent_platform.go`: `ResolveBinding` (around `:517`) holds the selector rules (environment XOR definition_version+profile, both pin halves required) and `writeAgentPlatformError`.
- `handlers_agent_registry.go:97`: `requireAgentRegistryAdmin`.
- v1alpha2 routes are registered at `router.go:580-601`. Static segments win over dynamic ones in chi's radix tree, as noted for `/agents/executions` and `bindings/resolve`.
- Postgres-backed handler tests use `newTestAgentPlatformStore` (`handlers_agent_platform_test.go:35`) and skip without `TEST_DATABASE_URL`.

GitOps reader, `internal/gitops/reader.go`
- A full shallow clone (`git clone --depth=1`, `:459`) at `GITOPS_LOCAL_PATH` (default `/tmp/mctl-gitops`, `cmd/api/main.go:1449`). It is not sparse, so `platform-gitops/agent-platform/**` is on disk.
- `ReadFiles` (`:1200`) reads top-level files under `RLock` with `revisionLocked()` and refuses non-regular files.
- `ComponentSourceRepo` fails closed on a parse error.
- `ListPlatformSkills` (`:1288`) reads under `RLock` and errors on a malformed skill, but returns no revision.
- There is no accessor for `agent-platform/` yet.

MCP, `internal/mcp`
- `server.go:339` registers `toolResolveAgent` (`:3215`), a thin forwarder using `s.apiGet` (`:2421`) with `WithReadOnlyHintAnnotation(true)`.
- `annotations_test.go` pins annotations per tool (`:81`, `:102`) and keeps a read-only list (`:253-260`).
- `docs/portal-allowlist.json` lists every tool; `mctl_list_agents` is `enabled: false` (`:238`).
- `commerce_test.go:35` has the table-of-paths forwarder test.

Gitops data on disk (`$MCTL_GITOPS_ROOT/agent-platform/`)
- `execution-profiles/<name>/profile.yaml`: 7 profiles (`authoring-canary`, `implementer`, `incident-responder`, `issue-investigator`, `mentor`, `service-agent`, `shepherd`, each `-default`). They have `kind: ExecutionProfile` and these spec fields: `version`, `modelPolicyRef.{task,compatibility}`, `skills`, `tools`, `policyRef`, `permissions.mutationScopes`, `budgetUsd`, `timeoutSeconds`, `runtime.sandbox.{backend,clusterWorkflowTemplate,approved}`, `approval.requiredBefore`, `evidence.required`, `capabilityDiscovery.{enabled,providers[].{type,id,alias,endpoint}}`.
- `policy.yaml`: `kind: AgentPlatformPolicy`, with `spec.limits.{maxBudgetUsd: 25, maxTimeoutSeconds: 7200}`, `knownTools[].name`, `knownSkills`, `knownModelPolicyTasks`, `knownPolicies`, `uncalledProfiles`, `knownMutationScopes[].{name,mutating,requiresApproval}`, `knownApprovalGates`, `approvedSandboxes[].{backend,clusterWorkflowTemplates}` and `knownEvidenceKinds`.
- `releases/shadow/*.yaml` only: `kind: ReleaseBindingIntent` with `metadata.{agent,environment}`, `spec.definition.{name,version}`, `spec.profile.{name,version}`, `bindingSource: compatibility-fixture`, `promotable: false` and `registryLifecycle`. There is no `releases/production/`.
- `mctl-gitops/scripts/validate-agent-platform.py` (866 lines): the issue's line citations were checked against it. `:210/214/217/221` are the unknown tool/skill/policyRef/task rules, `:240-253` capability discovery, `:260` evidence, `:263/267` ceilings, `:276/278` sandbox, `:287/293/297` approval gates and scopes, and `:648` compatibility.

Deployed state checked:
- `mctl_resolve_agent(issue-investigator, api_version=v1alpha2, environment=production)` returned the error `agentregistry: no binding for agent/environment: issue-investigator/production`. No v1alpha2 production binding exists.
- `mctl_get_agent(issue-investigator)`: `definitionVersions` null and `activeBindings` `{}`. Only v1 versions exist. The DB has no v1alpha2 rows for this agent, as the issue expected.
- `$MCTL_GITOPS_ROOT/agent-platform/` was listed and read as summarised above. Only `releases/shadow/` exists.
- `mctl_get_service_config(admin, mctl-api)` returned "service not found". A search of `platform-gitops/services/*/mctl-api` found nothing. The mctl-api deployment config (env, replicas, `GITOPS_LOCAL_PATH`) was **not observed**. It is assumed to use the clone default from `cmd/api/main.go`; see requirements.md, Open questions.

## Proposed solution

### 1. Reader: `internal/gitops/agent_platform.go` (new file in package gitops, methods on `*Reader`)

Types parse only what the checks and index need. Each also keeps `Raw map[string]any` so the index can show the full spec.

```go
type AgentPlatformProfile struct { Name, Dir, Path string; Spec ExecutionProfileSpec; Raw map[string]any }
type ExecutionProfileSpec struct {
    Version string; ModelPolicyRef struct{ Task, Compatibility string }
    Skills, Tools []string; PolicyRef string
    Permissions struct{ MutationScopes []string }
    BudgetUsd *float64; TimeoutSeconds *int
    Runtime struct{ Sandbox struct{ Backend, ClusterWorkflowTemplate string; Approved *bool } }
    Approval struct{ RequiredBefore []string }; Evidence struct{ Required []string }
    CapabilityDiscovery *struct{ Enabled *bool; Providers []struct{ Type, ID, Alias, Endpoint string } }
}
type AgentPlatformPolicy struct { Limits{MaxBudgetUsd *float64; MaxTimeoutSeconds *int}; KnownTools, KnownSkills, KnownModelPolicyTasks, KnownPolicies, KnownApprovalGates, KnownEvidenceKinds []string; KnownMutationScopes []MutationScope; ApprovedSandboxes map[string][]string }
type AgentPlatformRelease struct { Agent, Environment, Path string; Definition, Profile struct{ Name, Version string }; BindingSource string; Promotable *bool; RegistryLifecycle map[string]string }
```

- Pointers mark "absent" (not zero), so a missing `budgetUsd` becomes `unknown`, never a pass against 0. JSON and YAML tags match the camelCase on disk; `json` tags let the same struct decode a registry `SpecJSON`.
- `ListAgentPlatformProfiles() ([]AgentPlatformProfile, string, error)`, `GetAgentPlatformPolicy() (*AgentPlatformPolicy, string, error)` and `ListAgentPlatformReleases() ([]AgentPlatformRelease, string, error)`. Each takes `r.mu.RLock()`, calls `revisionLocked()` (an unsynced checkout is an error), and delegates to a `...Locked` helper.
- `ReadAgentPlatformSnapshot() (*AgentPlatformSnapshot, error)` takes the lock once and fills profiles, policy, releases and platform skills (through the existing `readPlatformSkillLocked`). Each part carries its own `Err error`, and all parts share one `Revision`. Handlers use this, so the whole index is one checkout and one source failing does not mask the others. This is what the "per-source ok/unavailable" response needs; the three single-purpose methods stay as the issue asked.
- Fail-closed rules, the same as `ComponentSourceRepo` and `ReadFiles`:
  - `os.Lstat` on every file, and a non-regular file is an error.
  - A YAML parse error is `fmt.Errorf("parsing %s: %w", rel, err)`.
  - The wrong `kind` (`ExecutionProfile`, `AgentPlatformPolicy`, `ReleaseBindingIntent`) is an error.
  - A duplicate `metadata.name` across profiles is an error.
  - A missing `agent-platform/` or sub-directory in a synced checkout is an empty list, or for policy `ErrAgentPlatformPolicyNotFound`, reported as `unavailable: not present at <rev>`.
- `GitReader` in `internal/api/interfaces.go` gains `ReadAgentPlatformSnapshot()`. The two test fakes get stub methods.

### 2. Checks: `internal/api/agent_preflight.go` (pure functions, no I/O)

`func evaluatePreflight(spec *gitops.ExecutionProfileSpec, specErr error, policy *gitops.AgentPlatformPolicy, policyErr error, reg *registryFacts) []PreflightCheck` and `func verdict([]PreflightCheck) string`.

- `PreflightCheck{ID, Status, Detail, Source string}`. The status constants are `pass`, `fail` and `unknown`.
- Sources are constants in one table, `ruleSources`: `"profile.budget": "validate-agent-platform.py:263"` and so on, with `"agentregistry"` for `binding.lifecycle`. This keeps drift visible in one place.
- Each check follows the Python rule for its line, as listed in requirements.md. Any missing input (policy unreadable, field absent, wrong type) gives `unknown` with a reason naming the field. There is no code path from an error to `pass`.
- `profile.capability_discovery` hardcodes provider id `mctl-api` and alias `mctl` (Python `MCTL_API_PROVIDER_ID`/`MCTL_API_REQUIRED_ALIAS`), citing `:240-253`.
- `verdict`: any `fail` gives `fail`; otherwise any `unknown` (or an empty check list) gives `unknown`; otherwise `pass`.

### 3. REST: `internal/api/handlers_agent_assets.go`

`GET /api/v1/agent-assets`, method `ListAgentAssets`
1. `requireAgentRegistryAdmin`. If both `AgentRegistry` and `GitReader` are nil, return 503.
2. Registry: `ListCatalog(ctx)`, or `unavailable` (nil store gives "agent registry not configured"; an error gives `err.Error()`).
3. GitOps: `ReadAgentPlatformSnapshot()`; each part sets its own source status.
4. Build `refs`: `profiles[name] -> {tools, skills, modelPolicyTask, capabilityProviders, policyRef}`, plus the inverse maps `skills`, `tools`, `policyRefs` and `modelPolicyTasks` (each value to a sorted profile list). Registry profile specs from the catalog are included when the catalog exposes a spec; otherwise only gitops profiles are reverse-indexed, and the response says so with `refs_scope: "gitops"`. Inverse maps are built only from sources with status `ok`.
5. Response:

```json
{ "gitops_revision": "...", "sources": {"registry": {"status":"ok"}, "gitops_policy": {"status":"unavailable","reason":"..."}, ...},
  "registry": {...}|null, "profiles": [...]|null, "releases": [...]|null, "policy": {...}|null, "skills": [...]|null, "refs": {...} }
```

`GET /api/v1/agents/{name}/preflight`, method `PreflightAgent`
1. Admin check. Selector parsing is factored out of `ResolveBinding` into `parseBindingSelector(r) (sel, errMsg)` so both handlers return identical 400s. `ResolveBinding` is refactored to call it, with its behaviour unchanged and pinned by the existing tests.
2. Resolve. If the store is non-nil, call `ResolveBinding` or `ResolveExplicit`.
   - On success: `source: agentregistry`, the spec decoded from `Profile.Spec` (JSON), and `registryFacts{defLifecycle, profLifecycle, compatibility}`.
   - On a "not found" class error (`ErrBindingNotFound`, `ErrDefinitionNotFound`, `ErrDefinitionVersionNotFound` or `ErrProfileVersionNotFound`): fall back to gitops.
   - On any other error: the `binding.*` checks are `unknown` with the error, profile checks run from gitops, and `registry_error` is set in the response.
3. GitOps fallback (`source: gitops`):
   - With an environment: the release intent `releases/<env>/<agent>.yaml` (`selection: release-intent`). If there is none, `<agent>-default` (`selection: naming-convention`).
   - With an explicit pin: profile `profile` (`selection: explicit`).
   - If the profile's `spec.version` differs from the intent's or pin's `profile.version`, `binding.compatibility` is `unknown` with the mismatch.
   - `binding.lifecycle` comes from the intent's `registryLifecycle` when present (detail: "from compatibility-fixture intent, not the registry"); otherwise `unknown`.
   - If no profile is found anywhere, return 404 via `writeError`.
4. Response:

```json
{"agent", "environment"?, "source", "selection"?, "definition": {"version"}, "profile": {"name","version"}, "gitops_revision", "sources", "checks": [...], "verdict"}
```

Routes are added in `router.go` next to the v1alpha2 block:

```go
r.Get("/agent-assets", h.ListAgentAssets)
r.Get("/agents/{name}/preflight", h.PreflightAgent)
```

`/agents/{name}/preflight` is three segments and collides with no existing route. The existing `router_test.go` pin gets one more case.

### 4. MCP (`internal/mcp/server.go`, registered after `toolResolveAgent` around `:339`)

- `toolListAgentAssets`: `mctl_list_agent_assets`, no arguments, `s.apiGet(ctx, "/api/v1/agent-assets")`.
- `toolPreflightAgent`: `mctl_preflight_agent`.
  - `agent_name` is required. The optional arguments are `environment` (enum `agentRegistryEnvironmentEnum`), `definition_version`, `profile` and `profile_version`.
  - It builds `url.Values` the same way as `toolResolveAgent`, with `url.PathEscape(agent)`.
  - The server does the selector validation, so the MCP and REST errors cannot drift.
- Both tools use `WithTitleAnnotation`, `WithReadOnlyHintAnnotation(true)` and `WithDestructiveHintAnnotation(false)`. Descriptions state: admin-only, no eligibility semantics, Python CI stays authoritative, and `unknown` is never `pass`.
- Receipt-gate classification (`agent_receipt_gate.go`, mctl-api#723): `TestAgentReceiptGate_ClassifiesEveryTool` (`agent_receipt_gate_test.go:222`) requires each tool to be exactly one of governed, ungoverned or read.
  - `mctl_list_agent_assets` is already a read by its `list_` prefix (`isAgentReadTool`, `:242`), so it is not added to any list.
  - `mctl_preflight_agent` matches no read prefix. It is added to `ungovernedAgentTools` next to `mctl_resolve_agent` (`:165`), the existing precedent for a read-only resolve-style tool without a read verb.
  - Side effect: mctl-agents' in-process policy checkpoint passes only get/list/read/search/describe calls, so agent runs may not be able to call `mctl_preflight_agent` until mctl-agents allows it. Human and admin MCP use is unaffected. See requirements.md, Open questions.
- Update the tool-count expectation in `server_test.go` (CLAUDE.md), `annotations_test.go` and `docs/portal-allowlist.json` (`enabled: false`, with a reason modelled on `mctl_list_agents`).

### Invariants kept
- Nothing is written: no DB writes, no gitops commits, no new tables.
- The index carries no eligibility fields. Preflight answers "would CI-equivalent rules pass", not "is it allowed". The runtime order (catalog, then ExecutionProfile eligibility, then sealed CapabilitySet, then PolicyCheckpoint) is untouched, and mctl-agents does not read these endpoints.

## Alternatives

1. **Shell out to `validate-agent-platform.py` from mctl-api.** This would remove the drift risk, but it adds a Python runtime to the mctl-api image. The script validates the whole repo rather than a selected profile, it cannot evaluate a registry-resolved spec, and running code from a git checkout inside the API process is a security and supply-chain concern. Dropped.
2. **Make `ExecutionProfile` checks part of `agentregistry` (validate at publish).** That turns a read-only diagnostic into an eligibility gate and changes the publish contract (`RequiredProfilePolicyFields`), which the issue puts out of scope. Dropped for slice 1.
3. **Three independent reader calls per request, no snapshot.** These are simpler, but a refresh between calls could mix revisions under one `gitops_revision`. The snapshot holds the lock once, at the cost of one extra method. Kept the snapshot, with the three public methods as wrappers.
4. **Fail the whole index on any unreadable source.** This is fail-closed, but it hides the readable data and makes the tool useless while the DB is empty or down. The issue explicitly asks for per-source status. Dropped.

## Platform impact

- **Migrations:** none. No schema change, no new env var, no Helm change.
- **Backward compatibility:** two new routes and two new MCP tools are additive. `ResolveBinding` gets a pure refactor (`parseBindingSelector`), guarded by its existing tests. The `GitReader` interface gains one method; only in-repo fakes implement it.
- **Resources:** each call reads about 10 small YAML files plus the skills catalog under the read lock (milliseconds), and makes one or two registry queries. Calls are admin-only and rare. There is no cache, so there is nothing to go stale beyond the checkout itself.
- **Risks and mitigations:**
  - *Go/Python drift:* every check cites its Python line in `source`, and the rule table is one constant map. A note in the code points at the script.
  - *Lock contention with refresh:* the read lock is held only for file reads, as `ListPlatformSkills` already does.
  - *Over-trust:* the response and tool descriptions state that it carries no eligibility. Production currently returns `unknown`, not `pass`, because there is no binding.
  - *Information exposure:* admin-only, and the tools are disabled on the shared portal.
  - *A DB spec shape that differs from gitops:* missing fields give `unknown`, never `pass`.
