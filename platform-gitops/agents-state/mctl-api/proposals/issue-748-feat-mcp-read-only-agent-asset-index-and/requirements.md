# Read-only agent asset index and preflight (REST + MCP), slice 1

## Context

Agent definitions, execution profiles, the agent-platform policy, release intents and platform skills each live in their own place. Some are in the mctl-api agent registry (PostgreSQL, `internal/agentregistry`). Others are in the mctl-gitops checkout that mctl-api already holds (`platform-gitops/agent-platform/...`, `platform-gitops/platform-skills/catalog/`). No view lists them together. Nothing answers reverse questions such as "which profiles reference skill Z, tool X or policyRef P". Nothing tells an operator whether agent X with profile Y would pass the platform's rules in environment Z without opening a PR (CI) or starting a run. The rules already exist in `mctl-gitops/scripts/validate-agent-platform.py`; they are just not put together anywhere.

This proposal adds two admin-only, read-only REST endpoints and two MCP forwarders. `GET /api/v1/agent-assets` is a merged index with reverse references. `GET /api/v1/agents/{name}/preflight` runs a per-check report against the resolved profile. Both read only the registry DB and the existing gitops clone. Neither creates writable state, grants anything, or replaces the Python CI validators: each check names the CI rule it mirrors so any drift between the Go and Python checks is visible.

## User stories

- AS a platform admin I WANT one index of agents, profiles, release intents, policy catalogs and skills with reverse references SO THAT I can see the impact of a change (for example removing a skill or a policyRef) before making it.
- AS a platform admin I WANT a preflight report for an (agent, environment) or an explicit (definition, profile) pin SO THAT I learn whether it would pass the platform rules without committing files or starting a run.
- AS an MCP client (Claude, an agent) I WANT `mctl_list_agent_assets` and `mctl_preflight_agent` as read-only tools SO THAT I can get the same answers from a conversation.
- AS a reviewer of the Go/Python rule pair I WANT every check to cite the CI rule line it mirrors SO THAT drift between them is visible.

## Acceptance criteria (EARS)

Reader (`internal/gitops/reader.go`)
- WHEN `ListAgentPlatformProfiles()`, `GetAgentPlatformPolicy()` or `ListAgentPlatformReleases()` is called THE SYSTEM SHALL read under the reader's read lock and return the checkout revision (commit SHA) together with the data.
- IF a `profile.yaml`, `policy.yaml` or `releases/<env>/<agent>.yaml` file exists but cannot be read or parsed THEN THE SYSTEM SHALL return an error naming the file, and SHALL NOT skip the file or return an empty result.
- IF the checkout has not been synced THEN THE SYSTEM SHALL return an error, not an empty result.
- IF the `agent-platform` directory (or a sub-directory) is absent in a synced checkout THEN THE SYSTEM SHALL return an empty list with the revision. Absence in a read checkout is a valid observation; a read failure is not.
- IF a path entry is a symlink or other non-regular file THEN THE SYSTEM SHALL return an error, as `ReadFiles` and `ComponentSourceRepo` already do.

Asset index (`GET /api/v1/agent-assets`)
- WHEN an admin calls the endpoint THE SYSTEM SHALL return the registry catalog (`Store.ListCatalog`), the gitops execution profiles, the release intents, the policy catalogs and the platform skills, plus a `gitops_revision`.
- THE SYSTEM SHALL report, for each source (`registry`, `gitops_profiles`, `gitops_policy`, `gitops_releases`, `platform_skills`), `status: ok` or `status: unavailable` with a `reason`.
- IF a source cannot be read THEN THE SYSTEM SHALL mark it `unavailable`, omit its data (`null`, not `[]`), and still return the sources that could be read, with HTTP 200.
- THE SYSTEM SHALL compute these reverse references: profile to tools, skills, `modelPolicyRef.task`, capability provider ids and `policyRef`; skill to profiles; tool to profiles; policyRef to profiles; model-policy task to profiles.
- WHEN a skill is referenced by two profiles THE SYSTEM SHALL list both profiles under that skill.
- WHILE serving the index THE SYSTEM SHALL NOT attach any eligibility, grant or "allowed" semantics to an entry.

