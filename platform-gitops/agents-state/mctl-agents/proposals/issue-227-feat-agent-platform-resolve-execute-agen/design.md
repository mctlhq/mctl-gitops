# Design: issue-227-feat-agent-platform-resolve-execute-agen

## Current state

Agent behavior is split between v1alpha1 manifests, options builders,
model-policy configuration, CWFT values, and image-only registry resolution.
There is no immutable pre-submit plan containing the complete effective
contract.

## Proposed solution

Add \`orchestrator/resolver.py\` and migrate only issue-investigator behind an
explicit \`legacy|declarative\` flag.

### v1alpha2 definition and compatibility fixtures

The canonical issue-investigator manifest at
\`agents/_manifests/issue-investigator/agent.yaml\` moves to
\`agents.mctl.ai/v1alpha2\` and contains identity/prompt/triggers plus
\`executionProfileRef: {name, compatibility}\`.

The pilot profile does not create \`agents/_profiles\` as a competing catalog.
It lives under \`tests/fixtures/resolver/profiles/\`, mirrors #950's schema,
and includes modelPolicyRef, skills, tools, policyRef, permissions, bounded
budget/timeout, runtime/sandbox/CWFT, approval and evidence. The investigator
uses the current $3 budget and 7200s workflow deadline. Permissions explicitly
limit target repositories to read, GitOps writes to the proposal path, and the
proposal issue comment; tools do not grant authorization.

A release fixture is explicitly non-promotable:

\`\`\`yaml
bindingSource: compatibility-fixture
promotable: false
environment: production
definition: {name: issue-investigator, version: "<definition hash>"}
profile: {name: investigator-default, version: "<profile hash>"}
releaseRevision: 1
registryLifecycle:
  definition: published
  profile: published
\`\`\`

Lifecycle metadata models registry-version state only; no global lifecycle
field is added to definition/profile YAML. Hashes pin fixture contents but are
not presented as real registry version numbers.

### Resolver

\`\`\`python
@dataclass(frozen=True)
class ExecutionPlan:
    agent: str
    definition_version: str
    profile_version: str
    release_revision: int
    binding_source: str
    model: str
    model_policy_version: str
    prompt_hashes: tuple[str, ...]
    skill_hashes: tuple[str, ...]
    tools: tuple[str, ...]
    policy_ref: str
    permissions: Mapping[str, Any]
    budget_usd: float
    timeout_seconds: float
    entrypoint: str
    options_builder: str
    sandbox_backend: str
    cluster_workflow_template: str
    target_repository_sha: str
    approval: Mapping[str, Any]
    evidence: tuple[str, ...]
\`\`\`

\`execute(agent, task)\`:

1. loads the canonical v1alpha2 definition;
2. resolves the fixture binding only through an explicit compatibility source;
3. loads the exact profile selected by the binding;
4. checks the definition's compatibility range against the concrete profile
   version;
5. rejects missing/ambiguous/disabled/unknown/unbounded/unapproved inputs;
6. resolves model using existing model-policy code;
7. pins target SHA and all owned hashes;
8. returns one frozen plan before Argo submission.

Declarative failure is non-retryable/actionable and does not switch to legacy.
Unknown API versions fail loudly. No baked-in default is accepted as a
v1alpha2 release.

### Investigator wiring

Default mode remains \`legacy\`. In \`declarative\`, the driver resolves once,
logs the immutable plan, verifies requested CWFT, and builds options from the
plan. Equivalence tests compare cwd, model, allowed tools, MCP servers,
permission mode, budget, add_dirs and env against today's builder.

The existing workflow contract and stop-at-proposed gate remain unchanged.
Production activation/default flip is a later change after #950 supplies real
validated bindings.

## Tests

- v1alpha1 compatibility and unknown-version failure;
- valid v1alpha2 definition/profile load;
- compatibility range checked against concrete profile version;
- missing/ambiguous/disabled/incompatible/unknown-policy/unbounded/unapproved
  failures before submission;
- tools cannot expand permissions;
- immutable deterministic snapshot including target SHA and owned hashes;
- legacy/declarative options equivalence;
- stop-at-proposed regression;
- explicit legacy rollback drill;
- fixture marked non-promotable and never treated as registry state.

## Rollback

Set the explicit mode to \`legacy\`; no declarative failure triggers this
automatically. Code rollback removes resolver/fixtures and restores the
v1alpha1 investigator manifest. Other agents remain untouched.