# Design: issue-950-feat-agent-platform-add-gitops-agentdefi

## Current state

Grounded in the actual clone (`mctlhq/mctl-gitops`, this proposal's target
repo):

- **Execution shape is hardcoded per-CWFT today.** Each agent's model
  choice, budget, timeout, tool posture and sandbox are not a resource —
  they are literal values baked into
  `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`:
  - `cwft-mctl-agents-investigate.yaml` line ~303:
    `ISSUE_INVESTIGATOR_BUDGET_USD: "3.00"`, no timeout override shown (SDK
    default), sandbox = the CWFT itself
    (`agent_image: ghcr.io/mctlhq/mctl-agents:1.31.0`, `resources.limits: {cpu:
    2000m, memory: 8Gi}`).
  - `cwft-mctl-agents-implement.yaml` line ~351:
    `IMPLEMENTER_TIMEOUT_SECONDS: "2400"`, line ~415:
    `IMPLEMENTER_BUDGET_USD: "20.00"`, `resources.limits: {cpu: 3000m,
    memory: 8Gi}`.
  - `cwft-mctl-agents-shepherd.yaml` line 483-484:
    `SHEPHERD_BUDGET_USD: "5.00"`.
  There is no schema, no owner field, no lifecycle state, and no
  cross-reference validation for any of these values — changing a budget
  means editing Argo template YAML directly and hoping
  `validate-manifests.yml`'s generic `kubeconform` pass (which only checks
  the CWFT is a structurally valid `ClusterWorkflowTemplate`, not that its
  embedded agent-budget env vars are sane) catches nothing wrong.
- **`AgentDefinition` identity already has a documented, decided home.**
  ADR-226 (`mctl-agents` issue #226, dependency of this issue, now
  `status: implemented` per this repo's own
  `platform-gitops/agents-state/mctl-agents/proposals/issue-226-architecture-agent-platform-define-agent/.status.yaml`,
  PR `mctlhq/mctl-agents#228`) decided `AgentManifest`
  (`agents/_manifests/<agent>/agent.yaml` in `mctl-agents`) becomes the
  on-disk GitOps serialization of `AgentDefinition`'s *draft* state, gaining
  a `spec.executionProfileRef: {name, version}` field under a new
  `agents.mctl.ai/v1alpha2` `apiVersion`. `mctl-gitops` is not that repo, so
  this proposal must not re-author identity/prompt/trigger fields here — the
  issue's own baseline explicitly says "must not create a parallel registry
  or duplicate existing release history."
- **`mctl-api`'s agent registry already exists and is out of scope to
  rebuild.** The seven MCP operations this session has access to
  (`mctl_create_agent`, `mctl_publish_agent_version`, `mctl_promote_agent`,
  `mctl_resolve_agent`, `mctl_rollback_agent`, `mctl_list_agent_versions`,
  `mctl_list_agent_executions`) already provide immutable published
  versions, per-environment (`production`/`shadow`) releases, promotion and
  rollback. This proposal's catalog must reference that registry's version
  identifiers, never reimplement "what is the current active version."
- **`mctl-gitops` already has one working precedent for exactly this
  shape of problem**: `platform-gitops/platform-skills/` — a `catalog/`
  of named, owned, lifecycle-stated resources
  (`catalog/<skill>/metadata.yaml` + `SKILL.md`, fields `name`, `title`,
  `description`, `owner`, `visibility` in
  `{public,tenant,admin,platform-internal}`, `status` in
  `{draft,active,deprecated}`, `runtimes`), a `bindings/` directory that
  activates catalog entries per tenant/role
  (`bindings/tenants/admins.yaml`: `{tenant, enabledSkills: []}`), a
  `policy.yaml` allow/denylist, and a CI validator script,
  `scripts/validate-platform-skills.py`, wired into
  `.github/workflows/validate-manifests.yml`'s "Validate platform skill
  registry" step. That validator already implements every pattern this
  issue needs: name/directory-match checks, required-field checks, enum
  checks, cross-reference checks (a binding may not reference an unknown or
  wrong-visibility/wrong-status skill), and a secret-leak regex scan. This
  design reuses that pattern almost verbatim rather than inventing a new
  one.
