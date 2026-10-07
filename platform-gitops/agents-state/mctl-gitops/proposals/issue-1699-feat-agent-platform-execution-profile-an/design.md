# Design: issue-1699-feat-agent-platform-execution-profile-an

## Current state

- `platform-gitops/agent-platform/` holds six `ExecutionProfile`s
  (`execution-profiles/<name>/profile.yaml`) and six `ReleaseBindingIntent`s
  (`releases/shadow/<agent>.yaml`), all `bindingSource: compatibility-fixture`,
  `promotable: false`. `README.md` explains that the v1alpha1 agents
  (incident-responder, mentor, service-agent) have profiles and bindings only
  for mctl-agents' release gate (`tools/check_binding_hash.py`
  `evaluate_promotion`), which compares sha256 of `agent.yaml` with
  `spec.sourceManifest.contentHash`.
- `schemas/execution-profile.schema.json` requires `version, modelPolicyRef,
  skills, tools, policyRef, permissions, budgetUsd (>0), timeoutSeconds (int >0),
  runtime{entrypoint, optionsBuilder, sandbox{backend, clusterWorkflowTemplate,
  approved, budgetEnv?}}, approval, evidence`. Empty `skills`,
  `mutationScopes`, `requiredBefore` and `evidence.required` arrays are allowed.
  `schemas/release-binding-intent.schema.json` requires `gitSha` as 40 hex chars
  and `contentHash` as `sha256:<64 hex>`.
- `policy.yaml`: `limits.maxBudgetUsd: 25.00`, `maxTimeoutSeconds: 7200`;
  `knownTools` includes `Read`, `Grep`, `Glob`; `knownModelPolicyTasks` includes
  `service_agent`; `knownPolicies` = `scoped-proposal-authoring`,
  `production-code-author`, `pr-shepherd`, `incident-response`,
  `digest-authoring` -- every one names a write; `approvedSandboxes.argo`
  includes `mctl-agents-run`.
- `scripts/validate-agent-platform.py`:
  - `validate_profile_file` checks references against `policy.yaml` and the
    ceilings.
  - `validate_profile_against_cwft` (real catalog only, or fixtures that ship
    `cluster-templates/`) loads `cwft-<clusterWorkflowTemplate>.yaml` and
    compares `budgetUsd` with either the variable named by `sandbox.budgetEnv`
    (`_env_value_by_name`) or the single `*_BUDGET_USD` in the template
    (`_unique_env_by_suffix`), and `timeoutSeconds` with the single
    `*_TIMEOUT_SECONDS` or, absent one, `spec.activeDeadlineSeconds`.
  - `cwft-mctl-agents-run.yaml` sets `SERVICE_AGENT_BUDGET_USD`,
    `MENTOR_BUDGET_USD`, `INCIDENT_RESPONDER_BUDGET_USD`, no
    `*_TIMEOUT_SECONDS`, and `activeDeadlineSeconds: 3600` (line 48).
- `.github/workflows/validate-manifests.yml` runs
  `scripts/validate-agent-platform.py --selftest`; fixtures live under
  `scripts/tests/fixtures/agent-platform/{valid,invalid}/<case>/`, each may
  ship its own `policy.yaml` (`case_policy_path`) and `cluster-templates/`
  (`case_cwft_dir`).
- `.github/workflows/auto-merge.yml` excludes `^platform-gitops/agent-platform/`
  from auto-merge; `.github/CODEOWNERS` assigns `platform-gitops/agent-platform/**`
  to `@mashkovd`.

What #598 ships (read at `ad4a2b95...`, file identical at `15afef70...`,
sha256 `4af4245df12133259961558f52a409cbf1ca8cca2ed08d5476942c22f62fe513`):
`agents/_manifests/authoring-canary/agent.yaml`, `apiVersion:
agents.mctl.ai/v1alpha1`, `runtime.entrypoint:
orchestrator.run_authoring_canary:run_authoring_canary`, `optionsBuilder:
orchestrator.options:build_authoring_canary_options`, `triggers: []`,
`modelPolicy.task: service_agent`, `toolPolicy.allow: [Read, Glob, Grep]`,
`execution.budgetUsd: 0.01`, sandbox `argo/mctl-agents-run` (nominal). Its
`orchestrator/validate_manifest.py` already maps `"authoring-canary-default":
"authoring-canary"` in `_AGENT_BY_CATALOG_PROFILE` and compares `spec.tools`
and `modelPolicyRef.task` with the builder; it deliberately does not compare
budgets. mctl-agents reads `policy.yaml` only for `spec.limits.maxService*`, so
an additive policy key does not affect it.

### Why the validator cannot accept the canary today

With `clusterWorkflowTemplate: mctl-agents-run`:
- no `budgetEnv` -> `_unique_env_by_suffix` raises "declares 3 _BUDGET_USD
  variables; cannot tell which one a profile pins";
- `budgetEnv: AUTHORING_CANARY_BUDGET_USD` -> "names sandbox.budgetEnv ... but
  cwft-mctl-agents-run.yaml does not set it";
