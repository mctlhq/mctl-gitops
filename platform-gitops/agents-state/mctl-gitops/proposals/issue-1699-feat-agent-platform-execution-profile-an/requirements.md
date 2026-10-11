# Execution profile and release binding for the inert authoring-canary agent

## Context

mctlhq/mctl-agents#598 (issue mctl-agents#596, proof run for mctl-agents#470)
adds `authoring-canary`, an inert agent: tools `Read`/`Glob`/`Grep` only,
`modelPolicy.task: service_agent`, `budgetUsd: 0.01`, `triggers: []`, and a
nominal sandbox `clusterWorkflowTemplate: mctl-agents-run` that never invokes
it. The mctl-agents release gate (`tools/check_binding_hash.py`
`evaluate_promotion`) promotes an agent only when a `ReleaseBindingIntent` in
`platform-gitops/agent-platform/releases/` pins the sha256 of its exact
`agent.yaml` bytes. That binding, and the `ExecutionProfile` it names, do not
exist yet, so the `binding hash` job on #598 reports `authoring-canary: missing`.

This proposal adds the profile `authoring-canary-default` (1.0.0) and the
binding `releases/shadow/authoring-canary.yaml`. Because the canary has no
caller, `scripts/validate-agent-platform.py`'s effective-value check
(`validate_profile_against_cwft`) cannot accept it as written: the named
template `cwft-mctl-agents-run.yaml` sets three `*_BUDGET_USD` variables and
none of them is the canary's, so every honest profile shape fails. The
proposal therefore also adds the smallest validator change that lets the
catalog state "this profile has no caller" truthfully, with the claim itself
checked, and tests in both directions.

## User stories

- AS the mctl-agents release gate I WANT a binding that pins the exact bytes of
  `agents/_manifests/authoring-canary/agent.yaml` SO THAT the canary release can
  be promoted through the governed path instead of reported `missing`.
- AS a platform reviewer I WANT the canary's profile to state exactly what #598
  ships (read-only tools, $0.01, no writes, no caller) SO THAT the catalog never
  overstates or understates an agent's capability.
- AS a catalog maintainer I WANT the validator to accept "no caller" only when
  it can verify that no template calls the agent SO THAT the exemption cannot
  silently hide an unverified budget on a real, scheduled agent.

## Acceptance criteria (EARS)

- WHEN `scripts/validate-agent-platform.py --selftest` runs on the branch THE
  SYSTEM SHALL report success for the real catalog (7 profiles, 7 release
  intents) and for every valid fixture, and SHALL fail every invalid fixture.
- WHEN the `Validate Manifests` workflow runs on the PR THE SYSTEM SHALL pass.
- THE SYSTEM SHALL provide
  `platform-gitops/agent-platform/execution-profiles/authoring-canary-default/profile.yaml`
  with `metadata.name: authoring-canary-default`, `spec.version: "1.0.0"`,
  `spec.tools: [Read, Glob, Grep]`, `spec.skills: []`,
  `spec.modelPolicyRef.task: service_agent`, `spec.budgetUsd: 0.01`,
  `spec.timeoutSeconds: 3600`, every `permissions.repository` write flag
  (`branchCreate`, `commit`, `pullRequestCreate`, `merge`) false,
  `permissions.kubernetes: none`, `permissions.mutationScopes: []`,
  `approval.requiredBefore: []`, `evidence.required: []`,
  `runtime.entrypoint: orchestrator.run_authoring_canary:run_authoring_canary`,
  `runtime.optionsBuilder: orchestrator.options:build_authoring_canary_options`,
  and `runtime.sandbox` = `argo` / `mctl-agents-run` / `approved: true` with no
  `budgetEnv`.
- THE SYSTEM SHALL provide `platform-gitops/agent-platform/releases/shadow/authoring-canary.yaml`
  shaped like `releases/shadow/mentor.yaml`, with `bindingSource:
  compatibility-fixture`, `promotable: false`, `definition.name:
  authoring-canary`, `profile.name: authoring-canary-default`,
  `profile.version: "1.0.0"`, `bindingRevision: 1`,
  `sourceManifest.path: agents/_manifests/authoring-canary/agent.yaml` and
  `sourceManifest.contentHash:
  "sha256:4af4245df12133259961558f52a409cbf1ca8cca2ed08d5476942c22f62fe513"`.
