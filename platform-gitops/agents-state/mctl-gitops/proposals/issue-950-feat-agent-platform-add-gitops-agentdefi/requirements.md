# GitOps AgentDefinition and ExecutionProfile catalog

## Context

Issue #950 implements the GitOps/schema half of accepted
[mctl-agents ADR 007](https://github.com/mctlhq/mctl-agents/blob/main/docs/adr/007-agent-definition-execution-profile-contract.md).

The contract separates the canonical \`AgentDefinition\` in
\`mctl-agents/agents/_manifests/<agent>/agent.yaml\`, independently versioned
\`ExecutionProfile\` constraints reviewed in Git, immutable registry versions
and atomic environment \`ReleaseBinding\` history in mctl-api, and an immutable
\`ExecutionPlan\`/\`ExecutionRecord\` for each run.

This issue must not create a second AgentDefinition body or release database.
It adds the profile catalog, schemas, fail-closed validation, and an exact-pair
release-intent shape for the existing mctl-api publish/promote/rollback path.
Migration is behavior-preserving: effective deployed CWFT overrides win over
Python defaults (implementer is currently $20 / 2400s).

## Acceptance criteria

- \`ExecutionProfile\` uses \`agents.mctl.ai/v1alpha2\` and requires owner,
  version/compatibility metadata, \`modelPolicyRef\`, versioned skills,
  explicit tools, \`policyRef\`, permissions, bounded budget/timeout,
  approved runtime/sandbox/CWFT, approval rules, and evidence requirements.
- Tools default to empty and are never authorization. Provider authorization
  remains authoritative. Unknown tool/action/policy/permission/model/skill/
  runtime references fail closed.
- Mutation requires both a scoped permission and the applicable approval rule.
- Canonical AgentDefinition data is not mirrored. References use an exact
  \`sourceManifest: {repo, path, gitSha}\` pointing to the mctl-agents
  v1alpha2 manifest.
- A release intent contains one exact
  \`definition: {name, version}\` and one exact
  \`profile: {name, version}\`. Validation checks the definition's profile
  name and compatibility constraint against that profile version.
- Missing, ambiguous, unpublished, deprecated-for-new-promotion, disabled, or
  incompatible versions reject promotion.
- Rollback restores one recorded prior compatible tuple and creates a new
  binding revision. Independent rollback of either half is rejected.
- Lifecycle authorities remain separate: Git file existence means draft;
  registry version owns published/deprecated/disabled; environment binding
  derives active. No global mutable \`lifecycleState\` field is allowed.
- Initial issue-investigator, implementer and shepherd profiles preserve
  effective behavior and do not broaden permissions. Implementer remains
  $20/2400s because the production CWFT overrides Python's $3/900s defaults.
- CI covers positive fixtures plus missing policy/scopes/bounds, unknown
  references, incompatible pairs, disabled versions, non-atomic rollback,
  and unapproved sandbox.
- No production fixture is activated and no existing mctl-api operation or
  running agent behavior changes in this issue.

## Out of scope

- A second AgentDefinition authoring surface.
- A parallel release-history store.
- Automatic release reconciliation or production promotion.
- Runtime resolver implementation (#227), UI, or new-agent activation.

## Fixed decisions

ADR 007 is normative for API version, lifecycle authority, atomic binding,
exact-pair rollback, fail-closed behavior, tools-versus-permissions, and
source-of-truth boundaries. Only schema/file mechanics remain implementation
details.