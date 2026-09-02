# Agent platform catalog

GitOps half of ADR 007 (`mctlhq/mctl-agents`
`docs/adr/007-agent-definition-execution-profile-contract.md`). This
directory holds the reviewed-in-Git `ExecutionProfile` catalog, the
platform policy that every profile and release intent is checked against,
and non-promotable `ReleaseBindingIntent` fixtures. Everything here is
validated by `scripts/validate-agent-platform.py`, wired into
`.github/workflows/validate-manifests.yml`.

This directory does **not** own, mirror, or replace:

- the canonical `AgentDefinition` body (prompt, triggers, identity) --
  that stays at `mctl-agents/agents/_manifests/<agent>/agent.yaml`, and is
  referenced here only via an exact `sourceManifest {repo, path, gitSha}`;
- immutable published versions, environment `ReleaseBinding` history, or
  `lifecycleState` -- all three live in the mctl-api registry
  (`mctl_publish_agent_version` / `mctl_promote_agent` /
  `mctl_resolve_agent` / `mctl_rollback_agent`);
- the per-run `ExecutionPlan`/`ExecutionRecord` -- that is the runtime
  resolver's job (mctl-agents issue #227), not implemented here.

## Layout

```text
platform-gitops/agent-platform/
  policy.yaml                              policy ceilings + reference catalogs
  execution-profiles/<name>/profile.yaml   agents.mctl.ai/v1alpha2 ExecutionProfile
  releases/<environment>/<agent>.yaml      agents.mctl.ai/v1alpha2 ReleaseBindingIntent
  schemas/execution-profile.schema.json
  schemas/release-binding-intent.schema.json
```

## Source-of-truth boundaries (ADR 007, four layers)

