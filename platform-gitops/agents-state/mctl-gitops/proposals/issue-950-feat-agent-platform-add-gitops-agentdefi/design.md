# Design: issue-950-feat-agent-platform-add-gitops-agentdefi

## Current state

Execution settings are split between mctl-agents manifests/options and
mctl-gitops CWFT environment values. mctl-api already owns immutable agent
versions, release promotion/resolution/rollback, and execution records.
ADR 007 is normative.

## Proposed solution

\`\`\`text
platform-gitops/agent-platform/
  policy.yaml
  execution-profiles/<name>/profile.yaml
  releases/<environment>/<agent>.yaml
  schemas/execution-profile.schema.json
  schemas/release-binding-intent.schema.json
\`\`\`

Canonical AgentDefinition files remain in
\`mctl-agents/agents/_manifests/<agent>/agent.yaml\`; mctl-gitops stores only
an exact \`sourceManifest {repo,path,gitSha}\` reference.

### ExecutionProfile

\`\`\`yaml
apiVersion: agents.mctl.ai/v1alpha2
kind: ExecutionProfile
metadata:
  name: implementer-default
  owner: platform
spec:
  version: "1.0.0"
  modelPolicyRef: {task: service_agent, compatibility: ">=1 <2"}
  skills: []
  tools: [Read, Write, Edit, Glob, Grep, Bash]
  policyRef: production-code-author
  permissions:
    repository: {read: true, branchCreate: true, commit: true, pullRequestCreate: true, merge: false}
    kubernetes: none
    network: approved-providers-only
    mutationScopes: [proposal-status, target-repository-branch]
  budgetUsd: 20.00
  timeoutSeconds: 2400
  runtime:
    entrypoint: orchestrator.agents.implementer:main
    optionsBuilder: orchestrator.options:build_implementer_options
    sandbox:
      backend: argo
      clusterWorkflowTemplate: mctl-agents-implement
      approved: true
  approval: {requiredBefore: [code-authoring]}
  evidence: {required: [proposal, diff, tests, pull-request]}
\`\`\`

No global lifecycle field is stored. File existence is draft; registry
metadata owns published/deprecated/disabled; active is derived only from an
environment binding.

### Release intent

\`\`\`yaml
apiVersion: agents.mctl.ai/v1alpha2
kind: ReleaseBindingIntent
metadata: {agent: implementer, environment: shadow}
spec:
  sourceManifest:
    repo: mctlhq/mctl-agents
    path: agents/_manifests/implementer/agent.yaml
    gitSha: "<exact SHA>"
  definition: {name: implementer, version: "3"}
  profile: {name: implementer-default, version: "5"}
  previousBindingRevision: 11
\`\`\`

This is reviewed intent, not release history. Promotion uses existing mctl-api
operations and atomically records the exact compatible pair. Rollback selects
a prior recorded pair, never independently chosen versions. Initial examples
are test/shadow fixtures and visibly non-promotable until real immutable
versions exist.

### Validation

\`scripts/validate-agent-platform.py\` is wired into
\`.github/workflows/validate-manifests.yml\` and fails closed on unknown or
missing schema/reference/policy/scope/bounds/runtime data. Tools default empty
but never grant provider authorization. Mutation requires scope plus approval.
CWFT and skill references must exist. Source manifest is SHA-pinned. Release
intent must resolve one compatible exact pair.

Profiles use effective deployed values: investigator $3 with the current
7200s workflow deadline; implementer $20/2400s from production CWFT overrides;
shepherd $5 and its current effective timeout. Existing broad SDK tool names
must be constrained by explicit permissions.

## Source-of-truth boundary

| Layer | Owns |
|---|---|
| mctl-agents Git | Canonical AgentDefinition draft/checked claim |
| mctl-gitops Git | ExecutionProfile drafts, schemas, policy, binding intent |
| mctl-api | Immutable versions, lifecycle, atomic ReleaseBinding history |
| ExecutionPlan/Record | Exact contract for one run |
| Temporal/Argo | Live orchestration and sandbox execution |

## Rollback

This change is additive and not runtime-load-bearing. Revert removes the
catalog/schema/validator and CI step. After reconciliation exists, operational
rollback always selects the exact previous registry tuple.