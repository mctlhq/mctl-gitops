# Tasks: issue-694-feat-runtime-assurance-define-assurance

- [ ] 1. Create `orchestrator/runtime_assurance.py` with the module docstring (scope, trust boundaries, reuse map, "no field expresses allow/deny/grant/approval"). Also add `API_VERSION = "assurance.mctl.ai/v1alpha1"`, the per-kind `SUPPORTED_API_VERSIONS`, `RuntimeAssuranceError`, the closed vocabularies (target kinds, environments, mutation modes, execution modes, observation statuses, outcomes, verdicts, finding states, dispositions, relations), the `MAX_*` caps and the id prefixes `asc-`/`atl-`/`arn-`/`ars-`/`afd-`. — DoD: the module imports only stdlib plus `context_snapshot`, `redaction`, `execution_evidence` and `policy_checkpoint` public names, and has no I/O.
- [ ] 2. Implement the shared blocks `TargetBoundary`, `AllowlistEntryRef`, `Budgets`, `InputSpec`, `SetupStep`, `InvariantSpec`, `FollowupTemplate`/`ParamBound`, `ScenarioRef`, `TargetRevision`, `VersionBinding` (wrapping `execution_evidence.VersionPins`), `ObservationRef` and `FollowupProposal`. Each gets `to_dict`/`from_dict`, unknown-key rejection, bound checks and credential screening (depends on 1). — DoD: every block round-trips, and wildcard refs, missing or out-of-cap budgets, and blank version fields are refused.
- [ ] 3. Implement `AssuranceScenario` with `seal_scenario` and `check_scenario_catalog`, enforcing the environment/allowlist, production/mutation, mutation/action-kind and deterministic/followup rules (depends on 2). — DoD: `scenario_id` and `content_hash` are derived through `hash_bytes(canonical_json(...))`, and a tampered hash is rejected on parse.
- [ ] 4. Implement `AssuranceTargetAllowlist`, `seal_allowlist` and `check_target_allowlisted(scenario, allowlist)` (depends on 3). — DoD: the check succeeds only on an exact allowlist id, entry hash, kind, ref and environment match.
- [ ] 5. Implement `AssuranceRun` and `seal_run`, reusing `ExecutionJoin` (with `runtime_execution_id` required), `PolicyDecisionRef` and `ApprovalRef`, plus `check_run_against_scenario` (mutation mode equality, granted budgets ≤ scenario budgets, attempt ≤ max_attempts, follow-up validity through `validate_followup`) (depends on 3). — DoD: timestamps are excluded from the hash, and an over-budget or mode-mismatched run is refused.
- [ ] 6. Implement `validate_followup(scenario, proposal)` (depends on 3). — DoD: unknown templates, undeclared parameters and out-of-bound values are refused, and the proposal shape cannot express a target, tenant, credential, tool or action kind.
- [ ] 7. Implement `AssuranceResult`, `seal_result` and `check_result_against_run`, covering the per-invariant verdict rules (held requires observed, otherwise unknown), the outcome consistency rules and the consumed-budget rule (depends on 5). — DoD: a result built from a failed or partial observation cannot claim `held` or `invariant_held`.
- [ ] 8. Implement `AssuranceFinding`, `seal_finding` and `transition_finding`, with candidate/confirmed/rejected state rules, the replay validation binding, the closed dispositions, `supersedes`, and `redact_text` on model-authored text (depends on 7). — DoD: a `confirmed` finding cannot be constructed or parsed without a valid replay reference, and terminal states cannot transition.
- [ ] 9. Add golden fixtures under `tests/fixtures/assurance/`: `scenario-fixture.json`, `scenario-shadow.json`, `allowlist.json`, `run.json`, `result-violated.json`, `finding-candidate.json`, `finding-confirmed.json` and `finding-rejected.json` (depends on 8). — DoD: each fixture parses, and its pinned `content_hash` recomputes exactly.
- [ ] 10. Write `docs/adr/022-runtime-assurance-contract.md` covering scope and non-goals, the eight trust boundaries mapped to validator rules, the per-field authority table, the reuse map (#196, #197, #198, #199, ADR 007) and follow-ups. Add one line to `CHANGELOG.md` only if the release-please convention requires it (depends on 8). — DoD: the ADR names every field in the module and its authority class.

## Tests

All tests go in `tests/test_runtime_assurance.py`.

- [ ] T1. Golden fixtures round-trip and keep their hashes. Re-sealing reproduces the ids. Altering any hashed field changes the id. Altering `started_at`/`ended_at` does not.
- [ ] T2. Malformed documents are refused: an unknown `api_version`, a mismatched `kind`, an unknown key at each nesting level, wrong types, an oversized string, a tampered `content_hash`, and a tampered id.
- [ ] T3. Over-broad scenarios are refused:
  - a wildcard or glob target ref;
  - a `shadow`/`production` target without `allowlist_entry`;
  - `production` with `fixture_only`;
  - a mutating action kind with `mutation_mode: none`;
  - a missing, zero or above-cap value on any budget axis;
  - `deterministic` with follow-ups;
  - more than the allowed number of inputs, invariants or tools.
- [ ] T4. Version-incomplete records are refused: a run, result or finding with a blank `definition_content_hash`, `agent`, `definition_version` or `environment`; a profile name without a version; a blank or malformed target `revision`; or a missing scenario `content_hash`.
- [ ] T5. Allowlist: `check_target_allowlisted` succeeds on an exact match. It fails on a different allowlist version, an entry hash mismatch, an environment not listed, or a ref mismatch.
- [ ] T6. Follow-ups: valid template parameters are accepted. An unknown template, an extra parameter, an out-of-range int, a non-enum value, or a proposal dict containing `target`/`tenant`/`credential`/`tool` keys is refused.
- [ ] T7. Run against scenario: granted budget above the scenario's, a different mutation mode, an attempt above `max_attempts`, or `ExecutionJoin` without `runtime_execution_id` is refused.
- [ ] T8. Observation honesty:
  - a `held` verdict backed by a `partial`, `observation_failed` or `not_attempted` observation is refused;
  - `invariant_held` with any `unknown` verdict is refused;
  - `invariant_violated` without an observed violated verdict is refused;
  - `observed` without an evidence or artifact reference is refused.
- [ ] T9. Finding lifecycle:
  - candidate to confirmed succeeds with a matching replay;
  - confirmation is refused when the replay has the same run id, a different binding, an outcome that is not violated, a different invariant, or `asserted` authority;
  - `rejected` without a disposition is refused;
  - confirmed or rejected cannot transition further;
  - an `asserted` candidate cannot be parsed as `confirmed` without validation.
- [ ] T10. Redaction: an authoritative string containing a `ghp_`/`sk-` credential shape is refused, and a model-authored `summary` containing one is stored as `[redacted]` and truncated to its bound.
- [ ] T11. Purity and no authority: an `ast` scan confirms stdlib-only imports plus the allowed intra-repo modules (mirroring `tests/test_execution_evidence.py::test_module_import_is_stdlib_only`). A field-name scan confirms that no dataclass field contains `allow`, `deny`, `permit`, `grant` or `authorized`.
- [ ] T12. Reuse: `AssuranceRun.execution` is an `execution_evidence.ExecutionJoin` instance, the binding's runtime is `execution_evidence.VersionPins`, and policy and approval refs are the `execution_evidence` classes (identity checks, not copies).

## Rollback

The change is additive. It adds a new module, fixtures, tests and an ADR, and
no runner, workflow or deployment imports the module yet. To roll back, revert
the PR. Nothing else to clean up: no records are persisted anywhere, there is
no migration, and the deployed `mctl-agents-worker` image is unaffected until a
later slice wires the harness in.