- `budgetEnv` naming another agent's variable -> budget mismatch (0.01 vs 5/10/20),
  and it would be a false statement anyway.
Adding `AUTHORING_CANARY_BUDGET_USD` to the template is forbidden by the issue
and by mctl-agents' `tests/test_authoring_canary.py`. Naming another template
does not help: every agent template sets its own agent's budget. So a
validator change is required.

## Proposed solution

### 1. Validator: an explicit, verified "uncalled" exemption in policy.yaml

Add to `policy.yaml`:

```yaml
  # Profiles whose agent has no caller: no ClusterWorkflowTemplate or
  # CronWorkflow runs them, so no template carries their budget and
  # budgetUsd cannot be compared with one. validate-agent-platform.py skips
  # only that comparison, and only after proving the claim: no file under
  # argo-workflows/cluster-templates/ may mention the profile's entrypoint
  # module. Giving the agent a caller means removing it from this list and
  # declaring sandbox.budgetEnv in the same PR.
  uncalledProfiles:
    # mctl-agents#596/#598: inert proof-run agent for the governed authoring
    # path. Manifest names mctl-agents-run only because the contract needs an
    # existing template.
    - authoring-canary-default
```

The exemption lives in `policy.yaml`, not as a new profile field, so the
profile keeps the exact shape mctl-agents' resolver and `validate_manifest.py`
already parse, and granting an exemption is a reviewed change to the policy
file (CODEOWNERS-guarded) rather than something a profile asserts about itself.

Changes in `scripts/validate-agent-platform.py`:

- `Policy.__init__`: `self.uncalled_profiles = set(spec.get("uncalledProfiles") or [])`
  (degrades to empty, which means "nobody is exempt" -- fails closed).
