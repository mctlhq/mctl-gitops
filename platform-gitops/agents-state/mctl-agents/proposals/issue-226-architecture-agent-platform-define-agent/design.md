# Design: issue-226-architecture-agent-platform-define-agent

## Current state

Grounded in the actual clone (`mctlhq/mctl-agents`, this proposal's target
repo):

- **`AgentManifest`** (`orchestrator/manifest.py`) is one YAML document per
  agent (`agents/_manifests/<agent>/agent.yaml`) with `apiVersion:
  agents.mctl.ai/v1alpha1`, `kind: Agent`. It bundles, in one flat
  `spec`, fields that the issue wants split in two:
  - identity/lifecycle-ish: `metadata.name`, `metadata.owner`,
    `spec.prompt.sources`, `spec.runtime.entrypoint` (e.g.
    `orchestrator.run_issue_investigator:investigate`).
  - execution-shape: `spec.runtime.optionsBuilder`, `spec.modelPolicy.task`
    (+ `legacyEnvOverride`), `spec.toolPolicy.allow`, `spec.execution.budgetUsd`,
    `spec.execution.timeoutSeconds`, `spec.execution.sandbox.backend` /
    `.clusterWorkflowTemplate`.
  - There is no version field and no lifecycle-state field anywhere in this
    file today — a manifest simply exists or doesn't. `load_all()` treats
    the six/seven `agent.yaml` files as the entire population, keyed by
    directory name; a duplicate name is a hard load error, not a version
    conflict.
- **`docs/agent-inventory.yaml`** is the human/CI-checked classification
  that predates and parallels `AgentManifest`: it draws the line between
  "agent" (calls the Claude Agent SDK — issue-investigator, implementer,
  shepherd, incident-responder, service-agent, mentor, question-author) and
  "orchestration" (deterministic control flow: issue-poller,
  shepherd-reconcile, run_all, the Argo CWFTs/cronworkflows themselves). It
  also carries `riskLevel` and `writes` per agent (e.g. implementer
  `riskLevel: high` / "the only agent that authors code"; shepherd
  `riskLevel: high` / "it merges to main"; issue-investigator
  `riskLevel: low` / "read-only against the target repo") and the
  `promptSources` vs `runtimeContextInputs` split (inputs this repo owns and
  can hash at publish time, vs. inputs that resolve per-run against a
  target repo's own SHA — see that file's extensive module docstring).
- **`orchestrator/validate_manifest.py`** enforces that `AgentManifest` never
  drifts from the real code: it calls the real `build_*_options()` function
  in `orchestrator/options.py` and diffs `allowed_tools`/`max_budget_usd`
  against the manifest's claims, checks `docs/agent-inventory.yaml` against
  every manifest field-by-field, and resolves every prompt source. This is
  the closest thing today to a schema-conformance test suite, and it is the
  precedent this ADR must not break: whatever `AgentDefinition`/
  `ExecutionProfile` becomes, its claims must stay checkable against real
  code the same way.
