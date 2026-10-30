# Design: issue-694-feat-runtime-assurance-define-assurance

## Current state

The repo has no assurance code (`grep -ri assurance` over `*.py`/`*.md` finds
nothing). It does have a well-established pattern for sealed governance
contracts. Each one is a pure, stdlib-only module of frozen dataclasses, with
`from_dict`/`to_dict`, unknown-key rejection, closed vocabularies, bounded
strings, a `sha256:` content hash and an id derived from that hash:

- `orchestrator/execution_identity.py` (ADR 011, #196): `ExecutionContext`, `API_VERSION = "identity.mctl.ai/v1alpha1"`, `context_id` prefix `ex-`, `seal()`/`recompute_content_hash()`.
- `orchestrator/execution_evidence.py` (ADR 018, #199/#520): `ExecutionEvidence`, `API_VERSION = "evidence.mctl.ai/v1alpha1"`. Reusable blocks: `ExecutionJoin` (`we_` work execution and `ex-` runtime execution), `PolicyDecisionRef`, `ApprovalRef` (`aar_` + `intent_hash`), `ArtifactRef`, `VersionPins` (ADR 007 pins; `definition_content_hash` load-bearing), `SubjectRef` (revision-bound), `Provenance` with `AUTHORITIES = ("observed", "derived", "asserted")`, `Gap` with `observation_failed` ("an unknown, never an observed absence"), and `MAX_TOOL_CALLS = 256`.
- `orchestrator/policy_checkpoint.py` (ADR 014, #197): `ActionRequest`, `Decision`, `ACTION_KINDS`, `VERDICTS`, `UNDECIDED_CODES`. This is the only policy engine.
- `orchestrator/action_approvals.py` (#198): `ActionIntent`, `intent_hash()`, `ApprovalRecord`. This is the durable approval store client.
- `orchestrator/context_snapshot.py`: `hash_bytes`/`canonical_json`, "the one `sha256:`-prefixed content-hash rule".
- `orchestrator/redaction.py`: `contains_credential`, `safe_scalar`, the one credential-shape screen.
- `orchestrator/implementation_completion.py` (ADR 021, #428): the most recent example of the pattern. It has closed outcome/stop-reason vocabularies, `MAX_*` bounds, `_UNHASHED` fields, `redact_text`, and a module docstring that states it "defines no field that could express approval ...". Tests in `tests/test_implementation_completion.py` check stdlib-only imports via `ast`. `tests/test_execution_evidence.py` (T9, `_FORBIDDEN_TOKENS = ("allow", "deny", "permit", "grant", "authorized")`) checks that the module carries no authority vocabulary.
- Golden fixtures live per contract under `tests/fixtures/<contract>/` (e.g. `tests/fixtures/evidence/`).
- ADRs are numbered under `docs/adr/`. The highest is `021-implementation-completion-contract.md`.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-agents-worker)`: base-service, image tag `1.84.0`, no database.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image tag `1.84.0`. Sibling services: `mctl-agents-worker-exec` and `mctl-agents-worker-implement`.
- No deployed configuration refers to assurance. This slice adds a pure library module and changes no deployment, env var, queue or chart, so the deployed state constrains nothing here.

## Proposed solution

### New module `orchestrator/runtime_assurance.py`

The module is pure and stdlib-only, mirroring `implementation_completion.py`. It
imports only `re`, `dataclasses`, `collections.abc` and `typing`, plus these
intra-repo modules, so that no rule is duplicated:

- `context_snapshot.hash_bytes`/`canonical_json` (the hashing rule);
- `redaction.contains_credential` (the credential screen);
- `execution_evidence.ExecutionJoin`, `VersionPins`, `PolicyDecisionRef`, `ApprovalRef`, `ArtifactRef`, `AUTHORITIES`, `MAX_TOOL_CALLS` (reused blocks and vocabularies);
- `policy_checkpoint.ACTION_KINDS`, `MCP_TOOL_CALL` (the action-kind vocabulary).

The module does no I/O and no persistence, and has no runner wiring.

`API_VERSION = "assurance.mctl.ai/v1alpha1"`. There is one `SUPPORTED_API_VERSIONS`
map per kind, and the module defines one error class, `RuntimeAssuranceError(ValueError)`.

#### `AssuranceScenario` (kind `AssuranceScenario`, id `asc-<16hex>`)

| Field | Type / rule | Authority |
|---|---|---|
| `name`, `version` | slug, bounded version token; `(name, version)` is the catalog key | authoritative (author, PR-reviewed) |
| `description` | bounded text, credential-screened | authoritative |
| `target` | `TargetBoundary{kind ∈ {repository, mctl_service, mcp_capability, fixture}, ref (no `*`, `?`, `[`; bounded), environment ∈ {fixture, shadow, production}, allowlist_entry: AllowlistEntryRef?}` | authoritative |
| `setup` | tuple of `SetupStep{step_id, kind ∈ {fixture_load, state_seed, noop}, fixture_ref: sha256}`; no commands | authoritative |
| `inputs` | ≤ 32 `InputSpec{name, kind ∈ {literal, fixture_ref}, value (literal: bounded, credential-screened) / content_hash (fixture_ref)}` | authoritative |
| `invariants` | 1-16 `InvariantSpec{invariant_id, statement (bounded), check_kind ∈ {deterministic_check, policy_decision_expected, evidence_present}}` | authoritative |
| `budgets` | `Budgets{max_attempts 1-10, max_tool_calls 1-256, max_wall_clock_seconds 1-3600, max_followups 0-16}`; all required | authoritative |
| `execution_mode` | `deterministic` or `bounded_adaptive` | authoritative |
| `mutation_mode` | `none` (default) or `fixture_only` | authoritative |
| `permitted_action_kinds` | subset of `policy_checkpoint.ACTION_KINDS`; anything except `mcp.tool.call` counts as mutating | authoritative |
| `permitted_tools` | ≤ 64 exact tool names (no patterns) | authoritative |
| `followup_templates` | ≤ 8 `FollowupTemplate{template_id, parameters: {name: ParamBound(kind ∈ {enum, int_range, fixture_ref}, ...)}}` | authoritative |
| `content_hash`, `scenario_id` | derived from all of the above | derived |

Validation rules:
- `shadow`/`production` require `allowlist_entry`. `fixture` forbids it.
- `production` requires `mutation_mode == "none"`.
- `mutation_mode == "none"` forbids mutating action kinds.
- `deterministic` requires `max_followups == 0` and no templates.

`check_scenario_catalog(scenarios)` refuses a `(name, version)` that appears with
two different hashes.

#### `AssuranceTargetAllowlist` (kind, id `atl-<16hex>`)

The allowlist is a versioned, hashed document. Each entry is
`{entry_id, target_kind, ref, environments}`, with exact refs only. The pure
function `check_target_allowlisted(scenario, allowlist)` succeeds only when:

- `scenario.target.allowlist_entry.allowlist_id` equals the allowlist's id;
- `content_hash` equals the entry's own hash;
- `kind`, `ref` and `environment` match.

The allowlist is data that a later PR or operator change controls. A model
never writes it. This check limits scope only. It does not replace
`policy_checkpoint`, so every live action the harness takes still goes through
`policy_checkpoint.Decision` and, where the policy requires it, through
`action_approvals`.

#### `VersionBinding` (shared by run, result and finding)

- `scenario`: `ScenarioRef{scenario_id, content_hash, name, version}`.
- `runtime`: `execution_evidence.VersionPins`, reused as is. Here `agent`, `environment`, `definition_version` and `definition_content_hash` are required. `profile_name`/`profile_version` are required together.
- `target`: `TargetRevision{kind, ref, revision}`. `revision` is a full git SHA (`execution_evidence._GIT_SHA_PATTERN` shape) or a bounded version token. It is never blank.

#### `AssuranceRun` (id `arn-<16hex>`)

- `binding: VersionBinding`.
- `execution: execution_evidence.ExecutionJoin`, with `runtime_execution_id` (`ex-`) required. `execution_id` (`we_`) is optional. This is the #196 identity and is not redefined.
- `mutation_mode`, which must equal the scenario's.
- `granted_budgets: Budgets`, each axis ≤ the scenario's.
- `attempt` (1-based, ≤ `max_attempts`).
- `started_at`, `ended_at?`: RFC 3339 Z timestamps. These are excluded from the hash, as in `implementation_completion._UNHASHED`.
- `observations`: ≤ 256 `ObservationRef{observation_id, invariant_ids, status ∈ {observed, partial, observation_failed, not_attempted}, evidence_id (ev-)? | artifact: ArtifactRef?, authority ∈ AUTHORITIES}`. An `observed` status requires a reference.
- `policy_decisions`: tuple of `PolicyDecisionRef`.
- `approvals`: tuple of `ApprovalRef`.
- `parent_run_id?`: set for a follow-up or replay. It is paired with `relation ∈ {followup, replay}` and `followup: FollowupProposal?`.

#### `AssuranceResult` (id `ars-<16hex>`)

- `run_id` and `binding`. The binding must equal the run's binding, which `check_result_against_run(result, run)` verifies.
- `outcome ∈ {invariant_held, invariant_violated, inconclusive, budget_exhausted, refused, harness_failure}`.
- `invariant_verdicts`: one entry per scenario invariant, `{invariant_id, verdict ∈ {held, violated, unknown}, observation_ids}`.
- `consumed: Budgets`-shaped usage.
- `evidence_ids`.

Rules:
- `held` requires every referenced observation to have status `observed`. Anything else forces `unknown`, so "could not observe" is never "absent".
- `invariant_held` requires all verdicts to be `held`.
- `invariant_violated` requires at least one `violated` verdict backed by an `observed` observation.
- `consumed` must be ≤ `granted_budgets` unless the outcome is `budget_exhausted`.

#### `AssuranceFinding` (id `afd-<16hex>`)

- `binding`, `origin_run_id`, `origin_result_id`, `invariant_id` (must be a scenario invariant).
- `state ∈ {candidate, confirmed, rejected}`.
- `reported_by{authority ∈ AUTHORITIES, producer (bounded slug)}`.
- `summary`: model-authored. It is bounded to 600 characters and passed through `redact_text`.
- `evidence_ids`.
- `validation?{replay_run_id, replay_result_id, authority ∈ {observed, derived}}`.
- `disposition? ∈ {false_positive, not_reproducible, duplicate, out_of_scope}` with a bounded `disposition_note`.
- `supersedes?` (the previous `afd-`).

Rules:
- `confirmed` requires `validation`, with `replay_run_id != origin_run_id`.
- `rejected` requires `disposition`.
- `candidate` forbids both.

`transition_finding(finding, to_state, *, replay_run, replay_result, disposition)`
is the only transition API. It checks the following, then seals a new revision
with `supersedes`:
- the replay run's binding equals the finding's binding;
- the replay run's `relation` is `replay`, with `parent_run_id == origin_run_id`;
- the replay result's outcome is `invariant_violated`, with a `violated` verdict for the same `invariant_id`.

`confirmed` and `rejected` are terminal.

#### `FollowupProposal` and `validate_followup`

`FollowupProposal{template_id, parameters}` is the only shape a model can
author. Its keys are closed, so `target`, `environment`, `tenant`, `credential`,
`tool` and `action_kind` cannot be expressed at all. `validate_followup` checks:
- the template exists in the scenario;
- every parameter is declared and within its `ParamBound`;
- the proposal adds no parameter keys beyond those.

A follow-up run inherits the parent's binding target and budgets and does not
replace them.

#### Redaction

Authoritative string fields that match `contains_credential` are rejected,
because a credential in an authored scenario is a bug and should not be masked
silently. Model-authored text (`summary`, `disposition_note`) is redacted to
`[redacted]` and truncated. No record carries tool output, prompts or target
responses. Those stay behind `ev-` evidence ids and `ArtifactRef` hashes.

### ADR `docs/adr/022-runtime-assurance-contract.md`

The ADR states the eight trust boundaries from the issue and maps each one to
the validator rule that enforces it. It includes the per-field authority table
(authoritative / derived / model-authored) and the reuse map (#196 to
`ExecutionJoin`, #197 to `PolicyDecisionRef`, #198 to `ApprovalRef`, #199 to
`ev-` ids, ADR 007 to `VersionPins`). It lists the follow-ups: the probe
harness, Tier B persistence in mctl-api, the allowlist home, and production
mutation through an approval-gated mode in a future api version.

### Fixtures and tests

Golden fixtures live in `tests/fixtures/assurance/`:
- `scenario-fixture.json` (fixture environment, deterministic);
- `scenario-shadow.json` (allowlisted shadow, bounded_adaptive);
- `allowlist.json`;
- `run.json` and `result-violated.json`;
- `finding-candidate.json`, `finding-confirmed.json` and `finding-rejected.json`.

Their `content_hash` values are pinned. `tests/test_runtime_assurance.py` covers
the tests listed in tasks.md.

## Alternatives

1. **Extend `ExecutionEvidence` with assurance blocks.** Rejected. An evidence envelope records which governance records applied to one execution. A scenario is a definition with no execution behind it, and a finding has a multi-revision lifecycle. Folding these in would overload ADR 018's hash-neutrality guarantees and blur the evidence/finding authority line. Assurance records refer to evidence by `ev-` id instead.
2. **JSON Schema files plus a generic validator.** Rejected. The repo has no JSON-Schema dependency, and every existing contract is a frozen-dataclass validator. Cross-field rules (held requires observed, confirmed requires replay, run budget ≤ scenario budget, allowlist entry hash) cannot be expressed cleanly in JSON Schema. A schema export can be generated later from the dataclasses if mctl-api needs one.
3. **Copy identity, policy and approval fields into assurance records** (actor, tenant, verdict, approver). Rejected. This is the "parallel authority model" the issue forbids, and the copies would drift from `ExecutionContext`, `policy_checkpoint.Decision` and `ApprovalRecord`. Only references are carried.
4. **Allow `production` + mutation behind a flag in v1alpha1.** Deferred. The issue makes production mutation a non-goal, and making it unrepresentable is the simplest invariant to verify.

## Platform impact

- **Migrations:** none. This is a new module, an ADR, fixtures and tests. No existing module, runner, workflow, chart or gitops file changes.
- **Backward compatibility:** imports from `execution_evidence`/`policy_checkpoint` are read-only reuse. The golden fixtures of those contracts are unaffected. `v1alpha1` is explicitly unstable, and a breaking change bumps the api version.
- **Resources:** none at runtime. The module is not loaded by any worker until the probe harness slice. It is stdlib-only, so it is safe to import into the Temporal worker (`tests/test_worker_isolation.py` constraint).
- **Risks and mitigations:**
  - Coupling to private names in `execution_evidence` (for example `_GIT_SHA_PATTERN`). Mitigation: import only public names. Where a pattern is private, either promote it to a public alias in `execution_evidence` (a behaviour-preserving one-line change, as `context_snapshot.hash_bytes` was) or redefine an equal regex with a test asserting equality.
  - Caps chosen too tight or too loose. Mitigation: they are named constants listed under Open questions, and a cap change is a version bump.
  - The contract is mistaken for authorization. Mitigation: a forbidden-token test (same as `execution_evidence` T9), and an ADR statement that `check_target_allowlisted` narrows scope and never authorizes.