- WHEN the binding is written THE SYSTEM SHALL set `sourceManifest.gitSha` to a
  #598 commit whose `agent.yaml` bytes hash to exactly that `contentHash`,
  verified by recomputing sha256 at implementation time.
- IF the #598 `agent.yaml` bytes no longer hash to `4af4245d...` at
  implementation time THEN THE SYSTEM SHALL NOT be merged with the old hash; the
  implementer recomputes the hash from the new bytes and records the change.
- WHEN a profile is listed in `policy.yaml` `spec.uncalledProfiles` THE SYSTEM
  SHALL skip only the budgetUsd-vs-CWFT comparison for that profile, and SHALL
  still compare `timeoutSeconds` with the named template's effective timeout.
- IF a profile listed in `uncalledProfiles` declares `runtime.sandbox.budgetEnv`
  THEN THE SYSTEM SHALL report a validation error.
- IF any file under `platform-gitops/argo-workflows/cluster-templates/`
  (ClusterWorkflowTemplates and CronWorkflows alike) contains the module name of
  an uncalled profile's `runtime.entrypoint` THEN THE SYSTEM SHALL report a
  validation error saying the profile has a caller.
- IF `uncalledProfiles` names a profile that does not exist in the catalog THEN
  THE SYSTEM SHALL report a validation error (no stale exemptions).
- WHILE a profile is not listed in `uncalledProfiles` THE SYSTEM SHALL validate
  it exactly as today (all six existing profiles unchanged, same results).
- WHEN `uv run python -m orchestrator.validate_manifest` runs in mctl-agents with
  the #598 branch and this branch checked out THE SYSTEM SHALL pass (the
  catalog-profile check maps `authoring-canary-default` to `authoring-canary`
  and compares tools/model task with `build_authoring_canary_options`).
- WHEN this PR is merged and `binding hash` is re-run on mctlhq/mctl-agents#598
  THE SYSTEM SHALL report `authoring-canary: match`.
- THE SYSTEM SHALL NOT add any reference to the canary (name, entrypoint,
  budget variable, step, parameter) to any `cwft-*.yaml` or `cronworkflow-*.yaml`.
- WHILE the PR touches `platform-gitops/agent-platform/**` THE SYSTEM SHALL NOT
  be merged by automation (already enforced by `.github/workflows/auto-merge.yml`
  and the CODEOWNERS entry `platform-gitops/agent-platform/** @mashkovd`).

## Out of scope

- Any change to an existing profile, existing binding, the promotion gate,
  CODEOWNERS or the ruleset.
- Any workflow, schedule, trigger, budget variable, step or parameter for the
  canary in any ClusterWorkflowTemplate or CronWorkflow.
- `promotable: true` or `bindingSource: registry` (owned by mctl-api#479).
- A `timeoutEnv` counterpart to `budgetEnv`, or any change to how timeouts are
  read from templates.
- Changes in mctlhq/mctl-agents (the `_AGENT_BY_CATALOG_PROFILE` mapping for
  `authoring-canary-default` already exists on #598).

## Open questions

- Which `gitSha` to record. The issue says "the head of #598 that carries that
  file" and names `15afef703a2d5dbf23ff64a862e3fbe5cfd54d4e` as the commit that
  introduced it. At investigation time the #598 head is
  `ad4a2b95506bf0d008eaa18a2ba52250e27316fa`, and the file hashes to
  `4af4245d...` at both. This proposal records the #598 head at implementation
  time (after recomputing the hash there) and names `15afef7` in the comment.
  If #598 is squash-merged, the branch SHA may later become unreachable; as with
  `mentor.yaml`, nothing verifies `gitSha` and `contentHash` is the pin, so this
  is cosmetic, but a reviewer may prefer re-pinning `gitSha` to the merge commit
  in a follow-up.
- The new `policyRef` name. No existing `knownPolicies` entry fits an agent that
  writes nothing (`scoped-proposal-authoring`, `digest-authoring` and the others
  all name a write). This proposal adds `inert-read-only`; the reviewer may
  prefer another name.
- `permissions.network`. The issue does not specify it. The canary still calls
  the model provider, so `approved-providers-only` (as in `mentor-default`) is
  the truthful value; `none` would understate what the process does.