- **mctl-api's agent registry** (mctl-api#126, not in this clone but
  consumed via three Temporal activities in this repo):
  - `orchestrator/temporal/activities/registry.py`'s `resolve_agent_release`
    calls `GET /api/v1/agents/{agent}/resolve?environment=...` then
    `GET /api/v1/agents/{agent}/versions`, and returns `None` — not an
    error — when nothing has ever been promoted, which
    `orchestrator/temporal/workflows/dev_loop.py`'s `_resolve()` treats as
    "fall back to the CWFT's own baked-in default image" (an explicit,
    already-designed fail-safe, not a silent substitution).
    `_image_ref()`'s docstring documents a real incident (2026-08-06,
    `mctl-agents-investigate-2b91b916` stuck on `InvalidImageName`) from
    conflating a bare `image_repository` with an already-tagged one —
    concrete evidence that "immutable reference" needs a validated,
    single-shape contract, not an ad hoc string.
  - `orchestrator/temporal/activities/state.py`'s `record_execution` posts
    to `/api/v1/agents/executions` with `agent`, `environment`, `version`,
    `image_ref`, `target_repo`, `argo_workflow_name`, `phase` — this is
    today's entire "execution identity" shape. It is explicitly *not* the
    gitops `.status.yaml` commit (that stays inside the Argo CWFT, under the
    `mctl-gitops-main-writes` mutex) — the module docstring calls out this
    boundary directly: registry/executions vs. gitops desired state are
    already understood as separate authorities in this codebase, just not
    written down as a general rule.
  - MCP operations already exposed to operators
    (`mctl_promote_agent`/`mctl_rollback_agent`/`mctl_resolve_agent`/
    `mctl_publish_agent_version`/`mctl_list_agent_versions`) confirm the
    registry already has: immutable published versions (manifest + git SHA +
    image ref + prompt hash, per `mctl_publish_agent_version`'s parameters),
    per-environment (`production`/`shadow`) releases, and rollback-to-
    previous-promotion.
- **Temporal/Argo execution state**: `DevLoopWorkflow`
  (`orchestrator/temporal/workflows/dev_loop.py`) is the durable orchestrator
  that resolves a release, submits an Argo CWFT via
  `activities/argo.py:submit_and_wait`, waits on a human approval signal,
  and records the result. Two existing ADRs in `docs/adr/` already document
  adjacent decisions at this exact boundary: ADR-005 (reconcile loop on
  Temporal) and ADR-006 (phase 6: merge → deploy → monitor, dated
  2026-08-29, the newest doc in the repo). Both are written in the same
  "Context / Decision / Non-goals / Implementation map" shape this ADR
  should match, and both explicitly frame their work as one phase of a
  larger, external "the plan" (referenced but not present in this repo —
  it lives outside `mctl-agents`, most likely in the `mctlhq/.github#18`
  epic or a linked doc). Separately, `context/decisions/` holds
  repo-internal ADRs in the Nygard template (`context/decisions/README.md`:
  "capture the context behind decisions about the orchestrator — language
  and runtime choice, harness dependencies, tooling"); `docs/adr/` is where
  cross-cutting dev-workflow-control-plane architecture already lives. This
  proposal's ADR belongs in `docs/adr/`, numbered 007, not
  `context/decisions/`.
- **Naming collision already in the codebase**: `config/model-policy.yaml`
  defines `profiles:` (`cheap`/`balanced`/`strong`, each with a model and an
  `escalates_to`), consumed via `spec.modelPolicy.task` →
  `config/model_policy.py`. This is an unrelated, narrower concept than the
  issue's `ExecutionProfile` (which also carries tools, budget, timeout,
  sandbox, approval, evidence). The ADR must name these distinctly.

## Proposed solution

This is a documentation-only change: one ADR,
`docs/adr/007-agent-definition-execution-profile-contract.md`, in the same
format as ADR-005/006 (Context / Decision / Non-goals / Implementation map,
plus an explicit state-machine section). No code, manifest, or registry
change ships with this proposal. The ADR content itself (drafted here so
reviewers can assess feasibility before the ADR is written verbatim in the
implementation task) resolves the issue's five contract points as follows:

1. **`AgentDefinition`** — the concrete, lifecycle-managed resource.
   Fields: `name` (today's manifest directory name / `metadata.name`),
   `owner` (`metadata.owner`), `purpose` (free text, new), `promptSources`
   + `runtimeContextInputs` (already exist, unchanged shape — lift verbatim
   from `docs/agent-inventory.yaml`'s existing split), `triggers` (today
   implicit in `docs/agent-inventory.yaml`'s `triggeredBy`; becomes an
   explicit field), `lifecycleState` (new), and exactly one
   `executionProfileRef` (new — a name + version pointer, not an inline
   embed, so an `ExecutionProfile` can be published and promoted
   independently). `AgentManifest` becomes the on-disk GitOps
   serialization of the *desired* `AgentDefinition` (draft) state — i.e.
   `agents/_manifests/<agent>/agent.yaml` keeps existing today, gains a
   `spec.executionProfileRef: {name, version}` field, and its
   `spec.runtime.optionsBuilder` / `spec.toolPolicy` / `spec.execution`
   fields move to live in the profile's own file instead of being inlined.
   This is an additive schema change (new `apiVersion`,
   `agents.mctl.ai/v1alpha2`, per the compatibility rule below), not a
   rewrite: `orchestrator/manifest.py`'s `SUPPORTED_API_VERSION` gate means
   old and new manifests can be told apart cleanly, and
   `orchestrator/validate_manifest.py`'s "call the real builder, diff the
   claim" contract carries over unchanged — it would just resolve
   `toolPolicy`/`execution` from the referenced profile file instead of the
   definition file.
2. **`ExecutionProfile`** — the reusable, independently versioned
   resource. Fields: `model` (references a `model-policy.yaml` *task*, kept
   as today's indirection — explicitly NOT renamed to avoid the
   profile/profile collision noted above; the ADR states this as a
   controlled synonym clash with a one-paragraph justification, since
   renaming `config/model-policy.yaml`'s `profiles:` key is out of scope),
   `skills` (new: a list of platform-skill references, formalising what
   `docs/agent-inventory.yaml`'s `skills.sourceOfTruth` note already says
   the registry "must not re-implement", i.e. `ExecutionProfile` references
   skill names, mctl-gitops's `platform-skills/catalog/` stays the store),
   `tools` (today's `toolPolicy.allow`), `budgetUsd`, `timeoutSeconds`,
   `runtime` (today's `runtime.type`/`entrypoint`/`optionsBuilder`,
   `sandbox.backend`/`clusterWorkflowTemplate`), `approval` (new: whether
   this profile's executions require a human signal before a mutating step
   — formalises the atomic-approve pattern `DevLoopWorkflow` already
   implements for the implement step), `evidence` (new: what execution
   evidence this profile's runs must produce — a forward reference to #199,
   not implemented here). Cardinality: one `ExecutionProfile` may be
   referenced by more than one `AgentDefinition` (the "reusable" the issue
   asks for), but nothing in `docs/agent-inventory.yaml` today shows two
   agents that should actually share one (every agent has a distinct
   budget and mostly distinct tool set) — so the migration creates one
   profile per existing agent (1:1) and leaves N:1 sharing as a capability
   the schema supports but no migration forces.
3. **Immutable published versions** — unchanged from what mctl-api#126
   already does for agents (`mctl_publish_agent_version`,
   `mctl_list_agent_versions`); this ADR extends the same mechanism to
   profiles: an `ExecutionProfile` gets its own version row (manifest hash +
   git SHA), published independently of the `AgentDefinition` that
   references it, so a profile-only change (e.g. a budget bump) publishes
   without bumping the definition's own version.
4. **Environment release/promotion state** — unchanged mechanism
   (`mctl_promote_agent`/`mctl_rollback_agent`/`resolve_agent_release`),
   generalized to resolve two references per environment instead of one:
   `(definitionVersion, profileVersion)`. `ResolvedRelease`
   (`activities/registry.py`) gains a `profile_version`/`profile_image_ref`
   pair alongside today's `version`/`image_ref`; `_resolve()` in
   `dev_loop.py` becomes a two-part lookup that still returns `None` on
   either half missing, preserving today's exact fail-safe (fall back to
   the CWFT default) rather than inventing a new failure mode.
5. **One execution pinned to exact resolved versions** — `ExecutionRecord`
   (`activities/state.py`) gains `definition_version` and `profile_version`
   fields alongside its existing `version`/`image_ref`/`target_repo`; the
   ADR states this is the "execution identity" #196 will build on, and that
   an execution missing either version reference must be rejected by
   `record_execution`'s schema (mctl-api side, out of scope here) rather
   than silently accepted with an empty string, the way `image_ref=""`
   is silently tolerated today for the pre-registry compatibility case.
   This ADR flags that pre-registry tolerance as a compatibility shim to
   preserve, not a pattern to extend to the new fields.

**Lifecycle states** (both `AgentDefinition` and `ExecutionProfile`, same
state machine, independently instantiated per resource):

```
draft --publish--> published --release(env)--> active
published --deprecate--> deprecated --disable--> disabled
active --deprecate--> deprecated (existing releases keep resolving; no NEW
                                    environment may release this version)
deprecated --disable--> disabled (resolve_agent_release must treat this
                                    version as unresolvable going forward)
```

`draft` = exists in Git/GitOps only, never published (mirrors today's
`agent.yaml` before any `mctl_publish_agent_version` call — this state
already exists implicitly for every manifest today). `published` = has an
immutable registry version, not yet released to any environment.
`active` = released to at least one environment (`resolve_agent_release`
returns it for that environment). `deprecated` = still resolvable where
already released, but not eligible for new promotions (mirrors
`mctl_disable_tenant_skill`'s adjacent skill-lifecycle pattern in this same
MCP surface). `disabled` = `resolve_agent_release` must return `None`,
routing through the exact same fail-safe path `_resolve()` already has for
"never released."

**Source-of-truth boundaries** (four authorities, restated as an explicit
table so schema/resolver issues do not re-derive it):

| Layer | Owns | Example in this repo |
|---|---|---|
| Git/GitOps (mctl-agents `agents/_manifests/`, mctl-gitops) | Desired state: draft definitions/profiles, reviewed and PR'd | `agents/_manifests/issue-investigator/agent.yaml` |
| mctl-api registry | Immutable published versions + environment releases | `mctl_publish_agent_version`, `mctl_promote_agent`, `resolve_agent_release` |
| Runtime-resolved execution snapshot | The exact (definition version, profile version, image ref) one Temporal workflow pinned at start | `ResolvedRelease` in `activities/registry.py` |
| Temporal/Argo execution state | The actual run: workflow history, Argo pod/workflow object, until TTL expiry | `DevLoopWorkflow` history, `submit_and_wait`'s `WorkflowResult` |

Git/GitOps never answers "what actually ran" (it has no runtime visibility);
the registry never answers "is this specific run still in flight" (Temporal
owns that); the runtime snapshot is a value, not a live source (it is
recorded once, in `ExecutionRecord`, and never mutated); Temporal/Argo state
is authoritative only until its own TTL (`ttlStrategy.secondsAfterCompletion`
for Argo, retention limits for Temporal), which is exactly why
`record_execution` exists — to outlive that TTL.

## Alternatives

1. **Keep `AgentManifest` as a single flat resource; add lifecycle fields
   directly to it, no separate profile.** Rejected: it does not give the
   issue's required "reusable" profile — every field bump (a budget change)
   would still force a definition-version bump even when identity/prompt/
   trigger are unchanged, which is the exact coupling the issue asks to
   remove. It also does not resolve the issue's explicit ask for two
   distinct resources.
2. **Model `ExecutionProfile` as a pure registry-side concept with no
   GitOps file, configured only via `mctl_deploy_service`-style MCP calls.**
   Rejected: every other agent-affecting input in this repo today is
   Git-reviewed (`agent.yaml` is a PR'd file); an MCP-only profile would be
   the one execution-affecting input with no code review trail, breaking
   the "reviewed Git/GitOps desired state" authority this ADR itself
   defines. It would also fragment validation — `validate_manifest.py`
   could no longer check profile claims against `options.py` the way it
   checks manifest claims today.
3. **Full N:1 sharing from day one — model `ExecutionProfile` as a small,
   curated set of named tiers (e.g. `read-only-low-risk`,
   `code-authoring-high-risk`) that every `AgentDefinition` picks from,
   collapsing today's seven distinct budgets into three or four tiers.**
   Rejected for this proposal: it would require re-litigating each agent's
   actual budget/tool/timeout values (a behavior change,
   explicitly out of scope — "Changing investigator/implementer/shepherd
   behavior" is a listed non-goal) as part of an architecture-only issue.
   The chosen 1:1-by-default design supports this consolidation later as a
   pure follow-up (merge two profiles once they are proven identical)
   without blocking the contract on it now.

## Platform impact

- **Migrations**: additive only. `agents.mctl.ai/v1alpha2` manifests can be
  introduced one agent at a time (`orchestrator/manifest.py`'s
  `SUPPORTED_API_VERSION` check already fails loudly on an unrecognized
  version, so a mixed v1alpha1/v1alpha2 population during migration is
  detectable, not silently ambiguous — though the ADR should note that
  `load_all()` would need to accept both versions during the transition
  window, which is a resolver-issue implementation detail, not decided
  here). Existing mctl-api registry rows (published agent versions,
  environment releases) are unaffected — profiles are new rows alongside
  them, not a rewrite of the agent table.
- **Backward compatibility**: `resolve_agent_release`'s `None`-means-
  "fall back to CWFT default" contract is preserved and extended
  symmetrically to the profile half of the resolution, so a target
  environment with no profile release yet behaves exactly like today's
  "no release yet" case — no new failure mode introduced.
- **Resource impact**: none from this issue directly (no code ships). The
  follow-up resolver issue will add one extra registry lookup per
  execution (profile resolve alongside definition resolve); this ADR notes
  it as a follow-up cost, not one paid here.
- **Risks + mitigations**:
  - *Risk*: the ADR is written but the follow-up schema/resolver issues
    interpret it inconsistently. *Mitigation*: the acceptance criterion
    "follow-up schema and resolver issues can implement the contract
    without reopening ownership or lifecycle decisions" is treated as a
    hard gate on the ADR's completeness — the state-machine table and
    source-of-truth table above are written to be copy-pasted into those
    issues directly.
  - *Risk*: "profile" naming collision with `config/model-policy.yaml`'s
    existing `profiles:` causes confusion in review or in future code.
    *Mitigation*: the ADR states the collision explicitly (as this design
    does) and mandates that code/docs always qualify as "execution profile"
    vs "model-policy profile" until/unless a follow-up renames the latter.
  - *Risk*: scope creep — an implementer reads this ADR and starts building
    the resolver as part of "closing out" this issue. *Mitigation*: the ADR
    itself repeats the issue's non-goals verbatim in its own Non-goals
    section (matching ADR-005/006's convention of an explicit Non-goals
    list), and this proposal's tasks.md contains no code tasks.
