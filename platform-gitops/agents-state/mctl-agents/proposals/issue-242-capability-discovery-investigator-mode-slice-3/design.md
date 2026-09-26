# Design: issue-242-capability-discovery-investigator-mode-slice-3

> **Slice 3 of 4 for mctlhq/mctl-agents#242.** Normative contract: ADR 017
> (`docs/adr/017-capability-discovery-and-gateway-contract.md`). Full
> original design: the slice-1 proposal
> `issue-242-feat-agent-platform-role-aware-capabilit/design.md`. Slice 2
> (`orchestrator/capability_gateway.py`, the `gateway=` builder parameter)
> merged as mctl-agents#508 → `146133d`. Every file:line below was re-read on
> `main` at `146133d`.

## Why the original "slice 3" is split

The original slice 3 was tasks 9–11 and 13–15. Re-reading `main` shows
three of them cannot land in one mctl-agents implementer run:

- **Task 14 (catalog field) is a different repository.** The mctl-gitops
  `ExecutionProfile` schema
  (`platform-gitops/agent-platform/schemas/execution-profile.schema.json`)
  has `additionalProperties: false` on `spec` with all 11 keys required, and
  every `spec.tools` entry must be a `policy.yaml` `knownTools` member. A
  `spec.capabilityDiscovery` field is a schema change, a validator change and
  a release-binding bump (`releases/shadow/issue-investigator.yaml` pins
  profile `1.3.0`) in mctl-gitops.
- **Task 11 (mode-aware `validate_manifest.py`) only matters once task 14
  exists.** Both set-equality checks (`_check_tool_policy_and_budget_match_options_py`
  at `validate_manifest.py:554` and `check_catalog_profiles_match_builders`
  at `:707`) call the profile's `runtime.optionsBuilder`, which is the legacy
  `build_issue_investigator_options`. Neither exercises the plan builder, so
  the gateway path cannot make them red. Task 11 stays paired with task 14
  (sequencing note: 11 before 14).
- **Task 13 (benchmark) needs live paid runs** in both modes against a fixed
  issue and SHA. An implementer run cannot produce those numbers.

So slice 3 is the runtime: the switch, the gateway construction site, the
policy decision, and the prompt. Slice 4 is catalog, validator and
benchmark.

## 1. The mode switch — `ISSUE_INVESTIGATOR_CAPABILITY_MODE`

`orchestrator/run_issue_investigator.py`, next to `_resolver_mode()`
(`:134`) and `_context_mode()` (`:155`). Values `eager` (default) and
`discovery`, read fresh on every call, invalid value → `SystemExit`.
Modelled on `_context_mode()`, which prints its own `[context] ...` line;
`_resolver_mode()` does not print (its line is printed by `_run_agent` at
`:1637`). The new helper prints `[capability] capability_mode=<mode>` in
every case.

`discovery` requires `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`: the
plan exists only on the declarative branch of `_run_agent` (`:1638–1647`).
`legacy + discovery` is rejected with `SystemExit` at the start of
`_run_agent`, before any options are built, never half-applied.

## 2. The construction site — `_run_agent`

`_run_agent(repo_dir, prompt, proposal_dir)` (`:1613`) runs under
`anyio.run` (`:2481`), so it can `await CapabilityGateway.build(...)`
between resolving the plan (`:1646`) and building options (`:1647`).

- **Import lazily.** `orchestrator.capability_gateway` is imported inside
  the discovery branch only. In `eager` mode it is never imported
  (`tests/test_worker_isolation.py` already forbids module-scope imports).
- **Correlation.** `_run_agent` receives no correlation inputs today. Reuse
  `context_assembly.build_execution_correlation(...)`
  (`orchestrator/context_assembly.py:869`), which already builds the
  declarative correlation from the plan's pins. `_run_agent` grows keyword
  arguments for what that helper needs and `investigate()` already holds
  (`issue_url`, `temporal_workflow_id`, `temporal_run_id`,
  `argo_workflow_name`). Do not hand-build an `ExecutionCorrelation`.
- **Providers.** The resolver and plan carry no provider concept. Slice 3
  declares one module-level provider for mctl-api:
  `ProviderRef(type="mcp-remote", id=MCTL_API_PROVIDER_ID, alias="mctl",
  endpoint_ref=MCTL_MCP_URL)`. Alias `mctl` keeps SDK-visible names
  `mcp__mctl__<tool>`, which match the plan's `mcp__mctl__*`. Moving the
  provider list into the profile is slice 4.
- **Checkpoint.** `PolicyDecidePolicyCheckpoint(grants=...)`. The grants are
  what the direct path's hook evaluates against for the same plan:
  `plan.tools` with `mcp__mctl__*` kept only when
  `options._mctl_tool_globs()` is non-empty, mirroring the builder's own
  two-fact conjunction. `AbsentPolicyCheckpoint` is never constructed in
  production.