| Layer | Owns | Example |
|---|---|---|
| `mctl-agents` Git | Canonical `AgentDefinition`: identity, prompt sources, triggers, `executionProfileRef` | `agents/_manifests/implementer/agent.yaml` |
| `mctl-gitops` Git (this directory) | `ExecutionProfile` drafts, policy ceilings, `ReleaseBindingIntent` review fixtures | `execution-profiles/implementer-default/profile.yaml` |
| mctl-api registry | Immutable published versions, per-environment `ReleaseBinding` history, lifecycle (published/deprecated/disabled) | `mctl_publish_agent_version`, `mctl_promote_agent`, `mctl_resolve_agent` |
| Runtime resolver / Temporal / Argo | One frozen `ExecutionPlan` per run; the actual execution | `orchestrator/resolver.py` (mctl-agents #227), Argo Workflow object |

A file existing under `execution-profiles/` or `releases/` means only
"drafted, reviewed in Git" -- the `draft` state. Nothing in this
directory can ever mark a version `published`, `active`, `deprecated`, or
`disabled`; that authority belongs entirely to the mctl-api registry, and
`active` is itself derived from an environment binding, never stored as a
field. This is why neither JSON Schema in `schemas/` permits a
`lifecycleState` property anywhere -- see
`scripts/tests/fixtures/agent-platform/invalid/global-lifecycle-state/`
for the negative fixture that proves it fails closed.

## Effective-value extraction

The three initial profiles (`issue-investigator-default`,
`implementer-default`, `shepherd-default`) are migrated to be
behavior-preserving, not re-litigated. Their `budgetUsd`/`timeoutSeconds`
come from the values actually enforced in production today, which is not
always the `orchestrator/options.py` Python default:

| Agent | budgetUsd | timeoutSeconds | Source |
|---|---|---|---|
| issue-investigator | 3.00 | 7200 | `cwft-mctl-agents-investigate.yaml` `ISSUE_INVESTIGATOR_BUDGET_USD`; no per-op timeout override exists, so the CWFT's `activeDeadlineSeconds: 7200` is the effective ceiling |
| implementer | 20.00 | 2400 | `cwft-mctl-agents-implement.yaml` `IMPLEMENTER_BUDGET_USD` / `IMPLEMENTER_TIMEOUT_SECONDS` -- these CWFT overrides win over the Python defaults ($3 / 900s) |
| shepherd | 5.00 | 7200 | `cwft-mctl-agents-shepherd.yaml` `SHEPHERD_BUDGET_USD` (raised from the Tier 3 spec's $1.00 default); no per-tick timeout override exists, so `activeDeadlineSeconds: 7200` is the effective ceiling |

Any future profile bump must state which side (Python default vs. deployed
CWFT override) it is changing, and why -- silently reverting to the Python
default would be a behavior change this issue is explicitly scoped not to
make.

## Production dependency

Every `ReleaseBindingIntent` fixture under `releases/` today has
`spec.bindingSource: compatibility-fixture` and `spec.promotable: false`.
There is no real mctl-api-published v1alpha2 version of any of these three
agents or profiles yet -- that publish step, and the runtime resolver that
would actually consume a real binding (mctl-agents #227), are both
follow-up work. Until they land:

- these fixtures can never be promoted to production by anything reading
  this directory (`scripts/validate-agent-platform.py` rejects any
  `compatibility-fixture` binding with `promotable: true` as inconsistent);
- no running agent, CWFT, or mctl-api schema changes as a result of this
  catalog existing;
- the `history`/`rollbackOf` fields on each intent exercise exact-pair
  rollback semantics against a local fixture ledger only, standing in for
  what will eventually be real mctl-api `ReleaseBinding` history once
  registry reconciliation exists.

## Validation

```bash
python3 -m pip install --quiet pyyaml jsonschema
scripts/validate-agent-platform.py             # real catalog only
scripts/validate-agent-platform.py --selftest  # + replay scripts/tests/fixtures/agent-platform/
```

`--selftest` asserts every fixture under
`scripts/tests/fixtures/agent-platform/valid/` passes and every fixture
under `.../invalid/` fails, one fixture per ADR 007 validation
expectation:

| ADR 007 expectation | Fixture |
|---|---|
| owner required | `invalid/missing-owner/` |
| policyRef required | `invalid/missing-policy-ref/` |
| permissions required | `invalid/missing-permissions/` |
| bounded budget/timeout present | `invalid/missing-bounds/` |
| budget ceiling enforced | `invalid/budget-exceeds-ceiling/` |
| unknown tool fails closed | `invalid/unknown-tool/` |
| unknown skill fails closed | `invalid/unknown-skill/` |
| unknown model-policy task fails closed | `invalid/unknown-model-policy-task/` |
| mutation requires scope + approval | `invalid/mutation-without-approval/` |
| unapproved sandbox rejected | `invalid/unapproved-sandbox/` |
| no global lifecycleState field | `invalid/global-lifecycle-state/` |
| unknown release-intent profile reference fails closed | `invalid/release-missing-profile/` |
| ambiguous profile version rejected | `invalid/release-ambiguous-profile/` |
| incompatible profile version rejected | `invalid/release-incompatible-version/` |
| disabled version rejected | `invalid/release-disabled-version/` |
| independent-half rollback rejected | `invalid/rollback-independent-half/` |
| effective budget/timeout match the CWFT | `invalid/cwft-budget-mismatch/` |
| exact-pair rollback accepted | `valid/rollback-replay/` |

### Effective values are checked against the deployed template

Every profile header claims to "preserve today's effective values", and
until 2026-09-02 nothing checked it. `budgetUsd` and `timeoutSeconds` are
now compared against the ClusterWorkflowTemplate the profile itself names
in `spec.runtime.sandbox.clusterWorkflowTemplate` — the template file is
derived from that field rather than from a profile→template table, because
a table would be a third place able to drift from the other two.

The comparison is against the **CWFT**, never against mctl-agents' Python
defaults, and that distinction is load-bearing: `implementer-default`
correctly declares `$20.00` because `cwft-mctl-agents-implement.yaml` sets
`IMPLEMENTER_BUDGET_USD` to `"20.00"`, while `orchestrator/options.py`
defaults to `$3.00`. A check written against the defaults would fire
immediately and be wrong.

For timeouts: a `*_TIMEOUT_SECONDS` env var wins when present, otherwise
the workflow-level `spec.activeDeadlineSeconds` is the effective timeout —
which is what the investigator and shepherd headers already state.

The check runs only against the real catalog, or against a fixture that
ships its own `cluster-templates/`. The other fixtures name real CWFTs
(`approvedSandboxes` forces that) while carrying made-up budgets, so
checking them against the deployed templates would fail them for the wrong
reason.

**The tool allow-list is deliberately not checked here.** It has to call
the real `orchestrator/options.py` builders, so it lives in mctl-agents'
`orchestrator/validate_manifest.py` (mctl-agents#277). Between the two,
every field this catalog asserts about a running agent is now compared to
the thing that actually runs.

## Rollback

This catalog is additive and not runtime-load-bearing -- nothing resolves
against it yet. Reverting the commit that introduced it removes the
catalog, schemas, validator, and CI step with no effect on any running
agent, CWFT, or mctl-api state. Once real registry-backed bindings exist,
operational rollback always selects the exact previous registry tuple
(`mctl_rollback_agent`'s existing "revert to from_version" semantics),
never an independently chosen pair -- exactly what
`invalid/rollback-independent-half/` and `valid/rollback-replay/` pin down
here ahead of that integration.
