# Design: issue-227-feat-agent-platform-resolve-execute-agen

## Current state

Read directly in this clone:

- `orchestrator/manifest.py` — loads `agents/_manifests/*/agent.yaml`
  (`apiVersion: agents.mctl.ai/v1alpha1`) into a flat `AgentManifest`
  dataclass: `runtime.{entrypoint,optionsBuilder}`, `prompt.sources`,
  `modelPolicy.{task,legacyEnvOverride}`, `toolPolicy.allow`,
  `execution.{budgetUsd,timeoutSeconds,sandbox}`. `load_all()` treats a
  duplicate `metadata.name` as a hard error, not a version conflict — there
  is no version field on the resource at all today.
- `orchestrator/validate_manifest.py` — resolves each manifest's
  `optionsBuilder` reference and calls it with dummy args, then diffs the
  YAML's `toolPolicy.allow`/`execution.budgetUsd`/`execution.timeoutSeconds`/
  `modelPolicy.legacyEnvOverride` against what
  `orchestrator/options.py`'s real `build_*_options()` function actually
  does — a checked claim, not a second implementation. This is the exact
  pattern the ADR's migration path (step 4: "resolve the combined claim...
  and prove it equals the legacy options-builder behavior") reuses.
- `agents/_manifests/issue-investigator/agent.yaml` — the investigator's
  current v1alpha1 manifest: `entrypoint:
  orchestrator.run_issue_investigator:investigate`,
  `optionsBuilder: orchestrator.options:build_issue_investigator_options`,
  one inline prompt source
  (`orchestrator/run_issue_investigator.py:_build_prompt`),
  `modelPolicy.task: service_agent` with
  `legacyEnvOverride: ISSUE_INVESTIGATOR_MODEL`, a 7-tool allow-list, and
  `execution.{budgetUsd: 3.00, sandbox.backend: argo,
  sandbox.clusterWorkflowTemplate: mctl-agents-investigate}`.
- `orchestrator/options.py:build_issue_investigator_options(repo_dir, model,
  proposal_dir)` — the real source of truth: builds `ClaudeAgentOptions`
  with `cwd=repo_dir`, `setting_sources=["project"]`,
  `allowed_tools=["Read","Write","Edit","Glob","Grep","WebSearch","WebFetch",
  "Bash", *_mctl_tool_globs()]`, `mcp_servers=mctl_mcp_config(...)`,
  `permission_mode="acceptEdits"`,
  `max_budget_usd=ISSUE_INVESTIGATOR_BUDGET_USD`, `add_dirs=[proposal_dir]`,
  `env={...,"PROPOSAL_DIR":...}`, `hooks=_command_audit_hooks()`.
- `orchestrator/run_issue_investigator.py:investigate()` — the driver:
  resolves `INVESTIGATOR_MODEL = os.getenv("ISSUE_INVESTIGATOR_MODEL",
  SERVICE_AGENT_MODEL)` once at import time, then in
  `_run_agent()` calls `build_issue_investigator_options(repo_dir,
  INVESTIGATOR_MODEL, proposal_dir)` and drives `ClaudeSDKClient` directly.
  Idempotency guard, `.status.yaml` `source` block, and the GitHub proposal
  comment all live here, untouched by this proposal.
- `orchestrator/temporal/activities/registry.py:resolve_agent_release(agent,
  environment)` — already resolves the **container image** version released
  to an environment via `GET /api/v1/agents/{agent}/resolve` +
  `GET /api/v1/agents/{agent}/versions` against mctl-api, returning `None`
  (not an error) when nothing was ever promoted — a legacy-compatible
  fallback to the CWFT's own baked-in default image. This is a real, already
  -shipped piece of "resolution", but it only pins the *image*, not the
  model/tools/budget/policy the ADR's `ExecutionProfile` covers.
- `orchestrator/temporal/activities/state.py:record_execution(record)` —
  posts `ExecutionRecord` (`agent, environment, version, image_ref,
  target_repo, argo_workflow_name, phase`) to
  `POST /api/v1/agents/executions`. This is mctl-api's existing audit
  contract; unchanged by this proposal.
- `orchestrator/temporal/workflows/dev_loop.py:DevLoopWorkflow.run()` — calls
  `_resolve("issue-investigator")` **before** `_run_cwft("mctl-agents-
  investigate", ...)`, i.e. release resolution already happens before Argo
  submission for the image tag; `_record(...)` writes the audit row right
  after the CWFT completes. This is the natural insertion point for a
  second, richer resolution step.