- **CI validation infrastructure**: `.github/workflows/validate-manifests.yml`
  already runs `helm lint`, `kubeconform` (with the community CRD schema
  catalog for `ClusterWorkflowTemplate`/`ExternalSecret`/etc.), the platform
  skill validator, `scripts/validate-local-workdir.py`, and `promtool` rule
  unit tests, all as required PR gates (`on: pull_request`). There is no
  Python test framework in this repo (`scripts/validate-platform-skills.py`
  is a plain script with no `pytest`/`conftest.py` anywhere in the clone) —
  negative-fixture testing here means "run the validator against a fixture
  designed to fail, assert non-zero exit," matched to the existing style,
  not a new test framework.
- **Every platform change is a PR-reviewed commit** (`CLAUDE.md`), except
  the two named automated-bump workflows (`gitops-bump.yaml`,
  `release-deploy.yaml`), which only ever touch a single `image.tag` field.
  A new "sync mctl-agents `agent.yaml` into mctl-gitops automatically" or
  "auto-promote on catalog change" workflow would not qualify for that
  narrow exception (it is not an `image.tag` bump), so it would need its
  own PR-reviewed design — explicitly deferred, see Out of scope.

## Proposed solution

Add a new top-level catalog, `platform-gitops/agent-platform/`, structured
like `platform-skills/` (same review model, same CI-gate shape, same
lifecycle vocabulary) but scoped to the two resources ADR-226 defines,
plus one new resource this proposal introduces to express reviewed
environment intent without duplicating mctl-api's registry:

```
platform-gitops/agent-platform/
  policy.yaml                          # platform-wide safe-default ceilings
  execution-profiles/
    issue-investigator/profile.yaml    # ExecutionProfile, v1alpha1
    implementer/profile.yaml
    shepherd/profile.yaml
  definitions/
    issue-investigator/definition.yaml # AgentDefinition catalog snapshot
    implementer/definition.yaml
    shepherd/definition.yaml
  releases/
    production/
      issue-investigator.yaml          # environment-activation intent
      implementer.yaml
      shepherd.yaml
```

**`ExecutionProfile`** (`apiVersion: agentplatform.mctl.ai/v1alpha1`, `kind:
ExecutionProfile`) — the new resource this repo actually authors and owns.
Fields, each traced to where the value lives today:

```yaml
apiVersion: agentplatform.mctl.ai/v1alpha1
kind: ExecutionProfile
metadata:
  name: implementer
  owner: platform                 # required; CI-rejected if absent
lifecycleState: active            # draft|published|active|deprecated|disabled
spec:
  model: balanced                 # model-policy.yaml TASK name (mctl-agents-owned;
                                   # mctl-gitops validates non-empty string only —
                                   # see Open questions in requirements.md)
  tools: []                       # explicit allow-list; default empty (no tools)
  skills: []                      # platform-skills/catalog/ names; validated here
  budgetUsd: 20.00                # from IMPLEMENTER_BUDGET_USD in cwft-mctl-agents-implement.yaml
  timeoutSeconds: 2400            # from IMPLEMENTER_TIMEOUT_SECONDS
  runtime:
    clusterWorkflowTemplateRef: mctl-agents-implement   # must exist under
                                                         # argo-workflows/cluster-templates/
  approval:
    required: true                # implementer authors code + opens PRs — mutating
  resources:
    cpuLimit: "3000m"
    memoryLimit: "8Gi"
```

**`AgentDefinition`** (`apiVersion: agentplatform.mctl.ai/v1alpha1`, `kind:
AgentDefinition`) — a thin, reviewed **catalog snapshot**, not a second
authoring surface:

```yaml
apiVersion: agentplatform.mctl.ai/v1alpha1
kind: AgentDefinition
metadata:
  name: implementer
  owner: platform
lifecycleState: active
spec:
  purpose: "Opens PRs implementing accepted proposals from agents-state/."
  executionProfileRef:
    name: implementer
    version: "1.0.0"             # ExecutionProfile registry version once published
  sourceManifest:                # pointer back to the real authoring file — this
    repo: mctlhq/mctl-agents      # is what keeps this from being a parallel registry
    path: agents/_manifests/implementer/agent.yaml
    gitSha: "<pinned at snapshot time>"
```

