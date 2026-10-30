# Runtime assurance contracts: AssuranceScenario, AssuranceRun, AssuranceResult, AssuranceFinding (v1alpha1)

## Context

mctlhq/mctl-agents#694 is the first required slice of the Agent Runtime
Assurance epic (mctlhq/.github#151). It asks for versioned, implementation-level
contracts for an assurance scenario, a run of that scenario, the run's result,
and the finding lifecycle that may follow. It also asks for the trust boundaries
those contracts enforce. Nothing executes probes in this slice. The point is
that the later deterministic bounded executor (the "probe harness", the next
work item) consumes these contracts as they are, and cannot invent its own
identity, policy, evidence or authority model.

mctl-agents already has sealed, canonical governance contracts:
`ExecutionContext` (`orchestrator/execution_identity.py`, ADR 011),
`ExecutionEvidence` (`orchestrator/execution_evidence.py`, ADR 018),
`policy_checkpoint` decisions (`orchestrator/policy_checkpoint.py`, ADR 014),
durable approvals (`orchestrator/action_approvals.py`), ADR 007 version pins,
and one hashing rule (`orchestrator/context_snapshot.hash_bytes`/`canonical_json`).
The new contracts must refer to those records. They must not copy them or
define parallel ones. They must also make target allowlisting, mutation mode
and budgets explicit, validated data. None of these may come from a prompt.

## User stories

- AS the probe-harness implementer I WANT one stable, validated schema for scenarios, runs, results and findings SO THAT the executor does not define its own identity or evidence format.
- AS a platform operator I WANT every finding bound to an exact scenario content hash, runtime release pins and target revision SO THAT I can replay it and know exactly what it is about.
- AS a security reviewer I WANT target allowlisting, mutation mode and budgets carried as data and checked by the validator SO THAT a probe model cannot widen its own scope.
- AS a triager I WANT a model-reported finding to stay `candidate` until a replay confirms it, and a rejected finding to carry a false-positive disposition SO THAT model claims are never treated as ground truth.
- AS an auditor I WANT the documentation to name which fields are authoritative, derived or model-authored SO THAT I know which statements I can trust.

## Acceptance criteria (EARS)

Contract and versioning
- THE SYSTEM SHALL define the kinds `AssuranceScenario`, `AssuranceRun`, `AssuranceResult` and `AssuranceFinding` under `api_version` `assurance.mctl.ai/v1alpha1` in a single pure module `orchestrator/runtime_assurance.py`.
- WHEN a document with an unknown `api_version`, a mismatched `kind`, or any unknown key is parsed THE SYSTEM SHALL raise `RuntimeAssuranceError` and return no object.
- WHEN any of the four records is sealed THE SYSTEM SHALL compute `content_hash` with `context_snapshot.hash_bytes(canonical_json(...))`, and derive its id from that hash (`asc-`, `arn-`, `ars-`, `afd-` + 16 hex).
- IF a parsed record's stored `content_hash` or id differs from the recomputed value THEN THE SYSTEM SHALL reject the record.

Scenario identity and immutability
- THE SYSTEM SHALL key an `AssuranceScenario` by `(name, version)`, and bind it exactly by `scenario_id` plus `content_hash`. Records are frozen dataclasses, so the content cannot change after sealing.
- IF two scenario documents share `(name, version)` but differ in `content_hash` THEN `check_scenario_catalog` SHALL reject the catalog as a version collision.

Target boundary, allowlist and mutation
- THE SYSTEM SHALL represent the target as a typed `TargetBoundary` (`kind`, `ref`, `environment`). Wildcards, globs and empty refs are refused.
- WHILE a scenario's `target.environment` is `shadow` or `production` THE SYSTEM SHALL require an `allowlist_entry` reference (`allowlist_id`, `entry_id`, `content_hash`). `check_target_allowlisted(scenario, allowlist)` SHALL succeed only when that exact entry, in that exact `AssuranceTargetAllowlist` version, admits the target's kind, ref and environment.
- THE SYSTEM SHALL carry `mutation_mode` as a closed vocabulary with default `none`. `AssuranceRun` SHALL repeat the `mutation_mode` it ran under, and the validator SHALL refuse a run whose mode differs from its scenario's.
- IF a scenario declares a mutating `permitted_action_kinds` entry (any `policy_checkpoint.ACTION_KINDS` member other than read-only tool calls) while `mutation_mode` is `none` THEN THE SYSTEM SHALL reject the scenario.
- IF a scenario combines `environment: production` with any `mutation_mode` other than `none` THEN THE SYSTEM SHALL reject it. Production mutation cannot be represented in v1alpha1.
- THE SYSTEM SHALL NOT define any field that expresses allow, deny, grant, approval or credential material. Authorization stays with `policy_checkpoint` and `action_approvals`, and records refer to it only through `PolicyDecisionRef` and `ApprovalRef`.

Bounded follow-ups
- WHEN a model proposes a follow-up THE SYSTEM SHALL accept it only through `validate_followup(scenario, proposal)`. The proposal must name a `followup_templates` entry of that scenario and supply only that template's declared parameters, within their declared bounds.
- IF a follow-up proposal names a target, environment, tenant, credential, tool or action kind THEN THE SYSTEM SHALL reject it, because those keys do not exist in `FollowupProposal`.

Budgets
- THE SYSTEM SHALL require every budget field to be present and positive within a hard cap: `max_attempts` (1-10), `max_tool_calls` (1-256), `max_wall_clock_seconds` (1-3600) and `max_followups` (0-16). A zero, negative, missing or "unlimited" value is refused.
- WHILE `execution_mode` is `deterministic` THE SYSTEM SHALL require `max_followups == 0` and an empty `followup_templates`.
- IF an `AssuranceRun`'s granted budget exceeds its scenario's budget on any axis THEN THE SYSTEM SHALL reject the run. `AssuranceResult.consumed` SHALL NOT exceed the run's granted budget unless the outcome is `budget_exhausted`.

Exact version binding
- THE SYSTEM SHALL require every `AssuranceRun`, `AssuranceResult` and `AssuranceFinding` to carry a `VersionBinding` with:
  - the scenario (`scenario_id`, `content_hash`, `name`, `version`);
  - the runtime, as `execution_evidence.VersionPins` with `agent`, `environment`, `definition_version` and `definition_content_hash`, plus `profile_name` and `profile_version` when a profile is resolved;
  - the target (`kind`, `ref`, `revision`).
- IF any of those version fields is missing or blank, or a target `revision` is not a full git SHA or bounded version token, THEN THE SYSTEM SHALL reject the record as version-incomplete.

Reuse of identity, policy, approval and evidence
- THE SYSTEM SHALL carry an `AssuranceRun`'s execution identity as `execution_evidence.ExecutionJoin` and require `runtime_execution_id` (`ex-`). It SHALL NOT define a new execution identity field.
- THE SYSTEM SHALL carry policy decisions as `execution_evidence.PolicyDecisionRef`, approvals as `execution_evidence.ApprovalRef`, and evidence as `ev-` evidence ids or `ArtifactRef`-style content hashes. It SHALL carry no payload copies.

Observation and results
- THE SYSTEM SHALL give every `ObservationRef` a `status` from `observed`, `partial`, `observation_failed` or `not_attempted`.
- IF an invariant's supporting observation is not `observed` THEN THE SYSTEM SHALL refuse the verdict `held` for that invariant and require `unknown`. A failed or partial observation is never recorded as observed absence.
- WHEN the outcome is `invariant_held` THE SYSTEM SHALL require every scenario invariant to have verdict `held`. WHEN the outcome is `invariant_violated` THE SYSTEM SHALL require at least one `violated` verdict with at least one `observed` evidence reference.

Finding lifecycle
- THE SYSTEM SHALL give an `AssuranceFinding` a state from `candidate`, `confirmed` or `rejected`, and allow only `candidate -> confirmed` and `candidate -> rejected`, through `transition_finding`. Each transition seals a new revision whose `supersedes` names the previous `finding_id`.
- IF a finding is `confirmed` without a `validation` block THEN THE SYSTEM SHALL reject it. A valid `validation` block has a `replay_run_id` different from the originating run, a replay result whose outcome is `invariant_violated` for the same `invariant_id`, and authority `observed` or `derived`.
- IF a finding is `rejected` without a `disposition` from the closed set (`false_positive`, `not_reproducible`, `duplicate`, `out_of_scope`) THEN THE SYSTEM SHALL reject it.
- WHILE a finding's `reported_by.authority` is `asserted` (model-authored) THE SYSTEM SHALL require state `candidate`, unless a validation block is present.

Redaction
- IF any string field matches `redaction.contains_credential`, or a model-authored text field exceeds its bound, THEN THE SYSTEM SHALL reject the record (for authoritative fields) or replace the text with `[redacted]` (for model-authored text). Sensitive inputs SHALL be carried as `fixture_ref` content hashes, never inline.

Tests and documentation
- THE SYSTEM SHALL ship golden fixtures under `tests/fixtures/assurance/` and tests that reject malformed, over-broad and version-incomplete documents.
- THE SYSTEM SHALL document the trust boundaries, and the authoritative / derived / model-authored classification of every field, in `docs/adr/022-runtime-assurance-contract.md`.

## Out of scope

- Executing probes, a probe harness, or any runner/CLI/Temporal wiring.
- Adaptive scenario generation.
- A second policy engine, approval store or evidence store; persistence of any assurance record (Tier B, mctl-api).
- Scanning arbitrary public or production targets; production mutation of any kind.
- Fixing mctl-agents#183 or mctl-telegram#602.

## Open questions

- Production mutation: the issue says "disabled by default". v1alpha1 makes it unrepresentable, which is stricter than a default. A later api version can add an opt-in mode gated on a durable approval. Confirm that this is acceptable.
- Where the canonical `AssuranceTargetAllowlist` lives (a gitops file reviewed by PR, or an mctl-api record). This slice defines only its shape and the pure check.
- Exact budget hard caps (10 attempts, 256 tool calls, 3600 s, 16 follow-ups) are chosen to match existing bounds (`execution_evidence.MAX_TOOL_CALLS = 256`). Confirm them before the harness depends on them.
- The target `kind` vocabulary (`repository`, `mctl_service`, `mcp_capability`, `fixture`) is a first cut. Tenant-scoped targets are not modelled separately. A tenant is part of the allowlisted `ref` and is never chosen by a model.
