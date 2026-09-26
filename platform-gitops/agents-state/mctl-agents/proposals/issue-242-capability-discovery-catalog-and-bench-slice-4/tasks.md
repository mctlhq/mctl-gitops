# Tasks: issue-242-capability-discovery-catalog-and-bench-slice-4

**Slice 4 of 4 for mctlhq/mctl-agents#242, mctl-agents half (part A in
design.md).** Slices 1–3 are merged. The mctl-gitops half (part B) and the
live measurement (part C) are not part of this run.

**PR body:** reference the issue with `Refs mctlhq/mctl-agents#242`, never
`Closes`/`Fixes`/`Resolves` — parts B and C remain.

## Catalog field → plan → runtime

- [ ] 1. `orchestrator/resolver.py` `load_profile`: parse optional
      `spec.capabilityDiscovery` (`enabled: bool`, ordered `providers` of
      `{type, id, alias, endpoint}`) per design.md sec. 2: `type` in
      `PROVIDER_TYPES`, no `/` in `id`/`alias`, unique aliases, `endpoint`
      a symbolic name from a closed code-side map (`mctl-api-mcp` →
      `MCTL_MCP_URL`), provider `mctl-api` must use alias `mctl`. Absent
      field == `enabled: false`, no providers. Any violation is a
      `ResolverError` naming the field. — DoD: a profile without the field
      resolves to a plan identical to today's.

- [ ] 2. `ExecutionPlan` gains `capability_discovery_enabled: bool = False`
      and `capability_providers: tuple[ProviderRef, ...] = ()`, both in
      `to_log_dict()` (depends on 1). — DoD: existing plan equality and
      log-shape tests pass with only the two new keys added.

- [ ] 3. `_run_agent` discovery branch (depends on 2): refuse with
      `SystemExit` when `plan.capability_discovery_enabled` is false ("the
      profile does not permit discovery"); pass `plan.capability_providers`
      to `CapabilityGateway.build`; remove the `MCTL_API_PROVIDER` constant.
      Update `docs/capability-pilot-status.md` (activation now needs the
      profile permission and the env var; rollback unchanged). — DoD:
      discovery runs only when the profile permits it AND the env var asks
      for it.

## Validation (task 11)

- [ ] 4. `orchestrator/validate_manifest.py`: for every catalog profile with
      `capabilityDiscovery.enabled: true`, resolve a plan and build
      `build_issue_investigator_options_from_plan(..., gateway=<stub>)`;
      assert `set(allowed_tools) - _CAPABILITY_TOOLS ==
      (set(spec.tools) - _CAPABILITY_TOOLS - {"mcp__mctl__*"}) |
      {"mcp__capability__*"}`. Do not change `_builder_call_args` or the
      two existing checks; do not switch any profile's `optionsBuilder`.
      — DoD: the current catalog (no field) validates exactly as today; a
      fixture profile with `enabled: true` passes, and one whose builder
      output would widen the tool surface fails.

## Benchmark harness (task 13, harness only)

- [ ] 5. `tools/capability_bench.py` per design.md sec. 4: `schema-bytes`
      (live provider listing, operator-run) and `compare` (two captured
      runs → markdown table), token math via `usage_ledger.records_for`;
      plus `docs/benchmarks/capability-discovery.md` as a skeleton that says
      "not yet measured" and how to run the measurement. — DoD: no model
      call and no network in tests.

## #509 carry-overs

- [ ] 6. Preflight order: resolver-mode check before the `MCTL_TOKEN` check
      in `_run_agent`; the `legacy + discovery` test no longer sets
      `MCTL_TOKEN`.
- [ ] 7. Per-tool annotation-drop flag on `ProviderTool`, counted in
      `_discover` after the eligibility `continue`s.
- [ ] 8. `invoke()`: fail-closed `try` around the checkpoint call and
      `policy_checkpoint_status`, returning `policy-denied` if a
      `PolicyCheckpoint` raises.

## Tests

- [ ] T11. `tests/test_manifest.py`: current catalog unchanged; an
      `enabled: true` fixture profile validates against the gateway
      allow-list; a widening builder fails loudly.
- [ ] T14. `tools/capability_bench.py` measurement functions compute schema
      bytes and token totals from recorded fixture messages, without a model
      or network.
- [ ] T20. Resolver: absent field → disabled with no providers; each
      invalid shape (bad type, `/` in id, duplicate alias, unknown endpoint
      name, `mctl-api` with a non-`mctl` alias) → `ResolverError`.
- [ ] T21. `_run_agent`: env `discovery` + profile not permitting →
      `SystemExit` before any gateway or options are built; permitted →
      the gateway gets `plan.capability_providers`.
- [ ] T22. One test each for tasks 6–8 (the resolver-mode message wins
      without a token; an ineligible tool's annotation drop is not
      counted; a raising checkpoint yields `policy-denied` and no provider
      call).

## Rollback

Additive: defaulted plan fields, a validator check that applies only to
profiles declaring the field, a standalone tool, and the P3 fixes. Unset
`ISSUE_INVESTIGATOR_CAPABILITY_MODE` to run eager. Reverting the PR restores
slice 3's constant provider.

## Not in this run

- **Part B (mctl-gitops, human-authored PR after this merges):**
  - `capabilityDiscovery` as an optional `spec` property in
    `schemas/execution-profile.schema.json`, plus the validator;
  - the field on `issue-investigator-default` with `enabled: false`;
  - the profile version `1.3.0` → `1.4.0` and the matching
    `releases/shadow/issue-investigator.yaml` pin, in the same PR.
- **Part C (operator):** flip `enabled: true` in a reviewed gitops PR, run
  the fixed issue once per mode, and fill in
  `docs/benchmarks/capability-discovery.md`.