Preflight (`GET /api/v1/agents/{name}/preflight`)
- THE SYSTEM SHALL accept the same selectors and return the same 400 errors as `GET /agents/{name}/bindings/resolve` (`handlers_agent_platform.go` `ResolveBinding`): either `environment`, or `definition_version` and `profile` with an optional `profile_version`. Never both, never neither.
- WHEN a v1alpha2 registry row resolves (`Store.ResolveBinding` / `Store.ResolveExplicit`) THE SYSTEM SHALL evaluate the checks on that profile spec and report `source: agentregistry`.
- IF the registry has no v1alpha2 binding or version for the selector (`ErrBindingNotFound`, `ErrDefinitionNotFound`, `ErrDefinitionVersionNotFound` or `ErrProfileVersionNotFound`) THEN THE SYSTEM SHALL fall back to gitops and report `source: gitops` with a `selection` field:
  - `release-intent`: from `releases/<environment>/<agent>.yaml`, using its `spec.profile.name` and `version`;
  - `explicit`: the named profile, for the pin form;
  - `naming-convention`: `<agent>-default`, only when no intent exists for that environment.
- IF the registry is unreachable or errors for any other reason THEN THE SYSTEM SHALL NOT fall back silently. It SHALL report the `binding.*` checks as `unknown` with the error, and SHALL still evaluate the profile checks from gitops with `source: gitops`.
- IF the selected gitops profile's `spec.version` differs from the version requested or pinned by the intent THEN THE SYSTEM SHALL report that mismatch in the `binding.compatibility` detail and mark that check `unknown`.
- IF no profile can be found anywhere THEN THE SYSTEM SHALL return HTTP 404.
- THE SYSTEM SHALL report each check as `{id, status: pass|fail|unknown, detail, source}`, where `source` is `agentregistry` or the CI rule it mirrors (`validate-agent-platform.py:<line>`). These are the checks:
  - `binding.lifecycle`: definition and profile lifecycle is `published` (or `deprecated`: `pass` with a note in the detail). `disabled` is `fail`. No registry row means `unknown`, unless a release intent's `registryLifecycle` gives values, in which case those are evaluated and the detail says they came from a fixture.
  - `binding.compatibility`: `compatibility.satisfied` from the registry (`validate-agent-platform.py:648`). `unknown` when nothing was resolved from the registry.
  - `profile.budget`: `budgetUsd <= limits.maxBudgetUsd` (`:263`).
  - `profile.timeout`: `timeoutSeconds <= limits.maxTimeoutSeconds` (`:267`).
  - `profile.sandbox`: `runtime.sandbox.approved` is true and the CWFT is in `approvedSandboxes[backend]` (`:276`, `:278`).
  - `profile.model_policy_task`: `modelPolicyRef.task` is in `knownModelPolicyTasks` (`:221`).
  - `profile.refs`: every tool, skill, policyRef and evidence kind is known (`:210`, `:214`, `:217`, `:260`).
  - `profile.approval_gates`: every approval gate is known, every mutation scope is known, and every mutating scope's `requiresApproval` gate is in `approval.requiredBefore` (`:287`, `:293`, `:297`).
  - `profile.capability_discovery`: unique aliases, unique (type, id) providers, provider `mctl-api` uses alias `mctl`, and `enabled` implies `mcp__mctl__*` is in tools (`:240-253`). If `capabilityDiscovery` is absent the check passes, with detail "not declared", as in CI.
