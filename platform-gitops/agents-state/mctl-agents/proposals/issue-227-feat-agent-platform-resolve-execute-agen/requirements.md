# Resolve execute(agent, task): declarative resolver for the issue-investigator pilot

## Context

`mctl-agents` runs six/seven Claude-Agent-SDK agents whose behaviour today is
determined by a scatter of coupled sources: a hand-written `AgentManifest`
(`agents/_manifests/<agent>/agent.yaml`, `orchestrator/manifest.py`) that
describes prompt/model/tool/budget/sandbox claims, an `options.py`
`build_*_options()` function that is the actual source of truth for those
claims, `config/model-policy.yaml` plus per-agent `os.getenv(...)` overrides
for model selection, and a Temporal `resolve_agent_release` /
`record_execution` pair (`orchestrator/temporal/activities/registry.py`,
`state.py`) that pins and audits only the container image version. There is
no single call that resolves "run agent X for task Y" into one immutable,
validated, inspectable plan before an Argo `ClusterWorkflowTemplate` is
submitted.

ADR-007 (`docs/adr/007-agent-definition-execution-profile-contract.md`,
accepted 2026-08-29, circulated against `mctlhq/mctl-gitops#950` and this
issue) already fixes the target contract: an `AgentDefinition` (identity,
prompt sources, triggers, one `executionProfileRef`) and a separately
versioned, reusable `ExecutionProfile` (model policy, skills, tools, policy/
permissions, budget, timeout, runtime/sandbox, approval, evidence), joined
per environment by an atomic `ReleaseBinding`, and resolved once per run into
an immutable `ExecutionPlan`. That ADR is documentation-only; this issue is
the first runtime implementation, scoped to a behaviour-preserving pilot of
exactly one agent: `issue-investigator`. Production catalog activation (the
real `ReleaseBinding` atomic promotion) is explicitly blocked on the sibling
GitOps catalog-schema issue (`mctl-gitops#950`); this issue's resolver must
work end-to-end against checked-in, git-reviewed compatibility fixtures
instead of a live catalog API, per the issue body's own sequencing note.

## User stories

- AS the Temporal `DevLoopWorkflow` I WANT to resolve `issue-investigator`'s
  full execution contract (model, tools, budget, timeout, sandbox, approval)
  into one immutable plan before submitting the `mctl-agents-investigate`
  Argo `ClusterWorkflowTemplate` SO THAT a missing, disabled, or incompatible
  definition/profile fails the run before any pod starts, not partway
  through.
- AS a platform engineer I WANT the declarative resolver behind an explicit,
  reversible compatibility flag SO THAT I can compare declarative and legacy
  investigator runs, and instantly fall back if the declarative path
  misbehaves, without a code rollback.
- AS an auditor I WANT every investigator run to carry a machine-readable
  snapshot of exactly which definition/profile/model/tool/budget/runtime
  versions produced it SO THAT I can answer "what ran and why" without
  re-deriving it from Git history and Temporal logs.
- AS a future implementer of the implementer/shepherd pilots I WANT the
  resolver's contract (`execute(agent, task) -> ExecutionPlan`) and its
  v1alpha2 schema proven against one real agent SO THAT extending it to the
  next agent is additive, not a redesign.

## Acceptance criteria (EARS)

- WHEN `execute("issue-investigator", task)` is called with a valid task
  payload THE SYSTEM SHALL return an immutable `ExecutionPlan` containing the
  resolved definition version, profile version, release revision, concrete
  model, effective tool allow-list, budget, timeout, sandbox/CWFT reference,
  approval requirements, and evidence requirements.
- WHEN the resolved `ExecutionPlan` is used to build investigator options
  THE SYSTEM SHALL produce the same `cwd`, `model`, `allowed_tools`,
  `mcp_servers`, `permission_mode`, `max_budget_usd`, `add_dirs`, and `env`
  shape that `orchestrator.options.build_issue_investigator_options()`
  produces today for the same inputs.
- WHEN the investigator runs with the compatibility flag unset or set to its
  legacy value THE SYSTEM SHALL execute exactly the current
  `run_issue_investigator.investigate()` code path, unchanged.