- `docs/adr/007-agent-definition-execution-profile-contract.md` — accepted
  2026-08-29 against this issue and `mctlhq/mctl-gitops#950`. Fixes the
  target contract (`AgentDefinition`, `ExecutionProfile`, atomic
  `ReleaseBinding`, immutable `ExecutionPlan`, lifecycle states, fail-closed
  v1alpha2 rules, legacy-only v1alpha1 fallback) and explicitly assigns this
  issue: "immutable `ExecutionPlan`, legacy-only fallback, v1alpha2
  pre-submit rejection, exact resolved tuple and execution identity." It
  also states production catalog activation is blocked on `#950`, and that
  `#227` "may implement and test the resolver against checked-in
  compatibility fixtures" in the meantime.
- `docs/agent-inventory.yaml` — classifies `issue-investigator` as the
  cheapest agent to version (its cwd is a throwaway clone of the *target*
  repo, so this repo's own prompt contribution is exactly one inline
  template) — the documented reason it is "the phase-4 pilot" for the prior
  Temporal/registry slice, and the natural reason to pick it again as the
  first `execute(agent, task)` pilot here.
- `config/model_policy.py` / `config/model-policy.yaml` — a *separate*,
  narrower "profile" concept (`cheap`/`balanced`/`strong` model tiers keyed
  by `tasks.service_agent: balanced`). ADR-007 explicitly does not rename
  this; the new `ExecutionProfile.modelPolicyRef` wraps it rather than
  replacing it.

## Proposed solution

Implement `execute(agent, task) -> ExecutionPlan` entirely inside
`mctl-agents`, as a new `orchestrator/resolver.py` module, and migrate only
`issue-investigator` to consume it behind a flag. No new mctl-api endpoint,
no new workflow engine, no change to Argo/Temporal's roles.

### 1. v1alpha2 schema alongside v1alpha1 (`orchestrator/manifest.py`)

Extend `orchestrator/manifest.py` to recognize a second `apiVersion`,
`agents.mctl.ai/v1alpha2`, without touching v1alpha1 parsing:

- `AgentDefinition` (new dataclass): `name`, `owner`, `purpose`,
  `prompt_sources`, `runtime_context_inputs`, `triggers`,
  `execution_profile_ref: {name, compatibility}`. Parsed from
  `agents/_manifests/<agent>/agent.yaml` when `apiVersion ==
  agents.mctl.ai/v1alpha2` (the file keeps its existing path; only its
  schema version and content change for a migrated agent).
- `ExecutionProfile` (new dataclass): `name`, `model_policy_ref`, `skills`,
  `tools`, `policy_ref`, `permissions`, `budget_usd`, `timeout_seconds`,
  `runtime` (`entrypoint`, `options_builder`, `sandbox.backend`,
  `sandbox.cluster_workflow_template`), `approval`, `evidence`. Parsed from
  a new mirrored location, `agents/_profiles/<profile-name>/profile.yaml` —
  same one-directory-per-resource convention `agents/_manifests/` already
  uses, so `validate_manifest.py`'s existing glob-and-validate shape extends
  without inventing a new layout.
- `load_all()` keeps returning v1alpha1 `AgentManifest` for every
  unmigrated agent; a new `load_all_v1alpha2()` (or a `version` field on a
  shared return type) returns `AgentDefinition` for migrated ones. Unknown
  `apiVersion` values continue to fail loudly (`ManifestError`), per ADR-007
  ("v1alpha1 remains supported... unknown API versions fail loudly").
- `agents/_manifests/issue-investigator/agent.yaml` is rewritten to
  v1alpha2, `executionProfileRef: {name: investigator-default,
  compatibility: ">=1.0.0 <2.0.0"}` (an illustrative semver-range
  constraint — exact syntax is a small parsing decision, not a design fork).
  `agents/_profiles/investigator-default/profile.yaml` is authored to carry
  exactly today's values: `modelPolicyRef.task: service_agent`,
  `tools: [Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Bash,
  "mcp__mctl__*"]`, `budgetUsd: 3.00`, `runtime.optionsBuilder:
  orchestrator.options:build_issue_investigator_options`,
  `runtime.sandbox.clusterWorkflowTemplate: mctl-agents-investigate`,
  `approval: none` (investigation never mutates beyond its own proposal
  path), `evidence: [proposal_triplet, status_yaml_source_block,
  github_comment]` — the ADR's "Mapping the three named agents" table row
  for `issue-investigator`, made literal.

