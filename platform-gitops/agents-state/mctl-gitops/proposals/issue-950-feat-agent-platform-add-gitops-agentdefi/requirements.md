# GitOps AgentDefinition and ExecutionProfile catalog

## Context

Issue #950 asks `mctl-gitops` to own a GitOps-managed catalog representation
for approved `AgentDefinition` and `ExecutionProfile` resources, per the
architecture ADR-226 in `mctlhq/mctl-agents` (issue #226, dependency of this
issue). ADR-226 was implemented on 2026-08-29 (`mctl-agents` PR #228 — see
`platform-gitops/agents-state/mctl-agents/proposals/issue-226-architecture-agent-platform-define-agent/.status.yaml`,
`status: implemented`), so the schema/catalog layout this proposal designs is
no longer ahead of the architecture decision — it is the intended next step
the ADR names as one of its two unblocked follow-ups ("the GitOps
catalog-schema ... children of mctlhq/.github#18").

ADR-226 decided: `AgentDefinition` (identity — owner, purpose, prompt
sources, triggers, lifecycle state, one `executionProfileRef`) keeps its
on-disk GitOps serialization as `mctl-agents`' existing
`agents/_manifests/<agent>/agent.yaml` (gaining `spec.executionProfileRef`
under a new `agents.mctl.ai/v1alpha2` `apiVersion`), and its
`spec.toolPolicy`/`spec.execution` fields move out into a separate,
independently versioned `ExecutionProfile` resource. The ADR does not fix
which repository owns the `ExecutionProfile` file, or how a reviewed,
promotable "this version is approved for environment X" record is expressed
in GitOps terms alongside mctl-api's existing immutable-version/
environment-release registry (`mctl_publish_agent_version`,
`mctl_promote_agent`, `mctl_resolve_agent`, `mctl_rollback_agent`,
`mctl_list_agent_versions` — already-live MCP operations). Today, the
`ExecutionProfile`-shaped fields (model/tools/budget/timeout/sandbox =
Argo `ClusterWorkflowTemplate`) already live in `mctl-gitops`, but hardcoded
inline in each CWFT as a workflow parameter or container env var — e.g.
`ISSUE_INVESTIGATOR_BUDGET_USD: "3.00"` in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`,
`IMPLEMENTER_BUDGET_USD: "20.00"` / `IMPLEMENTER_TIMEOUT_SECONDS: "2400"` in
`cwft-mctl-agents-implement.yaml`, `SHEPHERD_BUDGET_USD: "5.00"` in
`cwft-mctl-agents-shepherd.yaml`. Changing any of these today means editing
Argo template YAML directly, with no schema, no cross-reference validation,
and no lifecycle state. This proposal turns that implicit, scattered
execution shape into a reviewed, versioned, CI-validated catalog resource in
`mctl-gitops` — the repo that already owns Argo CWFTs and runtime deployment
state per this repo's own `CLAUDE.md` — while leaving `AgentDefinition`
authorship exactly where ADR-226 put it (`mctl-agents`' `agent.yaml`), so
this proposal does not create a second place to edit an agent's identity or
a parallel version-history for it.

## User stories

- AS a platform operator I WANT a versioned, PR-reviewed `ExecutionProfile`
  resource in `mctl-gitops` SO THAT changing an agent's budget, timeout,
  tool allow-list or sandbox template is a reviewed, auditable diff instead
  of a hand-edited CWFT env var with no schema or validation.
- AS a `mctl-gitops` CI reviewer I WANT every `ExecutionProfile` and every
  environment-activation reference validated against real repo state (an
  existing `ClusterWorkflowTemplate` name, an existing
  `platform-skills/catalog/` skill, positive bounded budget/timeout) SO
  THAT a broken or unsafe reference is caught before merge, not at runtime.
- AS the mctl-api agent registry (mctl-api#126, already implementing
  immutable published versions and environment releases) I WANT
  `mctl-gitops`'s catalog to reference registry versions rather than
  reimplement them SO THAT there is exactly one place ("what actually got
  promoted") — this repo only ever records reviewed *intent*.
- AS the maintainer of `issue-investigator`, `implementer`, and `shepherd`
  I WANT their current effective model/tools/budget/runtime settings
  represented as day-one `ExecutionProfile` fixtures with zero behavior
  change SO THAT the migration is provably a refactor, not a silent policy
  change (e.g. `implementer`'s `IMPLEMENTER_BUDGET_USD: "20.00"` must land
  as `budgetUsd: 20.00`, not a rounded or re-guessed number).
- AS a security reviewer I WANT the schema and its CI validator to fail
  closed on missing owner, unknown references, write-capable implicit tool
  defaults, and unbounded budget/timeout SO THAT an incomplete or malicious
  profile cannot silently expand what an agent can do.

## Acceptance criteria (EARS)

- WHEN a new `ExecutionProfile` resource is added under
  `platform-gitops/agent-platform/execution-profiles/<name>/profile.yaml`
  THE SYSTEM SHALL validate it against a versioned schema
  (`apiVersion: agentplatform.mctl.ai/v1alpha1`, `kind: ExecutionProfile`)
  covering `owner`, `model` (a model-policy task name), `tools` (an
  explicit allow-list, default empty), `skills` (platform-skill name
  references), `budgetUsd`, `timeoutSeconds`, `runtime.clusterWorkflowTemplateRef`,
  `approval`, and `lifecycleState`.
- WHEN a new `AgentDefinition` catalog entry is added under
  `platform-gitops/agent-platform/definitions/<name>/definition.yaml` THE
  SYSTEM SHALL validate `owner`, `purpose`, `triggers`, `lifecycleState`,
  and exactly one `executionProfileRef: {name, version}` — this file is a
  reviewed *approved-catalog snapshot* of the corresponding
  `mctl-agents` `agent.yaml`, not a second authoring surface; it SHALL
  carry a `sourceManifest` pointer (`repo`, `path`, `gitSha`) back to the
  `mctl-agents` file it mirrors.
- WHEN a `ExecutionProfile.runtime.clusterWorkflowTemplateRef` is set THE
  SYSTEM SHALL reject the file in CI unless a `ClusterWorkflowTemplate`
  with that exact `metadata.name` exists under
  `platform-gitops/argo-workflows/cluster-templates/`.
- WHEN a `ExecutionProfile.skills` entry is set THE SYSTEM SHALL reject the
  file in CI unless a matching directory exists under
  `platform-gitops/platform-skills/catalog/` with `status` in
  `{active, deprecated}`.
- WHEN an `AgentDefinition.executionProfileRef` is set THE SYSTEM SHALL
  reject the file in CI unless a profile with that `name` exists in
  `execution-profiles/` and, once profiles gain a published version number,
  a version matching `executionProfileRef.version` exists.
- IF `ExecutionProfile.tools` is omitted THEN THE SYSTEM SHALL default it to
  an empty list (no tools) rather than reject the file, and IF any listed
  tool is a known write/mutating tool (a `Write`/`Edit`/`Bash`-class name
  from a fixed deny-by-default set, or `mcp__mctl__mctl_*` operations
  documented as write/destructive) THEN THE SYSTEM SHALL require
  `approval.required: true` on that profile, rejecting the file otherwise.
- IF `ExecutionProfile.budgetUsd` or `.timeoutSeconds` is missing, zero, or
  exceeds a fixed platform ceiling (`platform-gitops/agent-platform/policy.yaml`)
  THEN THE SYSTEM SHALL reject the file — there is no "unbounded" value.
- IF `ExecutionProfile.owner` or `AgentDefinition.owner` is missing THEN THE
  SYSTEM SHALL reject the file.
- IF an `ExecutionProfile` or `AgentDefinition` `lifecycleState` is
  `disabled` THEN THE SYSTEM SHALL reject any
  `platform-gitops/agent-platform/releases/<environment>/<agent>.yaml`
  environment-activation entry that references it.
- WHEN an environment-activation file
  (`platform-gitops/agent-platform/releases/<environment>/<agent>.yaml`) is
  added or changed THE SYSTEM SHALL validate that both its
  `definitionRef` and `profileRef` resolve to catalog entries whose
  `lifecycleState` is `published` or `active` (never `draft`, `deprecated`
  for new activations, or `disabled`).
- WHEN `issue-investigator`, `implementer`, and `shepherd` fixtures are
  added THE SYSTEM SHALL preserve their current effective budget, timeout,
  tools and sandbox/`ClusterWorkflowTemplate` reference exactly as read
  from the corresponding `cwft-mctl-agents-*.yaml` files today (no behavior
  change).
- WHEN `mctl-gitops` CI runs on a pull request THE SYSTEM SHALL run a
  dedicated validator script (mirroring `scripts/validate-platform-skills.py`'s
  existing pattern for the platform-skills catalog) as part of
  `.github/workflows/validate-manifests.yml`, exercised against both
  positive fixtures (the three migrated agents) and negative fixtures
  (missing owner, unknown `clusterWorkflowTemplateRef`, unbounded budget,
  a write tool without `approval.required`, a `disabled` profile still
  referenced by an environment-activation file).
- WHILE this proposal is implemented THE SYSTEM SHALL NOT change
  `mctl-api`'s registry data model, NOT replace
  `mctl_publish_agent_version`/`mctl_promote_agent`/`mctl_rollback_agent`,
  and NOT change any running agent's actual budget, timeout, tools, or
  sandbox target.
- WHEN the catalog layout is documented THE SYSTEM SHALL record, in
  `design.md` and a repo doc, the boundary between (a) `mctl-agents`'
  `agent.yaml` (authoring surface for `AgentDefinition` identity), (b)
  `mctl-gitops`'s `agent-platform/` catalog (reviewed `ExecutionProfile`
  authoring surface, plus a reviewed *approved-snapshot* mirror of
  `AgentDefinition` and reviewed environment-activation intent), and (c)
  `mctl-api`'s registry (immutable published versions + actual environment
  releases) — so no later reader re-derives this boundary differently.

## Out of scope

- Implementing the sync automation that would keep `mctl-gitops`'s
  `AgentDefinition` snapshot mechanically in sync with `mctl-agents`'
  `agent.yaml`, or that would call `mctl_publish_agent_version`/
  `mctl_promote_agent` automatically when a catalog file changes (explicit
  issue non-goal: "Implementing the generic runtime resolver"; this
  proposal defines the reviewed GitOps record, not the reconciler that
  reads it — analogous to how `gitops-bump.yaml` bumping `image.tag` and
  `wft-deploy-service` actually deploying it are two separate pieces of
  work in this repo today).
- Changing `mctl-api`'s registry schema or UI (explicit issue non-goal).
- Activating any new agent, or changing `issue-investigator`/`implementer`/
  `shepherd`'s actual runtime behavior (explicit issue non-goal).
- Migrating every existing `agents-state` cron/orchestration workflow
  (`mctl-agents-run`, `-daily`, `-issue-poll`, `-reconcile`, `-approve`) into
  the profile model — only the three named agents (explicit issue
  non-goal: "Migrating every existing agent before the three-agent
  compatibility slice is proven").
- Full validation of `AgentDefinition` fields that only `mctl-agents`' own
  `orchestrator/validate_manifest.py` can check (e.g. that a
  `promptSources` path actually resolves inside that repo, or that a
  `model` maps to a real `config/model-policy.yaml` task) — `mctl-gitops`
  CI validates shape and its own cross-references only; see Open questions.

## Open questions

- Exact repo ownership of the `ExecutionProfile` file was left unresolved by
  ADR-226. This proposal resolves it as `mctl-gitops`, grounded in three
  things ADR-226 itself already establishes as `mctl-gitops`-owned:
  Argo CWFTs, runtime deployment state, and (per the design's
  four-layer source-of-truth table) the fact that `ExecutionProfile.runtime`
  is exactly "today's `runtime.type`/`entrypoint`/`optionsBuilder`,
  `sandbox.backend`/`clusterWorkflowTemplate`" — a `ClusterWorkflowTemplate`
  reference is meaningless without the repo that defines
  `ClusterWorkflowTemplate`s to validate it against. If a future ADR revision
  disagrees, only `execution-profiles/` and its validator move — the
  `AgentDefinition` snapshot and `releases/` design are unaffected.
- Whether `mctl-gitops`'s `AgentDefinition` catalog entry should be a full
  mirror (all fields duplicated) or a thin pointer (name/owner/lifecycle/
  `executionProfileRef`/`sourceManifest` pointer only) is resolved in
  design.md as "thin pointer" — duplicating `promptSources`/
  `runtimeContextInputs` here would be exactly the "parallel registry" the
  issue explicitly forbids, since `mctl-agents`' `agent.yaml` already owns
  those fields and `orchestrator/validate_manifest.py` already checks them
  against real code.
- How `mctl-gitops`'s reviewed environment-activation intent
  (`releases/<environment>/<agent>.yaml`) is reconciled into mctl-api's
  actual `mctl_promote_agent` call is explicitly out of scope (see above) —
  recorded here so the follow-up resolver issue does not have to
  re-discover that this file currently has no automation reading it; it is
  a reviewed record for a human (or a later CWFT) to act on, the same
  transitional state `platform-skills/bindings/` was in before
  `wft-platform-skill-publish.yaml` existed.
- No other ambiguity: the issue's Scope/Safe-default/Acceptance-criteria
  sections are otherwise explicit enough to design against directly.
