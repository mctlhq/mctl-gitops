# Architecture: AgentDefinition and ExecutionProfile contract

## Context

`mctl-agents` already has real infrastructure for agent lifecycle: `AgentManifest`
(`orchestrator/manifest.py`, `agents/_manifests/*/agent.yaml`, formalising the
classification in `docs/agent-inventory.yaml`) describes each of the six
SDK-backed agents (issue-investigator, implementer, shepherd, incident-responder,
service-agent, mentor; question-author exists as a seventh manifest but is not
yet part of the dev-loop). `orchestrator/validate_manifest.py` checks every
manifest claim against the real `orchestrator/options.py` builder it describes.
mctl-api (mctl-api#126, consumed here through
`orchestrator/temporal/activities/registry.py` and `state.py`) already provides
immutable published agent versions, per-environment releases (`resolve_agent_release`),
promotion/rollback (the `mctl_promote_agent` / `mctl_rollback_agent` MCP
operations this session has access to), and an execution audit trail
(`record_execution` / `ExecutionRecord`).

What is missing is the conceptual seam the issue asks for: today one YAML
document (`AgentManifest`) conflates a concrete agent's identity and lifecycle
(owner, purpose, prompt, trigger) with a reusable execution shape (model,
tools, budget, timeout, sandbox). There is no `ExecutionProfile` a second
agent could share, no documented lifecycle state machine for definitions or
profiles, and no single document that draws the boundary between reviewed
Git/GitOps state, mctl-api's immutable registry rows, and Temporal/Argo's
runtime-resolved execution. Without that document, the GitOps catalog-schema
and runtime-resolver follow-ups named in the parent epic (mctlhq/.github#18)
would each have to invent this boundary themselves, risking three
incompatible answers to the same question. This proposal is that missing
architecture document: an ADR, not a code change.

## User stories

- AS a mctl-agents maintainer I WANT a documented split between `AgentDefinition`
  and `ExecutionProfile` SO THAT two agents (e.g. a future second issue-driven
  agent) can share one execution profile without duplicating tool/budget/model
  policy across manifests.
- AS the author of the GitOps catalog-schema follow-up issue I WANT explicit
  lifecycle states and source-of-truth boundaries SO THAT I can implement the
  schema without re-deciding ownership or lifecycle semantics myself.
- AS the author of the runtime-resolver follow-up issue I WANT a defined
  execution-identity shape (definition version + profile version + model +
  policy + runtime, all immutable references) SO THAT a resolved execution is
  always traceable to exactly the definition/profile that produced it, and an
  unresolved reference fails safely instead of silently falling back.
- AS an operator running `mctl_promote_agent` / `mctl_rollback_agent` today
  I WANT the ADR to state how the existing mctl-api registry (agent, version,
  environment release) maps onto the new model SO THAT existing registry and
  release data is not invalidated by a later schema change.
- AS the maintainer of `issue-investigator`, `implementer`, and `shepherd`
  I WANT each mapped explicitly into the new model (owner, profile, tools,
  policy, budget, runtime, approval boundary) SO THAT their very different
  risk profiles (read-only vs code-authoring vs merge-authoring, per
  `docs/agent-inventory.yaml`'s `riskLevel` field) are preserved, not
  flattened.

## Acceptance criteria (EARS)

- WHEN the ADR is published THE SYSTEM SHALL define `AgentDefinition` as the
  concrete, lifecycle-managed identity (owner, purpose, prompt/instruction
  sources, triggers, lifecycle state, reference to exactly one
  `ExecutionProfile`) and `ExecutionProfile` as the reusable, independently
  versioned bundle (model policy, tool allow-list, skills, budget, timeout,
  runtime/sandbox backend, approval requirement, evidence requirement).
- WHEN the ADR maps `AgentManifest` onto the new model THE SYSTEM SHALL state
  explicitly whether `AgentManifest` becomes the on-disk serialization of
  `AgentDefinition` (with `spec.runtime`/`spec.toolPolicy`/`spec.execution`
  splitting into an embedded or referenced `ExecutionProfile`), remains a
  build-time-only input translated into both at publish time, or is replaced,
  and SHALL justify the choice against `orchestrator/manifest.py` and
  `orchestrator/validate_manifest.py`'s existing "manifest is a checked claim,
  not a second implementation" contract.
- WHEN the ADR defines lifecycle states THE SYSTEM SHALL enumerate the
  allowed states for both `AgentDefinition` and `ExecutionProfile` (at
  minimum draft/published/active/deprecated/disabled) and SHALL enumerate
  every allowed transition as an explicit table, so each transition can be
  tested independently.
- WHEN the ADR defines source-of-truth boundaries THE SYSTEM SHALL state,
  for each of (a) reviewed Git/GitOps desired state, (b) mctl-api's immutable
  registry versions and environment releases, (c) the runtime-resolved
  execution snapshot Temporal activities produce (`resolve_agent_release`),
  and (d) Temporal/Argo's own execution state, which one is authoritative for
  which question, and SHALL make clear these are non-overlapping.
- WHEN the ADR defines compatibility/versioning rules THE SYSTEM SHALL cover
  `apiVersion` evolution (today pinned to `agents.mctl.ai/v1alpha1` in
  `orchestrator/manifest.py`), `AgentDefinition` version bumps, `ExecutionProfile`
  version bumps, prompt/skill input hashing (building on
  `docs/agent-inventory.yaml`'s existing `promptSources` vs
  `runtimeContextInputs` split), and environment release rollback semantics.
- IF an execution's resolved `AgentDefinition` version or `ExecutionProfile`
  version reference cannot be found THEN THE SYSTEM SHALL define this as a
  fail-safe condition (execution refused or explicitly falls back to a
  documented default, never silently substituted), consistent with
  `resolve_agent_release`'s existing "no release yet" `None` contract.
- WHEN the ADR maps the three named agents THE SYSTEM SHALL record, for
  each of `issue-investigator`, `implementer`, and `shepherd`, its owner,
  model-policy task, tool allow-list, budget, sandbox/runtime, and approval
  boundary, grounded in `agents/_manifests/*/agent.yaml` and
  `docs/agent-inventory.yaml`'s existing `riskLevel`/`writes` fields.
- WHEN the ADR states a migration path THE SYSTEM SHALL describe how existing
  `agent.yaml` files and existing mctl-api registry rows (already-published
  versions, already-promoted releases) remain valid without a breaking
  migration, or SHALL state the compatibility shim if not.
- WHILE this proposal is being implemented THE SYSTEM SHALL NOT change any
  runtime behavior of `issue-investigator`, `implementer`, `shepherd`, or any
  other agent in `docs/agent-inventory.yaml` — this is a design document only.
- WHEN the ADR is complete THE SYSTEM SHALL identify the concrete schema and
  resolver follow-up issues it unblocks (the GitOps catalog-schema and
  runtime-resolver children of mctlhq/.github#18) and state which ownership/
  lifecycle questions those issues no longer need to re-decide.

## Out of scope

- Implementing a resolver, a new catalog schema file, or any runtime code
  change (explicit issue non-goal).
- Rebuilding or migrating the existing mctl-api registry data model
  (explicit issue non-goal; mctl-api#126 stays as-is).
- Any catalog UI or new MCP operation (explicit issue non-goal).
- Activating a new agent or changing which agents exist today (explicit
  issue non-goal).
- Changing `issue-investigator`, `implementer`, or `shepherd` runtime
  behavior, prompts, tools, or budgets (explicit issue non-goal).
- The enabling work tracked separately (#149 isolated Argo execution, #195
  execution traces, #196 execution identity/context, #197 runtime policy
  checkpoints, #198 human approval, #199 execution evidence) — this ADR
  states how they plug into the model but does not implement them.
- Merging or starting implementation of the resolver/schema as part of this
  investigation (explicit issue non-goal).

## Open questions

- The issue's "reusable ... profile" wording collides with an existing,
  unrelated concept: `config/model-policy.yaml` already defines `profiles`
  (`cheap`/`balanced`/`strong` model-escalation tiers) consumed via
  `modelPolicy.task`. The ADR must pick disambiguating terminology (e.g.
  `ExecutionProfile` vs `model-policy profile`) rather than let "profile"
  mean two different things in the same system. Recorded as a naming risk
  to resolve in the ADR itself, not blocking this proposal.
- Whether `ExecutionProfile` is versioned fully independently of
  `AgentDefinition` (many-to-many sharing) or 1:1 per definition initially,
  with sharing deferred, is left to the ADR's own judgment — the issue asks
  for "reusable" but no current agent shares tool/budget/sandbox shape with
  another closely enough to demand day-one sharing (`docs/agent-inventory.yaml`
  shows each agent with distinct budgets and mostly distinct tool sets).
  Resolved in design.md by proposing 1:1-by-default, N:1-by-construction.
- Whether `question-author` (manifested in `agents/_manifests/question-author/`
  but absent from the Temporal `DevLoopWorkflow` / registry-resolve path)
  is in scope for the initial `AgentDefinition` migration or deferred is not
  stated by the issue. Treated as in-scope-for-mapping, out-of-scope-for-
  registry-resolution-changes, since it already has a manifest today.
- No other ambiguity: the issue is otherwise fully specified (explicit
  contract list, explicit acceptance criteria, explicit non-goals).