- **The MCP guard.** `ensure_mctl_connected` (`:1659–1661`) is gated on
  `bool(options.mcp_servers)`. On the gateway path `mcp_servers` is
  `{"capability": ...}`, so the guard would look for an `mctl` connection
  that is deliberately absent. In discovery mode the guard is skipped. Its
  job (a positive proof that the provider answered) is done by
  `CapabilityGateway.build`, which lists tools against the live provider or
  raises `ProviderUnavailableError`.
- **Provider failure is fatal in discovery mode.** If `build()` raises, the
  run fails with the reason code. It never falls back to `eager`: a silent
  mode change would invalidate whatever the pilot is measuring.

## 3. Product decision: ADR 017 sec. 8, option B

ADR 017 sec. 8 left open whether reads that disclose sensitive data
(`mctl_get_service_config`, `mctl_get_service_logs`,
`mctl_read_openclaw_identity`) need a checkpoint. Facts on `main`:

- On the direct path, `_PolicyCheckpointHook` sends **every**
  `mcp__mctl__*` call through `policy_checkpoint.checkpoint`, and every
  decision, ALLOW included, emits a `POLICY_DECISION` audit line
  (`decide()` → `emit()`, `policy_checkpoint.py:416–459`, `:506`).
  `BUILTIN_POLICY` allows reads (`mctl-mcp-read`), so reads are audited but
  not gated.
- On the gateway path, `capability_invoke` consults the checkpoint only for
  `mutating`/`consequential`. A `read-only` call is dispatched with no
  policy decision and no `POLICY_DECISION` line. That is an audit regression
  compared with the direct path. It is also the mechanism behind the
  `mctl_verify_domain` P1 on #508, which is today closed only by a table
  test.

**Decision (option B): `capability_invoke` sends every capability through
the `PolicyCheckpoint`, whatever its tier.**

- Behaviour is unchanged, because `BUILTIN_POLICY` still allows reads.
- The audit trail matches the direct path.
- A misclassified `read-only` entry can no longer bypass policy.
- The consequence tier stays in the descriptor and in `capability_search`
  rows as information for the model; it no longer decides whether the
  checkpoint runs.
- `_require_enforcing_checkpoint` then refuses `AbsentPolicyCheckpoint`
  over any non-empty set, not only over a consequential one.

Rejected:
- **A (keep the tier gate):** it loses the audit line.
- **C (a "sensitive-read" tier behind approval):** the investigator reads
  logs on almost every run, so every run would stall on approvals. C is a
  separate product decision and would get its own issue if wanted.

ADR 017 sec. 8's last paragraph and its "`mutating` and `consequential`
capabilities are the ones `capability_invoke` submits" sentence are amended
to record B, with a dated note that this was the owner's decision on
2026-09-26.

## 4. The discovery prompt block — `_build_prompt`

`_build_prompt(issue, service, slug, *, context=None,
service_skills_block="")` (`:1427`). A short block (about 15 lines) is added
only in discovery mode. It tells the model to use `capability_search`, then
`capability_describe`, then `capability_invoke`, and to treat reason codes
as answers. Eager bytes stay identical. Existing byte-identity tests
(`test_build_prompt_with_context_none_matches_the_no_kwarg_call`, tests
`:3594`; `test_shadow_mode_prompt_is_byte_identical_to_off_...`, `:3626`)
must keep passing unchanged. The block is added through a keyword argument
with an empty default, the way `service_skills_block` is, so the
`inspect.getsource(_build_prompt)` hash (`:1817`) changes once, which is
expected and logged, not pinned.

## 5. Carried from #508's last review round (non-blocking P3s)

- Bound `capability_id` in the `arguments must be a JSON object` trace
  branch of `invoke()` as well (`_MAX_TRACED_ID_LENGTH`).
- Count annotation serialization drops made in `_annotations_to_dict` on the
  `_McpProviderSession` path in the `CAPABILITY_PROVIDER_DEGRADED` line, and
  test through `_McpProviderSession`, not `FakeSession`.
- `test_every_read_only_tool_in_the_table_is_allowed_by_the_builtin_policy`
  takes its grants from `options._mctl_tool_globs()` instead of a literal.
- `_discover` rejects a `provider.id` containing `/` with a `GatewayError`
  that names it, next to the tool-name check.

## 6. Pilot status document

`docs/capability-pilot-status.md`, in the shape of
`docs/resolver-pilot-status.md`. It covers what is live (code, off by
default), what activates it (`ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`
plus `ISSUE_INVESTIGATOR_CAPABILITY_MODE=discovery`), what is blocked
(catalog field, validator, benchmark: slice 4), and the rollback switch
(unset the env var).

## Rollback

`ISSUE_INVESTIGATOR_CAPABILITY_MODE` unset means eager, the exact path that
runs today; `capability_gateway` is not even imported. Option B changes only
the gateway path, which nothing in production enables by default. Reverting
the PR removes the switch and the construction site.