No `promptSources`, `runtimeContextInputs`, or `triggers` payload is
duplicated here — those stay exclusively in `mctl-agents`' `agent.yaml`,
matching ADR-226's decision and the issue's explicit "must not ... duplicate
existing release history" constraint. `mctl-gitops` CI can validate this
file's own shape and its `executionProfileRef` against the local
`execution-profiles/` catalog; it cannot validate that `sourceManifest`
still matches `mctl-agents`' current `agent.yaml` content without a
cross-repo fetch, which this proposal does not add (see Open questions) —
the field exists so a human reviewer, or a later CI job with read access to
`mctl-agents`, has an exact pointer to check against.

**`releases/<environment>/<agent>.yaml`** — reviewed environment-activation
*intent*, deliberately not a second copy of mctl-api's release state:

```yaml
agent: implementer
environment: production
definitionRef: {name: implementer, version: "1.0.0"}
profileRef: {name: implementer, version: "1.0.0"}
```

This is the GitOps-reviewed record of "this is the version combination this
environment should run" — the same role `platform-gitops/services/<team>/<service>/values.yaml`'s
`image.tag` plays for a regular service (a reviewed desired-state pointer,
not the deployment mechanism itself). Nothing in this proposal makes this
file *drive* `mctl_promote_agent` automatically; that reconciliation is
explicitly deferred (see Out of scope in requirements.md), matching how
`image.tag` bumps (`gitops-bump.yaml`) and actual service deploys
(`wft-deploy-service`) are already two separate, sequenced pieces of work in
this repo.

**`policy.yaml`** — platform-wide fail-closed ceilings, mirroring
`platform-skills/policy.yaml`'s allow/denylist shape but for numeric safe
defaults:

```yaml
maxBudgetUsd: 25.00
maxTimeoutSeconds: 3600
writeToolPatterns:
  - "Write"
  - "Edit"
  - "Bash"
  - "mcp__mctl__mctl_deploy_*"
  - "mcp__mctl__mctl_retire_*"
  - "mcp__mctl__mctl_delete_*"
  - "mcp__mctl__mctl_rollback_*"
  - "mcp__mctl__mctl_*_service"
```
(`writeToolPatterns` is intentionally a superset check, not an exhaustive
enumeration — a profile that lists a tool matching one of these patterns
without `approval.required: true` fails CI; a tool that matches none of
these patterns is treated as read-only, so an unrecognized-but-actually-
mutating future tool is a documented residual risk closed by keeping this
list current, not by the schema alone.)

**Validator**: `scripts/validate-agent-platform.py`, structured exactly like
`scripts/validate-platform-skills.py` (same `load_yaml`/`fail`/errors-list
shape): loads every `execution-profiles/*/profile.yaml` and
`definitions/*/definition.yaml`, applies the checks from requirements.md's
EARS list, then loads every `releases/*/*.yaml` and cross-checks
`definitionRef`/`profileRef` against the catalog. Wired into
`.github/workflows/validate-manifests.yml` as a new step, "Validate agent
platform catalog", immediately after "Validate platform skill registry" (same
Python/PyYAML toolchain already installed in that job — no new dependency).

