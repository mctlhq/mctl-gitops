# Tasks: issue-227-feat-agent-platform-resolve-execute-agen

- [ ] 1. Add v1alpha2 dataclasses (`AgentDefinition`, `ExecutionProfile`) and
      loaders to `orchestrator/manifest.py`, keeping all existing v1alpha1
      parsing (`AgentManifest`, `load`, `load_all`) unchanged — DoD: new
      `load_v1alpha2_definition(path)` / `load_execution_profile(path)`
      functions exist, an unknown `apiVersion` still raises `ManifestError`,
      and every current v1alpha1 manifest continues to load byte-identically
      through the existing `load_all()`.
- [ ] 2. Author `agents/_profiles/investigator-default/profile.yaml`
      (depends on 1) encoding today's real values verbatim: `modelPolicyRef.
      task: service_agent`, the 8-entry tool list from
      `build_issue_investigator_options()`, `budgetUsd: 3.00`,
      `runtime.optionsBuilder:
      orchestrator.options:build_issue_investigator_options`,
      `runtime.sandbox.{backend: argo, clusterWorkflowTemplate:
      mctl-agents-investigate}`, `approval: none`, `evidence:
      [proposal_triplet, status_yaml_source_block, github_comment]` — DoD:
      file parses via task 1's loader; a new
      `test_investigator_profile_matches_manifest_v1alpha1_claim` test
      diffs its resolved fields against the *current*
      `agents/_manifests/issue-investigator/agent.yaml` (read before task 3
      rewrites it) and passes.
- [ ] 3. Rewrite `agents/_manifests/issue-investigator/agent.yaml` to
      `apiVersion: agents.mctl.ai/v1alpha2` with
      `spec.executionProfileRef: {name: investigator-default, compatibility:
      ...}` (depends on 1, 2) — DoD: `orchestrator/validate_manifest.py`
      gains a v1alpha2 branch that resolves the definition + profile pair
      and runs the *same* options-builder-comparison check it already runs
      for v1alpha1 manifests; `uv run python -m
      orchestrator.validate_manifest agents/_manifests/issue-investigator/
      agent.yaml` passes; every other agent's v1alpha1 manifest is untouched
      and its validation is unaffected.
- [ ] 4. Add `tests/fixtures/resolver/issue-investigator.release.yaml`
      (depends on 3) recording `{environment: production, definition:
      {name, version}, profile: {name, version}, revision: 1, status:
      published}` with content-hash-derived versions — DoD: a helper script
      or test (`test_resolver_fixture_hashes_match_checked_in_files`)
      recomputes both hashes from the live files and asserts they equal the
      fixture's recorded values, so drift fails CI instead of silently
      passing.
- [ ] 5. Implement `orchestrator/resolver.py`: `ExecutionTask`,
      `ExecutionPlan`, `ResolutionError`, and `execute(agent, task)`
      (depends on 1, 4) performing the five resolution steps from design.md
      §3 (definition load, profile+compatibility check, release-binding
      fixture lookup, model resolution via `config/model_policy.py`, prompt
      hash) — DoD: `execute("issue-investigator", task)` returns a frozen
      `ExecutionPlan` for a valid task; each of missing-definition,
      missing-profile, incompatible-compatibility-range, disabled-status,
      and missing-release-binding-fixture raises `ResolutionError` with a
      message naming the specific bad reference, all covered by unit tests.
- [ ] 6. Add `orchestrator/options.py:
      build_issue_investigator_options_from_plan(repo_dir, plan,
      proposal_dir)` (depends on 5) wrapping the existing
      `build_issue_investigator_options()` shape with `plan.model`/
      `plan.tools`/`plan.budget_usd` substituted for today's module
      constants — DoD: unmodified `build_issue_investigator_options()`
      signature/behavior; new function exists and is exercised by task 8's
      golden test.
- [ ] 7. Wire `ISSUE_INVESTIGATOR_RESOLVER_MODE` (env var, default
      `"legacy"`) into `orchestrator/run_issue_investigator.py` (depends on
      5, 6): `"legacy"` runs today's unchanged path; `"declarative"` calls
      `execute()` before `_clone_repo(...)`, converts `ResolutionError` into
      `InvestigateResult(error=...)` exactly like the existing
      `except Exception` branch, logs `plan.to_dict()`, and drives
      `_run_agent()` through `build_issue_investigator_options_from_plan`;
      any other value raises `SystemExit` at import time — DoD:
      `investigate()`'s public signature and `InvestigateResult` shape are
      unchanged; `mctl_trigger_issue`/`mctl-agents-investigate` callers need
      no changes; a resolution failure never reaches `_clone_repo` (no
      wasted clone/spend).
- [ ] 8. Golden/contract equivalence test comparing
      `build_issue_investigator_options(...)` and
      `build_issue_investigator_options_from_plan(...)` for the same
      repo_dir/proposal_dir inputs under the fixture-resolved plan (depends
      on 5, 6) — DoD: `cwd`, `model`, `allowed_tools` (as a set),
      `mcp_servers`, `permission_mode`, `max_budget_usd`, `add_dirs` are
      asserted equal field-by-field; test fails loudly if either function's
      shape changes without the other being updated.
- [ ] 9. Declarative-mode integration test driving
      `run_issue_investigator.investigate()` end-to-end with
      `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`, a mocked `gh` /
      `ClaudeSDKClient` (reusing `tests/conftest.py`'s existing
      `fake_mcp_client_factory` pattern) (depends on 7) — DoD: proposal
      triplet, `.status.yaml` `source` block, GitHub comment call, and
      `status: proposed` stop-point are all identical to the existing
      legacy-mode tests in `tests/test_run_issue_investigator.py` for the
      same inputs.
- [ ] 10. Replay/determinism test:  two `execute("issue-investigator",
      task)` calls against the same fixture state and task payload (depends
      on 5) — DoD: `ExecutionPlan` equality (dataclass `==`) holds; a
      mutated (unregenerated) fixture hash makes the second call raise
      `ResolutionError` instead of silently returning a stale plan.
- [ ] 11. Rollback drill test: with `ISSUE_INVESTIGATOR_RESOLVER_MODE` unset
      (or explicitly reset to `legacy`) after having been `declarative`
      (depends on 7) — DoD: a test asserts the driver's observable behavior
      (options shape, model, tools, budget) matches a clean-legacy baseline
      run with no residual state from having been in declarative mode
      (module-level constants are read once per env, not cached across
      modes in a way that would leak).
- [ ] 12. Update `docs/agent-inventory.yaml` and
      `docs/adr/007-agent-definition-execution-profile-contract.md`'s
      "Downstream sequencing" note (depends on 3-9) to record that
      `issue-investigator` has a v1alpha2 definition/profile pair validated
      against checked-in fixtures, and that production activation still
      requires `#950` — DoD: doc PR reviewed alongside the code; no other
      agent's inventory entry is touched.

