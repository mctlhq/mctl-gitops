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
| conflicting values for one CWFT variable rejected | `invalid/cwft-conflicting-budget-values/` |
| non-numeric CWFT value degrades to a file-scoped error | `invalid/cwft-non-numeric-budget/` |
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

## Kill switch: `human.request_input`

`issue-investigator-default` lists `human.request_input` in `spec.tools`
(mctl-gitops#1277). It is a capability entry, not an SDK tool: mctl-agents
(`orchestrator/options.py`, mctl-agents#333 / ADR 013) treats the durable
human-clarification primitive as granted only when that exact literal is in
the resolved `ExecutionPlan.tools`, and strips it from the SDK allow-list.
`policy.yaml` lists it under `knownTools` with `category: capability` so the
reference check accepts it.

To turn the capability off, one reviewed PR here is the whole procedure:

1. delete `human.request_input` from the profile's `spec.tools`;
2. bump the profile's `spec.version` (`validate-profile-version-bumps.py`
   rejects an unbumped edit);
3. re-pin `releases/shadow/issue-investigator.yaml`: `profile.version` to the
   new version, advance `bindingRevision`/`previousBindingRevision`, and
   record the old pair in `history` (the resolver fails closed when the
   binding and the profile disagree on the version).

No image build, no CWFT change and no Argo/ArgoCD sync is involved:
`mctl-agents-investigate` shallow-clones `mctl-gitops` `main` in each run's
`clone-gitops` initContainer and points `MCTL_GITOPS_ROOT` at that clone, and
the resolver reads the profile from there. The next run resolved after the
merge gets a plan without the capability. A run that has already resolved
its plan keeps it -- an `ExecutionPlan` is immutable per run.

Turning it back on is the same three steps in reverse, with another version
bump. Two things keep the capability inert today whatever this file says:
the investigator CWFT does not set `ISSUE_INVESTIGATOR_RESOLVER_MODE`, so it
runs in the `legacy` mode, which builds no plan at all; and on mctl-agents
`main` nothing calls `plan_grants_human_input` yet.

## Capability discovery: `capabilityDiscovery`

`issue-investigator-default` carries an optional `spec.capabilityDiscovery`
block (mctl-agents#242 slice 4). It states whether the profile **permits** the
investigator's capability-discovery mode, where the model sees three gateway
tools instead of every `mcp__mctl__*` schema, and which providers discovery
may reach. The field is optional, and leaving it out means `enabled: false`.

Discovery runs only when two things agree: the profile says `enabled: true`,
and the CWFT sets `ISSUE_INVESTIGATOR_CAPABILITY_MODE=discovery`. If the env
var asks for discovery but the profile does not permit it, the run fails
closed with a named `SystemExit`. It never falls back silently.

- **Rollback:** unset the env var. No gitops change or redeploy is needed.
- **Forbidding discovery permanently:** set `enabled: false` in one reviewed
  PR here. This takes the same three steps as the `human.request_input`
  kill switch above: edit the field, bump `spec.version`, and re-pin
  `releases/shadow/issue-investigator.yaml`.

Rules, in the schema and in `validate-agent-platform.py`:

- `endpoint` is a symbolic name that mctl-agents resolves in code
  (`mctl-api-mcp` → `MCTL_MCP_URL`), never a URL. A catalog edit cannot
  point the gateway, or the bearer token it sends, at another host.
- `providers` is ordered. Aliases and `(type, id)` pairs are unique.
- Provider `mctl-api` keeps alias `mctl`, so the gateway's names stay
  `mcp__mctl__<tool>` and still match `spec.tools`.
- `enabled: true` needs at least one provider and `mcp__mctl__*` in
  `spec.tools`.

mctl-agents' resolver (`_parse_capability_discovery`) enforces the same rules
and is authoritative. Its `validate_manifest.py` also checks that a profile
with `enabled: true` gets no wider tool surface in discovery mode than in
eager mode.

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
