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

Four more profiles were added for mctl-agents#470
(`incident-responder-default`, `mentor-default`, `service-agent-default`,
and later `authoring-canary-default`), under the same rule. All four name
`mctl-agents-run`. The first three run there, which is why each names its own
budget variable in `sandbox.budgetEnv` (see "Effective values are checked
against the deployed template" below); authoring-canary has no caller and
names none (see "Profiles with no caller" below):

| Agent | budgetUsd | timeoutSeconds | Source |
|---|---|---|---|
| incident-responder | 20.00 | 3600 | `cwft-mctl-agents-run.yaml` `INCIDENT_RESPONDER_BUDGET_USD` -- the CWFT override wins over the Python default ($5); no per-agent timeout exists, so `activeDeadlineSeconds: 3600` is the effective ceiling |
| mentor | 10.00 | 3600 | `cwft-mctl-agents-run.yaml` `MENTOR_BUDGET_USD`; `activeDeadlineSeconds: 3600` |
| service-agent | 5.00 | 3600 | `cwft-mctl-agents-run.yaml` `SERVICE_AGENT_BUDGET_USD`, per service run; `activeDeadlineSeconds: 3600` |
| authoring-canary | 0.01 | 3600 | The agent's `agent.yaml` `execution.budgetUsd`; no template carries it (see "Profiles with no caller"). `activeDeadlineSeconds: 3600` |

Those four agents are `agents.mctl.ai/v1alpha1` and never go through the
runtime resolver, so nothing reads their profiles or bindings at run time.
They exist for mctl-agents' production promotion gate
(`tools/check_binding_hash.py` `evaluate_promotion`), which refuses to
promote a release whose `agent.yaml` does not hash to the binding's
`spec.sourceManifest.contentHash`. Editing one of those `agent.yaml` files
therefore needs its binding re-pinned here first; the procedure is
mctl-agents `docs/runbooks/agent-yaml-binding-repin.md`.

#### Profiles with no caller

`authoring-canary` (mctl-agents#596/#598) is inert: no ClusterWorkflowTemplate
or CronWorkflow runs it, so no template holds its budget. A profile listed in
`policy.yaml` `spec.uncalledProfiles` skips only the `budgetUsd` comparison
with the template; `timeoutSeconds` is still compared. The claim is checked,
not trusted: the profile must not declare `sandbox.budgetEnv`; no file under
`argo-workflows/cluster-templates/` (templates and CronWorkflows) may contain
the entrypoint module or the agent's name in snake, kebab or upper case
(`run_authoring_canary`, `authoring_canary`, `authoring-canary`,
`AUTHORING_CANARY`); an unreadable template fails the exemption; and an entry
naming no profile is an error. Giving the agent a caller means removing it
from the list and declaring `budgetEnv` in the same PR.

What this repository cannot see: a call made inside the orchestrator. The
`mctl-agents-run` template runs `python -m orchestrator.run_all`, which
dispatches to several agents that no template names. Wiring the canary in as
a new `run_all` mode would change no file here. That direction is guarded in
mctl-agents: `tests/test_authoring_canary.py` fails when any module under
`orchestrator/`, `tools/` or `config/` names the entrypoint, and a manifest
change there needs a human merge.

Any future profile bump must state which side (Python default vs. deployed
CWFT override) it is changing, and why -- silently reverting to the Python
default would be a behavior change this issue is explicitly scoped not to
make.

## Production dependency

Every `ReleaseBindingIntent` fixture under `releases/` today has
`spec.bindingSource: compatibility-fixture` and `spec.promotable: false`.
There is no real mctl-api-published v1alpha2 version of any of these
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
| several budget variables and no `budgetEnv` rejected | `invalid/cwft-several-budgets-without-budget-env/` |
| `budgetEnv` reads the named variable, not another one | `invalid/cwft-budget-env-mismatch/` |
| `budgetEnv` naming a variable the CWFT does not set rejected | `invalid/cwft-budget-env-not-set/` |
| `budgetEnv` variable set twice with different values rejected, whichever value the profile declares | `invalid/cwft-budget-env-conflicting-values-declares-first/`, `...-declares-second/` |
| `budgetEnv` must be a `*_BUDGET_USD` name | `invalid/budget-env-not-a-budget-variable/` |
| `budgetEnv` selects one of several budget variables | `valid/cwft-budget-env-selects-one-of-several/` |
| exact-pair rollback accepted | `valid/rollback-replay/` |
| uncalled profile skips only the budget comparison | `valid/uncalled-profile-without-budget-env/` |
| uncalled profile with a caller in a template rejected | `invalid/uncalled-profile-with-caller/` |
| uncalled profile named by agent, not module, rejected | `invalid/uncalled-profile-with-caller-by-agent-name/` |
| uncalled profile naming `budgetEnv` rejected | `invalid/uncalled-profile-with-budget-env/` |
| uncalled profile's timeout still checked | `invalid/uncalled-profile-timeout-mismatch/` |
| stale `uncalledProfiles` entry rejected | `invalid/uncalled-profiles-stale-entry/` |
| profile not listed in `uncalledProfiles` validated as before | `invalid/unlisted-profile-without-budget-env/` |

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

A template that runs one agent sets one `*_BUDGET_USD` variable, and the
check finds it by suffix. `mctl-agents-run` runs three agents and sets three,
and the check refuses to pick among them. A profile for such a template names
its variable in `spec.runtime.sandbox.budgetEnv`, and `budgetUsd` is then
compared with that variable alone. The field only says which variable is
checked. It configures nothing, and no agent reads it.

Nothing here checks that a profile names its own agent's variable. Which
variable an agent reads is decided in mctl-agents (`budgetEnv` in its
`docs/agent-inventory.yaml`). By convention it is the agent's name in upper
snake case plus `_BUDGET_USD`, and all six deployed variables follow that, so
a new profile should too. The convention is not enforced: an agent may
legitimately read a differently named variable, and a check built on the
name would then refuse a correct profile.

There is no `timeoutEnv` counterpart. `mctl-agents-run` sets no
`*_TIMEOUT_SECONDS` today, so its three profiles all take
`activeDeadlineSeconds`. Adding a per-agent `*_TIMEOUT_SECONDS` to a template
that several profiles name needs that counterpart first: one such variable
would be read as the timeout of every profile naming the template, and two
would fail them all as ambiguous.

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
bump. The capability is live: the investigator CWFT sets
`ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative` (owner decision 2026-10-04),
and since mctl-agents 1.66.0 (#558) a plan that grants it lets the
investigator seal one clarification question per round. A second, coarser
off switch is setting that env var back to `legacy` in the CWFT, which
skips the catalog entirely.

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

This catalog is runtime-load-bearing in production: the investigator CWFT
runs `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`, so every investigation
resolves its plan from it, and a broken binding or profile fails every run
closed. The immediate operational rollback is setting that env var to
`legacy` in the CWFT. The resolver itself does read it, and
fails closed on what it reads (see the two sections above). Reverting the commit that introduced it would now
break investigations unless the CWFT is switched back to `legacy` first. Once real registry-backed bindings exist,
operational rollback always selects the exact previous registry tuple
(`mctl_rollback_agent`'s existing "revert to from_version" semantics),
never an independently chosen pair -- exactly what
`invalid/rollback-independent-half/` and `valid/rollback-replay/` pin down
here ahead of that integration.