## Tests

- [ ] T1. `test_manifest_v1alpha2_loads_definition_and_profile` — a minimal
      valid v1alpha2 fixture pair round-trips through
      `load_v1alpha2_definition`/`load_execution_profile`.
- [ ] T2. `test_manifest_unknown_api_version_fails_loudly` — an
      `apiVersion: agents.mctl.ai/v1alpha3` document raises `ManifestError`.
- [ ] T3. `test_validate_manifest_v1alpha2_matches_options_builder` —
      `issue-investigator`'s migrated manifest+profile pair resolves to the
      same tool/budget claim `build_issue_investigator_options()` actually
      implements (extends the existing `test_manifest_is_valid`
      parametrization).
- [ ] T4. `test_resolver_fixture_hashes_match_checked_in_files` (task 4's
      DoD, promoted to a named test).
- [ ] T5. `test_execute_returns_immutable_plan_for_issue_investigator` (task
      5's happy path).
- [ ] T6. `test_execute_rejects_missing_definition` /
      `_rejects_missing_profile` / `_rejects_incompatible_compatibility` /
      `_rejects_disabled_status` / `_rejects_missing_release_binding` — five
      parametrized negative cases, each asserting `ResolutionError` and a
      message naming the failing reference.
- [ ] T7. `test_options_from_plan_equals_legacy_options` (task 8's DoD).
- [ ] T8. `test_investigate_declarative_mode_matches_legacy_artifacts` (task
      9's DoD).
- [ ] T9. `test_execute_is_deterministic_and_replay_safe` (task 10's DoD).
- [ ] T10. `test_investigator_resolver_mode_rejects_unknown_value` —
      anything other than `legacy`/`declarative` raises `SystemExit` at
      driver start.
- [ ] T11. `test_investigator_resolver_mode_defaults_to_legacy` — no env var
      set reproduces today's exact behavior (regression guard for the
      rollback requirement).
- [ ] T12. `test_resolution_failure_never_submits_argo` — with a
      deliberately broken fixture, `investigate(...,
      dry_run=False)` in declarative mode returns an error result without
      any `gh repo clone` call having been made (mock assertion on
      `_clone_repo`/`_run` not being invoked for the clone step).

## Rollback

Immediate operational rollback is a single environment-variable change:
unset `ISSUE_INVESTIGATOR_RESOLVER_MODE` (or set it to `"legacy"`) on the
`mctl-agents-investigate` CWFT's pod spec / the driver's runtime env, which
routes every subsequent investigator run back through the untouched
`build_issue_investigator_options()` / `INVESTIGATOR_MODEL` path with zero
code change and zero redeploy of anything except the env var itself — no
Argo template, Temporal workflow, or mctl-api change ever depended on the
declarative path, so no downstream rollback is required there.

Code-level rollback, if the resolver module itself needs to be reverted, is
a plain Git revert of tasks 1-9's commits: `agents/_manifests/issue-
investigator/agent.yaml` reverts to v1alpha1, `orchestrator/manifest.py`'s
v1alpha1 loader was never modified so nothing else regresses, and
`orchestrator/resolver.py` plus `agents/_profiles/` are net-new files that
disappear cleanly. Because `orchestrator/options.py:
build_issue_investigator_options()` and `orchestrator/
run_issue_investigator.py`'s legacy branch are never edited by this
proposal (only wrapped/branched around), a revert cannot leave the legacy
path in a half-migrated state.

Task 11's rollback-drill test is the CI guard that this promise stays true:
it fails the build if flipping the flag back does not reproduce byte
-identical legacy behavior.