**Fixtures**: `execution-profiles/{issue-investigator,implementer,shepherd}/profile.yaml`
and matching `definitions/*/definition.yaml`, with values read directly off
today's CWFTs (see Current state's line references) so the migration is a
byte-for-byte transcription, not a re-decision. `releases/production/*.yaml`
for all three, since all three are already active in production today.
Negative fixtures live under `scripts/testdata/agent-platform/negative/` (one
YAML file per failure mode named in requirements.md's EARS list) and are
exercised by a small shell/python check in the same CI step (or a follow-up
step) asserting the validator exits non-zero for each — matching the "run
against a fixture that must fail" style already implicit in this repo's
validator scripts (none currently ship this as an automated regression, so
this proposal is a net improvement in that respect, not merely parity).

## Alternatives

1. **Duplicate the full `AgentDefinition` (identity + prompt + triggers)
   inside `mctl-gitops` instead of a thin pointer.** Rejected: this is
   exactly the "parallel registry" the issue's baseline explicitly forbids,
   and it would create two places that can drift — `mctl-agents`'
   `orchestrator/validate_manifest.py` already checks the real file against
   real code; a full duplicate here would have no such check and would
   silently go stale.
2. **Put `ExecutionProfile` in `mctl-agents` instead of `mctl-gitops`**
   (i.e., keep the whole split inside the repo that already owns
   `agent.yaml`). Rejected: `ExecutionProfile.runtime.clusterWorkflowTemplateRef`
   is only meaningful and only checkable against a repo that defines
   `ClusterWorkflowTemplate`s — that is `mctl-gitops`, not `mctl-agents`.
   Splitting the resource across the repo boundary that already exists for
   "who owns Argo state" (per this repo's own `CLAUDE.md`) is more
   consistent than collapsing it into the repo that owns prompts/identity.
3. **Skip the `AgentDefinition` catalog snapshot entirely and let
   `releases/<environment>/<agent>.yaml` reference `mctl-agents`' `agent.yaml`
   version directly with no local mirror.** Rejected for now: without a
   local `AgentDefinition` entry, `mctl-gitops` CI has nothing to validate
   an `executionProfileRef`/`definitionRef` pairing against locally, and the
   issue's own acceptance criteria explicitly asks for "Investigator,
   implementer and shepherd fixtures/definitions" in this repo. The thin
   snapshot keeps that requirement satisfied without duplicating owned
   content — see the `sourceManifest` pointer design above.
4. **Make the environment-activation file call `mctl_promote_agent`
   automatically via a new bot-commit workflow, day one.** Rejected for this
   proposal: that would be a third, unreviewed direct-to-main automation
   alongside the two `CLAUDE.md` already names as exceptions
   (`gitops-bump.yaml`, `release-deploy.yaml`), and it duplicates the
   "runtime resolver" work the issue's own non-goals explicitly exclude.
   Landing the reviewed record first, with the reconciler as an explicit,
   separately-scoped follow-up, matches how this repo already sequenced
   `image.tag` bumps vs. actual deploys.

## Platform impact

- **Migrations**: additive only. No existing CWFT, `values.yaml`, or
  `agent.yaml` is modified by this proposal — the three fixture profiles are
  a new, parallel catalog that documents today's already-live values. A
  follow-up issue (explicitly out of scope here) would make the CWFTs
  actually read from a resolved `ExecutionProfile` instead of a hardcoded
  env var; until then, this catalog is documentation-grade truth that must
  be kept in step with the CWFTs by PR review discipline, called out
  explicitly in the migration doc this proposal produces.
- **Backward compatibility**: `mctl-api`'s registry, `mctl_promote_agent`/
  `mctl_rollback_agent`/`resolve_agent_release`, and every running agent's
  actual runtime behavior are untouched. `agents-state/` proposal/status
  tracking (the mechanism this very proposal is written through) is a
  separate concern from `agent-platform/` and is not modified.
- **Resource impact**: negligible — a handful of new YAML files plus one
  new CI step (a Python script over local YAML, no network calls, similar
  cost to the existing platform-skill validation step).
- **Risks + mitigations**:
  - *Risk*: the `agent-platform/` catalog drifts from the CWFTs' actual
    hardcoded values (since nothing enforces they match until the resolver
    follow-up lands). *Mitigation*: fixtures are transcribed with explicit
    line-number citations in this design (auditable), and the migration doc
    (task 6) states this drift risk and names the follow-up issue that
    closes it.
  - *Risk*: `writeToolPatterns` in `policy.yaml` misses a real mutating tool,
    letting a profile grant it without `approval.required`. *Mitigation*:
    documented as a residual risk in this design rather than papered over;
    the pattern list is reviewed the same way any other security-relevant
    GitOps file is (PR review, `CLAUDE.md`'s no-bypass rule), and the
    fail-closed default (unknown reference rejected, not silently allowed)
    still holds for every *listed* tool.
  - *Risk*: a reviewer edits `releases/<environment>/<agent>.yaml` believing
    it actually promotes the version in mctl-api. *Mitigation*: the file's
    own header comment states plainly that it is reviewed intent only, not
    a trigger, until the reconciler follow-up exists; the migration doc
    states this explicitly as well.
