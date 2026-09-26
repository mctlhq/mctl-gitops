# Tasks: issue-242-capability-discovery-investigator-mode-slice-3

**Slice 3 of 4 for mctlhq/mctl-agents#242.** Slices 1 (#485) and 2 (#508)
are merged. This slice wires discovery mode into the issue investigator,
behind an env var that defaults to today's behaviour. The catalog field,
the mode-aware `validate_manifest.py` and the benchmark are slice 4 and must
not be started here (see design.md "Why the original slice 3 is split").

Task numbers 9, 10 and 15 keep the slice-1 proposal's numbering; S1–S4 are
new in this slice.

**PR body:** reference the issue with `Refs mctlhq/mctl-agents#242`, never
`Closes`/`Fixes`/`Resolves` — slice 4 is still pending.

## Mode and construction site

- [ ] 9. Add `_capability_mode()` to `orchestrator/run_issue_investigator.py`
      next to `_resolver_mode()`/`_context_mode()`: env
      `ISSUE_INVESTIGATOR_CAPABILITY_MODE`, values `eager` (default) and
      `discovery`, read fresh per call, invalid → `SystemExit`, and a
      printed `[capability] capability_mode=<mode>` line in every case.
      `_run_agent` rejects `legacy + discovery` with `SystemExit` before
      building any options. — DoD: unset env runs the unchanged path and
      never imports `orchestrator.capability_gateway`.

- [ ] S1. Discovery branch of `_run_agent` (depends on 9): after the plan is
      resolved, build the correlation with
      `context_assembly.build_execution_correlation(...)` (grow
      `_run_agent`'s keyword arguments with what that helper needs and
      `investigate()` already holds; do not hand-build an
      `ExecutionCorrelation`), then
      `await CapabilityGateway.build(plan, correlation, [MCTL_API_PROVIDER],
      checkpoint=PolicyDecidePolicyCheckpoint(grants=...))` and pass
      `gateway=` to `build_issue_investigator_options_from_plan`.
      `MCTL_API_PROVIDER = ProviderRef(type="mcp-remote",
      id=MCTL_API_PROVIDER_ID, alias="mctl", endpoint_ref=MCTL_MCP_URL)`.
      Grants: `plan.tools` with `mcp__mctl__*` kept only when
      `options._mctl_tool_globs()` is non-empty. Skip
      `ensure_mctl_connected` in discovery mode (the gateway's `build()` is
      the positive connection proof). A `GatewayError` from `build()` fails
      the run with its reason code and never falls back to `eager`. — DoD:
      import is lazy; `AbsentPolicyCheckpoint` is not constructed anywhere
      in production code.

## Product decision (ADR 017 sec. 8, option B)

- [ ] S2. `CapabilityGateway.invoke()` sends every capability through the
      `PolicyCheckpoint` before dispatch, whatever its consequence tier;
      remove the tier gate (`_CHECKPOINT_CONSEQUENCES`) from the invoke
      path. `options._require_enforcing_checkpoint` refuses
      `AbsentPolicyCheckpoint` over any non-empty sealed set. Amend ADR 017
      sec. 8 (the "are the ones `capability_invoke` submits" sentence and
      the open-question paragraph) to record option B with a dated owner
      decision (2026-09-26), keeping C (a sensitive-read approval tier)
      explicitly out of scope. Update `config/capability-consequence.yaml`'s
      header comment accordingly. — DoD: a `read-only` invocation produces a
      `POLICY_DECISION` line and a `policy_checkpoint: allowed` invocation
      record; a denied `read-only` call performs no provider call.

## Prompt

- [ ] 10. Discovery-mode-only prompt block in `_build_prompt`, passed as a
      keyword argument with an empty default like `service_skills_block`
      (depends on 9): search → describe → invoke, reason codes are answers.
      — DoD: eager-mode prompt bytes unchanged; the existing byte-identity
      tests pass unchanged.

## #508 carry-overs

- [ ] S3. In `orchestrator/capability_gateway.py`: bound `capability_id` to
      `_MAX_TRACED_ID_LENGTH` in the `arguments must be a JSON object`
      branch; count serialization drops made in `_annotations_to_dict` in
      the `CAPABILITY_PROVIDER_DEGRADED` line; reject a `provider.id`
      containing `/` in `_discover` with a `GatewayError` naming it. —
      DoD: one test each; the annotation test goes through
      `_McpProviderSession`, not `FakeSession`.

- [ ] S4. `test_every_read_only_tool_in_the_table_is_allowed_by_the_builtin_policy`
      takes its grants from `options._mctl_tool_globs()` (with
      `MCTL_TOKEN` set) instead of the literal `("mcp__mctl__*",)`.

## Docs

- [ ] 15. Add `docs/capability-pilot-status.md` in the shape of
      `docs/resolver-pilot-status.md`: what is live (code, off by default),
      the two env vars that activate it, what is blocked (slice 4: catalog
      field, mode-aware validator, benchmark), and the rollback switch. —
      DoD: a reader can tell shipped code from activated behaviour.

## Tests

- [ ] T13. Mode switch, mirroring the resolver-mode tests in
      `tests/test_run_issue_investigator.py` (`:3227`–`:3285`): unset →
      eager and `capability_gateway` not imported; explicit `eager` →
      unchanged path; invalid → `SystemExit`; `legacy + discovery` →
      `SystemExit`; the `[capability]` line is printed in every case.
      Update `_fake_build_from_plan` (`:3253`) to accept `gateway=`.

- [ ] T17. Discovery construction site: with a fake connector, `_run_agent`
      in `declarative + discovery` builds the gateway with the mctl-api
      provider and a `PolicyDecidePolicyCheckpoint`, passes it as
      `gateway=`, does not call `ensure_mctl_connected`, and uses a
      correlation equal to `build_execution_correlation`'s output. A
      provider failure fails the run and never builds eager options.

- [ ] T18. Option B: a `read-only` invocation calls the checkpoint (recording
      fake), a denied `read-only` call returns `policy-denied` with no
      provider call, and the builder refuses `AbsentPolicyCheckpoint` over
      a read-only-only set.

- [ ] T19. Eager prompt bytes are identical with the discovery block absent;
      the block appears only in discovery mode.

## Rollback

Unset `ISSUE_INVESTIGATOR_CAPABILITY_MODE` (default `eager`): the path that
runs today, with `capability_gateway` never imported. Option B affects only
the gateway path, which is off by default. Reverting the PR removes the
switch, the construction site and the ADR amendment.

## Deferred: slice 4 (not part of this run)

Task 11 (mode-aware `validate_manifest.py`), then task 14 (mctl-gitops:
`spec.capabilityDiscovery` in `execution-profile.schema.json`, validator
and `knownTools` for `mcp__capability__*`, the `issue-investigator-default`
profile field with `mode: eager`, and the matching release-binding bump),
task 13 (benchmark harness plus a live measurement in both modes) and tests
T11 and T14. Slice 4 needs its own new slug.