- `validate_profile_against_cwft(path, doc, errors, cwft_dir, uncalled=False)`:
  when `uncalled` is true,
  - if `sandbox.budgetEnv` is set -> error ("an uncalled profile has no budget
    variable to name");
  - scan every `*.yaml` in `cwft_dir` as text for the entrypoint module's last
    component (`run_authoring_canary`, from `runtime.entrypoint.split(":")[0]
    .rsplit(".", 1)[-1]`); any hit -> error naming the file ("profile X is
    listed in uncalledProfiles but <file> references <token>; it has a caller");
    text match is deliberate: the same conservative rule mctl-agents' test
    applies, and a mention in a comment is reviewer noise worth flagging;
  - skip the budget lookup and comparison only; the timeout lookup and
    comparison run unchanged.
- `validate_catalog`: pass `uncalled=name in policy.uncalled_profiles`; after
  the profile walk, report every `uncalledProfiles` entry that is not a loaded
  profile name ("stale exemption"). This check runs regardless of `cwft_dir`.

All six existing profiles are not in the list, so their code path is
byte-for-byte the current one.

### 2. Profile `execution-profiles/authoring-canary-default/profile.yaml`

Header comment in the style of `mentor-default`, giving the source of each value
(the #598 manifest and `build_authoring_canary_options`), then:

```yaml
apiVersion: agents.mctl.ai/v1alpha2
kind: ExecutionProfile
metadata:
  name: authoring-canary-default
  owner: platform
spec:
  version: "1.0.0"
  modelPolicyRef:
    task: service_agent
    compatibility: ">=1.0.0 <2.0.0"
  skills: []
  tools: [Read, Glob, Grep]
  policyRef: inert-read-only
  permissions:
    repository: {read: true, branchCreate: false, commit: false,
                 pullRequestCreate: false, merge: false}
    kubernetes: none
    network: approved-providers-only
    mutationScopes: []
  budgetUsd: 0.01
  timeoutSeconds: 3600
  runtime:
    entrypoint: orchestrator.run_authoring_canary:run_authoring_canary
    optionsBuilder: orchestrator.options:build_authoring_canary_options
    sandbox:
      backend: argo
      clusterWorkflowTemplate: mctl-agents-run
      approved: true
  approval:
    requiredBefore: []
  evidence:
    required: []
```

(Written in the repository's block style; flow style above is for brevity.)

Decisions the issue asked to be made explicitly:

- **Sandbox and budget check.** `clusterWorkflowTemplate: mctl-agents-run`
  mirrors the manifest (the field must name an approved, existing template;
  `approvedSandboxes` forces it). No `budgetEnv`: no variable carries the
  canary's budget, and naming one would be false. `budgetUsd: 0.01` is the
  manifest's `execution.budgetUsd` and the builder's value; it is verified
  against the policy ceiling, and its no-caller status is verified by the new
  `uncalledProfiles` check. Nothing is added to any `cwft-*.yaml` or CronWorkflow.
- **Timeout.** The schema requires a positive integer and the validator still
  compares it with the named template's effective timeout. `3600` is
  `cwft-mctl-agents-run.yaml` `spec.activeDeadlineSeconds` -- the only
  wall-clock bound that would apply if the canary ever ran in its nominal
  sandbox, and the value `mentor-default`/`service-agent-default` take from the
  same template. The agent itself has no bound; the comment says so.
- **Policy catalog.** Add `inert-read-only` to `knownPolicies`, with a comment:
  reads the workspace, writes nothing, has no caller. Reusing any existing name
  would overstate the agent (each names a write). The historical
  `read-only-investigation` was removed because it was false for the
  investigator; here "read-only" is true and checked (`tools` equality in
  mctl-agents, all write permissions false, no mutation scopes). No new
  evidence kind: `evidence.required: []` states the canary produces nothing.
  No new mutation scope or approval gate.
- **Network.** `approved-providers-only`: the SDK still calls the model
  provider. `none` would understate it.

### 3. Binding `releases/shadow/authoring-canary.yaml`

Shaped like `releases/shadow/mentor.yaml`:

```yaml
apiVersion: agents.mctl.ai/v1alpha2
kind: ReleaseBindingIntent
metadata:
  agent: authoring-canary
  environment: shadow
spec:
  sourceManifest:
    repo: mctlhq/mctl-agents
    path: agents/_manifests/authoring-canary/agent.yaml
    gitSha: "<#598 head at implementation time; ad4a2b95506bf0d008eaa18a2ba52250e27316fa today>"
    contentHash: "sha256:4af4245df12133259961558f52a409cbf1ca8cca2ed08d5476942c22f62fe513"
  bindingSource: compatibility-fixture
  promotable: false
  registryLifecycle: {definition: published, profile: published}
  definition:
    name: authoring-canary
    version: "1"
    profileCompatibility: ">=1.0.0 <2.0.0"
  profile:
    name: authoring-canary-default
    version: "1.0.0"
  bindingRevision: 1
```

The comment records that `15afef703a2d5dbf23ff64a862e3fbe5cfd54d4e` introduced
the file, that `contentHash` is the pin and `gitSha` is unverified, and that
editing the canary's `agent.yaml` before or after merge requires re-pinning per
mctl-agents `docs/runbooks/agent-yaml-binding-repin.md`. Before committing, the
implementer recomputes the hash:
`gh api "repos/mctlhq/mctl-agents/contents/agents/_manifests/authoring-canary/agent.yaml?ref=<sha>" -q .content | base64 -d | sha256sum`.

### 4. Documentation

`README.md`: add a row for authoring-canary to the effective-value table
(budget source: the manifest, unverifiable against a template by design;
timeout: `activeDeadlineSeconds: 3600`), a short "Profiles with no caller"
subsection describing `uncalledProfiles`, and the new fixtures in the
expectation table.

## Alternatives

1. **Add `AUTHORING_CANARY_BUDGET_USD: "0.01"` to `cwft-mctl-agents-run.yaml`
   and set `budgetEnv`.** Smallest diff, but explicitly forbidden: it puts the
   canary's name in a CWFT (breaks mctl-agents `tests/test_authoring_canary.py`)
   and asserts a budget enforcement that does not exist. Dropped.
2. **New optional profile field (e.g. `runtime.sandbox.uncalled: true`).**
   Self-describing, but it changes the profile shape mctl-agents parses, lets a
   profile exempt itself, and needs a schema change plus a mctl-agents-side
   review. The policy-list keeps the exemption in the policy file a reviewer
   already guards. Dropped.
3. **Point `budgetEnv` at an existing variable / skip the CWFT check by name in
   code.** The first is a false statement that also fails (0.01 vs 5.00); the
   second hardcodes an agent in the validator and verifies nothing. Dropped.
4. **Skip the binding until a caller exists.** Defeats the purpose of the proof
   run (#598's `binding hash` stays `missing`). Dropped.

## Platform impact

- **Runtime:** none. No template, CronWorkflow or Argo object changes; the
  canary is v1alpha1 and never goes through `orchestrator/resolver.py`; no
  ArgoCD-synced manifest changes. Only the release gate reads the new files.
- **Backward compatibility:** `uncalledProfiles` is additive; the six existing
  profiles take the unchanged path. mctl-agents reads only
  `spec.limits.maxService*` from `policy.yaml`, so the new key and policy name
  do not affect it. Its `check_catalog_profiles_match_builders` will start
  checking the new profile; with #598 checked out the mapping and builder exist.
- **Ordering risk:** before #598 merges, mctl-agents main has no
  `authoring-canary-default` mapping, so mctl-agents' `validate_manifest` run
  against mctl-gitops main would report "no entry in _AGENT_BY_CATALOG_PROFILE".
  Mitigation: merge #598 first, or merge both close together; the reviewer
  controls this since the PR is not auto-mergeable.
- **Hash drift:** if #598 edits `agent.yaml` again, the gate reports a mismatch.
  Mitigation: recompute at implementation time and before merge.
- **Exemption abuse:** a scheduled agent added to `uncalledProfiles` would skip
  its budget check. Mitigation: the entrypoint-reference scan fails it as soon
  as any template calls it, and stale entries fail too.
- **Merge control:** the change touches `platform-gitops/agent-platform/**`;
  `auto-merge.yml` already excludes it and CODEOWNERS requires `@mashkovd`.