- IF `policy.yaml` is unavailable THEN THE SYSTEM SHALL mark every check that needs it (`profile.budget`, `profile.timeout`, `profile.sandbox`, `profile.model_policy_task`, `profile.refs`, `profile.approval_gates`) `unknown`, and the verdict SHALL NOT be `pass`.
- IF a field a check needs is absent or has the wrong type in the profile spec THEN THE SYSTEM SHALL mark that check `unknown` with the field path, never `pass`.
- THE SYSTEM SHALL compute `verdict`: `fail` if any check fails; else `unknown` if any check is unknown; else `pass`.
- THE SYSTEM SHALL include `gitops_revision`, `source`, `selection`, the resolved definition and profile identifiers, and the `sources` status block in the response.

Access and MCP
- IF the caller is not an agent-registry admin THEN THE SYSTEM SHALL respond 403, through `requireAgentRegistryAdmin`.
- IF neither the agent registry nor the gitops reader is configured THEN THE SYSTEM SHALL respond 503. If only one is configured, the other is reported as an `unavailable` source.
- WHEN `mctl_list_agent_assets` is called THE SYSTEM SHALL forward to `GET /api/v1/agent-assets` through `s.apiGet`.
- WHEN `mctl_preflight_agent` is called THE SYSTEM SHALL forward to `GET /api/v1/agents/{agent_name}/preflight` with the given selectors, URL-escaped.
- THE SYSTEM SHALL classify `mctl_list_agent_assets` as a read tool (by its `list_` prefix) and `mctl_preflight_agent` as an ungoverned agent tool (`ungovernedAgentTools`, like `mctl_resolve_agent`). Each is classified exactly once.
- THE SYSTEM SHALL annotate both tools `readOnlyHint=true` and `destructiveHint=false`, and list both in `docs/portal-allowlist.json` with `enabled: false`.

## Out of scope

- Publishing mctl-agents `config/model-policy.yaml` or the provider endpoint map as data (slice 2). `knownModelPolicyTasks` stands in for it.
- Aligning `agentregistry.RequiredProfilePolicyFields` (`internal/agentregistry/v1alpha2_types.go:95`) with the gitops profile schema.
- CWFT drift checks (`validate-agent-platform.py:454`), the budget-env comparison against templates, and the `uncalledProfiles` logic.
- Full JSON-schema validation of profiles against `agent-platform/schemas/execution-profile.schema.json`. CI keeps doing that.
- A `mctl doctor` CLI, or any mctl-agents consumption of the index.
- Enabling either tool on the shared Cloudflare portal.

## Open questions

- Production fallback target. Live state shows no v1alpha2 binding for `issue-investigator/production`, and gitops has only `releases/shadow/`. The "Done when" call (`environment=production`) can therefore only be answered through the `naming-convention` fallback (`issue-investigator-default`). This proposal implements that fallback, labels it explicitly, and leaves the `binding.*` checks `unknown`, so the production verdict will be `unknown`, not `pass`, until a real binding exists. The reviewer should confirm that an `unknown` verdict with a full per-check report meets "Done when".
- Whether `deprecated` lifecycle should be `pass` (current choice, with a note) or `fail`. `CreateBinding` refuses deprecated versions for new bindings (`v1alpha2_store.go:401`). A rollback, however, may leave an active binding on a deprecated version (`:416`, `:627`), and resolve still returns it, so the agent would run. That is why the current choice is `pass`.
- Whether the Go checks should read the `MCTL_API_PROVIDER_ID` / `MCTL_API_REQUIRED_ALIAS` constants from the Python file. This proposal hardcodes `mctl-api` / `mctl`, citing the line they mirror.
- Tool name `mctl_preflight_agent`, as the issue asks, matches none of the read verbs (get/list/read/search/describe) that mctl-agents' policy checkpoint lets through. Agent runs may therefore be unable to call it, though humans and admins can. A name such as `mctl_get_agent_preflight` would avoid that. This proposal keeps the issue's name and classifies the tool as ungoverned (`mctl_resolve_agent` precedent). The reviewer should decide whether to rename it.
- The deployed mctl-api config (`GITOPS_LOCAL_PATH`, replica count) could not be read from `platform-gitops/services/` (see design.md). The design assumes the same full shallow clone that `cmd/api/main.go` configures by default.