- WHEN the investigator runs with the compatibility flag set to its
  declarative value THE SYSTEM SHALL resolve and log an `ExecutionPlan` and
  drive `build_issue_investigator_options()` from it instead of from the
  module-level `INVESTIGATOR_MODEL` constant and hard-coded tool list.
- IF the referenced `AgentDefinition`, `ExecutionProfile`, or their
  compatibility pairing is missing, disabled, or incompatible THEN THE
  SYSTEM SHALL raise a resolution error identifying the missing/incompatible
  reference before any Argo `ClusterWorkflowTemplate` is submitted.
- IF the declarative resolution path raises THEN THE SYSTEM SHALL NOT submit
  `mctl-agents-investigate` for that run; the Temporal workflow step SHALL
  fail with a non-retryable, actionable error rather than falling back
  silently to the legacy path.
- WHILE the declarative compatibility flag is enabled for `issue-investigator`
  THE SYSTEM SHALL still preserve deterministic proposal slug/idempotency
  behavior, the proposal artifact triplet, the `.status.yaml` `source` block,
  the GitHub proposal comment, and the stop-at-`proposed` behavior exactly as
  today.
- WHEN two calls to `execute("issue-investigator", task)` use the same
  checked-in fixture state and the same task payload THE SYSTEM SHALL return
  byte-identical `ExecutionPlan` identifiers (definition version, profile
  version, revision, prompt hash) — the resolver is deterministic and
  replay-safe.
- WHEN `mctl_trigger_issue(issue_url)` or the `mctl-agents-investigate`
  operation is invoked THE SYSTEM SHALL require no change to the caller's
  request shape or observed contract, regardless of which compatibility mode
  is active.
- IF the declarative path is rolled back to legacy THEN THE SYSTEM SHALL
  resume producing identical results to a deployment that never enabled the
  declarative path, with the rollback documented and covered by a test.

## Out of scope

- Migrating `implementer` or `shepherd` to the resolver (ADR-007 non-goal,
  reaffirmed here).
- Any change to investigator prompts, permissions, model-selection semantics,
  or product-visible behavior.
- A live mctl-api catalog/registry endpoint for `AgentDefinition` /
  `ExecutionProfile` / `ReleaseBinding` (that is `mctl-gitops#950`'s GitOps
  catalog-schema work; this issue consumes checked-in fixtures instead).
- Production cutover / promotion of the declarative path as the default —
  this proposal ships the resolver, the pilot migration, the flag, and the
  equivalence tests; flipping the default is a separate, later change once
  `#950` lands.
- A catalog UI or agent self-service creation flow.
- Approving a proposal, starting Tier 2 implementation, or merging a PR
  (unaffected by this change).
- Modifying `orchestrator/temporal/activities/registry.py`'s or `state.py`'s
  existing HTTP contracts with mctl-api (`resolve_agent_release`,
  `record_execution`) — those stay as-is; this issue's `ExecutionPlan` is a
  local, in-repo artifact layered on top, not a new mctl-api schema.

## Open questions

- Exact on-disk location for `ExecutionProfile` fixtures (`agents/_profiles/`
  proposed in design.md, mirroring `agents/_manifests/`) is not specified by
  the issue. Proceeding with that mirrored layout since it reuses
  `validate_manifest.py`'s existing "checked claim against real code"
  pattern and needs no new top-level directory convention.
- The issue does not specify the exact flag name/mechanism for compatibility
  mode. Proceeding with an explicit env var
  (`ISSUE_INVESTIGATOR_RESOLVER_MODE=legacy|declarative`, default `legacy`)
  read once at driver start, mirroring the existing
  `ISSUE_INVESTIGATOR_MODEL` env-override convention already validated by
  `validate_manifest.py`.
- Whether resolved `ExecutionPlan` identifiers should also be pushed into
  mctl-api's `record_execution` payload is left open — this proposal treats
  that as a mctl-api schema change out of this repo's scope and instead logs
  the plan and asserts on it in tests/replay fixtures; a follow-up can extend
  the audit trail once `#950`'s registry-side schema exists.
- The issue does not name a deterministic version-numbering scheme for
  fixture-backed definition/profile versions absent a real registry.
  Proceeding with content-hash-derived versions (sha256 of the fixture file,
  truncated) so re-running against unchanged fixtures is provably
  deterministic without inventing a fake incrementing counter that could be
  mistaken for a real registry sequence.