### 2. Checked-in compatibility fixtures stand in for the not-yet-built catalog

Because `#950` (mctl-gitops catalog-schema, atomic `ReleaseBinding`) is not
built, `execute()` cannot call a live mctl-api endpoint for
definition/profile versions or a `ReleaseBinding`. Instead, a new
`tests/fixtures/resolver/issue-investigator.release.yaml` (git-reviewed,
deterministic) plays the role of one `ReleaseBinding` row:

```yaml
environment: production
definition: {name: issue-investigator, version: <content-hash of agent.yaml>}
profile: {name: investigator-default, version: <content-hash of profile.yaml>}
revision: 1
```

`orchestrator/resolver.py` computes `definition.version` /
`profile.version` itself (sha256 of the resolved YAML bytes, truncated —
see requirements.md's Open Questions) and asserts it matches the fixture's
recorded value; a fixture that has drifted from the real file (i.e., the
file changed but the fixture wasn't regenerated) is exactly the "ambiguous
reference" case the ADR requires to fail closed, so this doubles as a
regression guard against unreviewed profile/definition drift. This is
explicitly a **pilot-only compatibility shim**: `resolver.py` is written so
that swapping the fixture read for a real mctl-api `ReleaseBinding` call is
a single function's implementation change (`_resolve_release_binding`),
not a rewrite of `execute()`'s contract — the seam `#950`'s production
cutover needs.

### 3. `execute(agent, task) -> ExecutionPlan`

```python
@dataclass(frozen=True)
class ExecutionTask:
    kind: str                 # "investigate" for this pilot
    payload: dict[str, Any]   # e.g. {"issue_url": ...}
    environment: str = "production"

@dataclass(frozen=True)
class ExecutionPlan:
    agent: str
    definition_version: str
    profile_version: str
    release_revision: int
    model: str
    model_policy_source: str      # mirrors ModelSelection.source
    prompt_hash: str               # hash of the resolved prompt sources
    tools: tuple[str, ...]
    budget_usd: float
    timeout_seconds: float | None
    sandbox_backend: str
    cluster_workflow_template: str
    approval_required: bool
    evidence: tuple[str, ...]
    options_builder: str
    entrypoint: str

def execute(agent: str, task: ExecutionTask) -> ExecutionPlan: ...
```

`execute()`:

1. Loads the v1alpha2 `AgentDefinition` for `agent` (`ManifestError` if
   missing/unparseable — "missing" case).
2. Loads the referenced `ExecutionProfile` and checks
   `execution_profile_ref.compatibility` against the profile's own declared
   version range ("incompatible" case) and that neither resource is marked
   `disabled` in the fixture ("disabled" case — the fixture format carries a
   `status: published|deprecated|disabled` field per resource, mirroring
   ADR-007's version lifecycle table).
3. Resolves the release binding from the checked-in fixture for
   `task.environment` ("ambiguous"/missing-release case if no fixture row
   matches).
4. Resolves the concrete model via the *existing*
   `config/model_policy.py:ModelPolicy` using `profile.model_policy_ref.task`
   — reused, not reimplemented, so model-selection semantics are provably
   unchanged.
5. Computes `prompt_hash` over the definition's `prompt_sources` (same set
   `validate_manifest.py._check_prompt_sources` already resolves).
6. Returns the immutable `ExecutionPlan`.

All five failure branches raise a single `ResolutionError(ValueError)`
subclass carrying which check failed and the offending reference name — the
"actionable errors" requirement — and `execute()` never partially applies a
plan.

### 4. Wiring `ExecutionPlan` into the investigator (compatibility flag)

`orchestrator/options.py:build_issue_investigator_options()` keeps its
existing signature and behavior (nothing else may regress). A thin new
`build_issue_investigator_options_from_plan(repo_dir, plan, proposal_dir)`
wraps it, substituting `plan.model`/`plan.tools`/`plan.budget_usd` for the
constants the current function reads from its own module scope, and is
proven equal by a golden test (below) rather than duplicating construction
logic — it calls the same underlying `ClaudeAgentOptions(...)` shape with
values taken from `plan` where the legacy function takes them from
`INVESTIGATOR_MODEL`/`ISSUE_INVESTIGATOR_BUDGET_USD`/its own literal tool
list.

`orchestrator/run_issue_investigator.py:investigate()` reads
`ISSUE_INVESTIGATOR_RESOLVER_MODE` (env var, default `"legacy"`) once:

- `"legacy"` (default): today's code path, byte-for-byte unchanged —
  `_run_agent()` calls `build_issue_investigator_options(repo_dir,
  INVESTIGATOR_MODEL, proposal_dir)` exactly as now.
- `"declarative"`: `investigate()` calls `execute("issue-investigator",
  ExecutionTask(kind="investigate", payload={"issue_url": issue_url}))`
  before cloning the target repo (so a resolution failure — missing/
  disabled/incompatible profile — aborts *before* the network clone, the
  Argo submission, and any spend, matching the "reject before submitting
  execution" requirement even though this particular submission already
  happens after Temporal's own Argo dispatch for the CWFT itself — see
  Platform impact below for the two-layer submission point this implies),
  then drives `_run_agent()` through
  `build_issue_investigator_options_from_plan(...)`. On `ResolutionError`,
  `investigate()` returns an `InvestigateResult(error=...)` exactly like
  today's other failure branches — no new exception type escapes to
  callers, preserving the `mctl_trigger_issue`/`mctl-agents-investigate`
  contract.
- Any other value: fail loudly at import time (`SystemExit`) — not a silent
  fallback to legacy, since a typo'd flag silently running unaudited legacy
  behavior would defeat the flag's purpose.

`orchestrator/temporal/workflows/dev_loop.py` is **not required** to change
for this pilot: `DevLoopWorkflow` already resolves the image version and
submits the CWFT; the new resolution step runs *inside* the Argo pod when
the CWFT's driver container invokes `run_issue_investigator.investigate()`
with the flag set, which is sufficient to prove and test the pilot without
touching the Temporal workflow's determinism-sensitive command sequence (a
change there is easy to get wrong — see `dev_loop.py`'s own extensive
`workflow.patched(...)` comments on why every command reordering there is
high-risk). A follow-up (tracked as an open item, not blocking this issue)
can move resolution one layer earlier, into a new Temporal activity that
runs `execute()` before `_run_cwft("mctl-agents-investigate", ...)`, once
the pilot is proven — at that point "before Argo submission" becomes
literal rather than "before the investigator's own network/spend work
inside the submitted pod."

### 5. Immutable plan snapshot for identity/tracing/evidence

`ExecutionPlan` is a frozen dataclass with a deterministic `to_dict()`
(stable key order) logged once, verbatim, via `print()` at the top of
`_run_agent()`'s declarative branch — visible in the pod's stdout, which
Argo already archives (per `mctl_get_workflow_logs`'s existing "the archive
retains logs far longer than the cluster does" behavior) — so the plan is
independently retrievable without a new storage system. Pushing these
identifiers into mctl-api's `ExecutionRecord` schema is explicitly deferred
(see requirements.md Open Questions) rather than bolted onto
`record_execution`'s existing, mctl-api-owned payload shape.

## Alternatives

1. **Resolve everything through a new mctl-api endpoint now, ahead of
   `#950`.** Rejected: `#950` owns the GitOps catalog schema and atomic
   `ReleaseBinding`; building a parallel, mctl-agents-only endpoint would
   create the exact "three incompatible answers to the same question" risk
   ADR-007's Context section calls out, and would have to be thrown away or
   migrated once `#950` lands. Checked-in fixtures give the same
   test/replay guarantees without a premature API surface.
2. **Skip the `AgentDefinition`/`ExecutionProfile` split for the pilot and
   just add a `version` field to the existing flat `AgentManifest`.**
   Rejected: this is ADR-007's Alternative 1, already rejected there for the
   same reason it would fail here — a budget-only change would still force
   a full definition-version bump, defeating the "profile is reusable and
   independently versioned" requirement the issue explicitly asks for, and
   would leave this issue re-litigating a decision ADR-007 already closed.
3. **Move resolution into `DevLoopWorkflow` immediately, replacing
   `resolve_agent_release`'s call site with `execute()`.** Rejected for this
   slice: `dev_loop.py` is a `@workflow.defn` whose command sequence is
   replay-sensitive (see its own `workflow.patched(...)` history around
   approval ordering and slug scoping) — introducing a new activity call
   there is exactly the kind of command-order change that file's comments
   warn wedges in-flight histories if done carelessly. Proving the resolver
   correct inside the already-isolated, stateless Argo pod first, then
   promoting the call site once `#950` exists and the equivalence tests are
   green, is the lower-risk order; the ADR's own "Downstream sequencing"
   section supports investigating/implementing before promotion regardless.
4. **Make the compatibility flag a manifest field
   (`spec.executionProfileRef.compatibilityMode`) instead of an env var.**
   Rejected for this pilot: every other per-agent runtime override in this
   codebase today (`ISSUE_INVESTIGATOR_MODEL`,
   `ISSUE_INVESTIGATOR_BUDGET_USD`) is an env var read once at driver start
   and is what `validate_manifest.py`'s existing
   `_LEGACY_MODEL_ENV_VAR_BY_AGENT` pattern already knows how to check
   against real code; a manifest-encoded flag would need its own new
   validator branch for no behavioral benefit at pilot scale, and would
   blur the "definition version bumps mean identity/prompt/trigger changed"
   rule from moving a purely operational toggle into versioned content.

## Platform impact

- **Migrations:** additive only. `agents/_manifests/issue-investigator/
  agent.yaml` moves from v1alpha1 to v1alpha2 content, but `orchestrator/
  manifest.py` keeps loading both versions, so every other agent's manifest
  is untouched and `load_all()`'s existing consumers
  (`validate_manifest.py`, `tests/test_manifest.py`,
  `tests/test_agent_inventory.py`) need only accept a mixed v1alpha1/
  v1alpha2 population, not a flag day.
- **Backward compatibility:** default `ISSUE_INVESTIGATOR_RESOLVER_MODE=
  legacy` means zero behavior change for every existing caller
  (`mctl_trigger_issue`, the `mctl-agents-investigate` CWFT, the issue
  poller) until the flag is explicitly flipped, and flipping it back is a
  one-line env change with no code rollback, satisfying the issue's
  "deterministic fallback/rollback" requirement directly.
  `build_issue_investigator_options()` itself is never modified, only
  wrapped, so `validate_manifest.py`'s existing v1alpha1-shaped comparison
  for every other agent keeps working unmodified.
- **Resource impact:** one extra in-process fixture read + hash + model-
  policy lookup per declarative-mode investigator run — no network call,
  negligible compared to the existing `gh repo clone` and SDK turn. No new
  Kubernetes resources, no new mctl-api load.
- **Security:** unchanged tool/MCP access — `ExecutionProfile.tools` is
  declared to be exactly today's `build_issue_investigator_options()` list
  and proven so by the same style of check `validate_manifest.py` already
  runs; per ADR-007, `tools` remains a reviewed least-privilege *claim*, not
  authorization — MCP/GitHub/Kubernetes stay authoritative server-side,
  unchanged by this issue.
- **Risks + mitigations:**
  - *Fixture/reality drift* (a profile file edited without regenerating its
    fixture-recorded hash) — mitigated by `execute()` failing closed on a
    hash mismatch (see "Proposed solution" §2), turned into an explicit
    `test_resolver_fixtures_match_checked_in_definitions` test rather than a
    silent pass.
  - *Declarative/legacy divergence* — mitigated by a golden equivalence
    test (tasks.md T2) asserting `build_issue_investigator_options_from_plan
    (...)` and `build_issue_investigator_options(...)` produce identical
    `ClaudeAgentOptions` for the same repo/proposal-dir inputs.
  - *Flag misconfiguration reaching production silently* — mitigated by
    failing loudly (`SystemExit`) on any `ISSUE_INVESTIGATOR_RESOLVER_MODE`
    value other than the two recognized ones, and by `validate_manifest.py`
    gaining a check that the compatibility flag's default is `legacy` in
    the shipped `config/settings.py`/env defaults (tasks.md T7).
  - *Premature reliance on this pilot's fixture-backed `ReleaseBinding` as if
    it were the real catalog* — mitigated by naming and documenting it
    explicitly as a test/compat-only shim (`tests/fixtures/resolver/`, not
    `config/` or `agents/_manifests/`) and by this proposal's Non-goals
    entry ruling out promoting it to the default without `#950`.
