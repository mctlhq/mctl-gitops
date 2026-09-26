# Design: issue-242-capability-discovery-catalog-and-bench-slice-4

> **Slice 4 of 4 for mctlhq/mctl-agents#242, mctl-agents half.** Normative
> contract: ADR 017. Slices 1–3 merged (#485, #508, #509 → `2848fbe`).
> File:line references were re-read on `main` at `fed243e` (mctl-agents) and
> `26bc4327` (mctl-gitops).

## What slice 4 is, and how it is split

The remaining work spans two repositories and one live measurement:

| Part | Where | Who |
|---|---|---|
| A. Profile field parsed into the plan; runtime reads providers and the permission from the plan; mode-aware validation; benchmark harness; #509 P3s | mctl-agents | this proposal (implementer) |
| B. `spec.capabilityDiscovery` in the ExecutionProfile schema, on `issue-investigator-default`, with the version and release-binding bump | mctl-gitops | a human-authored mctl-gitops PR, after A merges |
| C. The live eager-vs-discovery measurement | operator | after A and B, with discovery permitted on the profile |

Order: A before B. The resolver ignores unknown spec keys (`load_profile`,
`resolver.py:516–635`, `spec.get` only), so neither order breaks mctl-agents.
Landing A first means the validator and the runtime already understand the
field on the day gitops starts declaring it. Both the runtime CWFTs and
mctl-agents CI read gitops `main` with no ref pin, so B takes effect as soon
as it merges.

## 1. Governance decision: the catalog permits, the env var activates

Today (slice 3), whether discovery runs depends only on
`ISSUE_INVESTIGATOR_CAPABILITY_MODE`, an environment variable. The provider
list is a code constant (`MCTL_API_PROVIDER`,
`run_issue_investigator.py:134–136`).

**Decision:** the reviewed catalog decides whether discovery is allowed and
which providers it may reach. The env var decides only whether a given
deployment turns it on.

```yaml
spec:
  capabilityDiscovery:          # optional; absent == {enabled: false}
    enabled: false              # true permits discovery for this profile
    providers:                  # ordered; alias assignment follows this order
      - {type: mcp-remote, id: mctl-api, alias: mctl, endpoint: mctl-api-mcp}
```

- Discovery runs only when the profile says `enabled: true` **and** the env
  var says `discovery`. Anything else runs eager.
- An env var set to `discovery` while the profile does not permit it is a
  `SystemExit` with a named reason. That is the same fail-closed posture as
  slice 3's other preflights, never a silent fallback.
- Rollback stays one env var, and needs no redeploy or gitops change.
  Permanently forbidding discovery is one reviewed gitops line
  (`enabled: false`).
- `endpoint` is a **symbolic name** resolved in code (`mctl-api-mcp` →
  `MCTL_MCP_URL`), never a URL in the catalog. A catalog edit must not be
  able to point the gateway, and the bearer token it sends, at an arbitrary
  host. Unknown endpoint names are a resolver error.
- The `mctl-api` provider must keep alias `mctl`, so that SDK-visible names
  stay `mcp__mctl__<tool>` and continue to match `spec.tools`' `mcp__mctl__*`.
  The resolver validates this rather than relying on convention.

Rejected alternatives:
- **Keep the env var only:** an unreviewed switch decides which tool surface
  a production agent gets.
- **Catalog only:** a pilot could no longer be scoped to one deployment, and
  rollback would need a gitops PR.

## 2. Resolver and plan (mctl-agents)

- `load_profile` parses the optional `spec.capabilityDiscovery`. It
  validates `enabled` as a bool; each provider's `type` against
  `PROVIDER_TYPES`, `id`/`alias` as non-empty with no `/`, and `endpoint`
  against a closed code-side map; alias uniqueness; and the `mctl-api` → `mctl`
  alias rule. It stays permissive about other unknown spec keys, as today.
- `ExecutionPlan` gains `capability_discovery_enabled: bool = False` and
  `capability_providers: tuple[ProviderRef, ...] = ()`, both included in
  `to_log_dict()`. The defaults keep every existing plan and test identical.
- `_run_agent`'s discovery branch uses `plan.capability_providers` instead of
  the `MCTL_API_PROVIDER` constant, and refuses when
  `plan.capability_discovery_enabled` is false. The constant is removed. The
  resolver is the one place that turns catalog entries into `ProviderRef`s.

## 3. Mode-aware validation (task 11)

`validate_manifest.py`'s two equality checks
(`_check_tool_policy_and_budget_match_options_py`, `:554`;
`check_catalog_profiles_match_builders`, `:707`) exercise the profile's
`runtime.optionsBuilder`, which stays the legacy
`build_issue_investigator_options`. Slice 4 does **not** switch that builder:
doing so first in gitops would make `_builder_call_args` (`:160–166`) call
the plan builder with the wrong signature and turn mctl-agents CI red.

It adds a third check for profiles that set `capabilityDiscovery.enabled:
true`: build `build_issue_investigator_options_from_plan(plan, ...,
gateway=<stub>)` for a plan resolved from that profile, and assert
`set(allowed_tools) - _CAPABILITY_TOOLS == (set(spec.tools) -
_CAPABILITY_TOOLS - {"mcp__mctl__*"}) | {"mcp__capability__*"}`. This is the
"no permission expansion" claim made checkable against the catalog.
Profiles without the field are compared exactly as today.

## 4. Benchmark harness (task 13, measurement is an operator step)

`tools/capability_bench.py`, runnable only by an operator:

- `schema-bytes`: connects to the mctl-api provider once, lists its tools,
  and reports the eager first-turn tool-schema bytes (all advertised
  `mcp__mctl__*` schemas the profile allows) against the discovery first-turn
  bytes (the three gateway tool schemas from `CapabilityGateway.sdk_tools()`).
- `compare`: takes two run transcripts (eager and discovery; captured
  `ResultMessage` JSON or `USAGE` records) and produces the markdown table for
  `docs/benchmarks/capability-discovery.md`: input, output, cache-read and
  cache-creation tokens, turns, and wall clock, with the sample size stated.
  Token math reuses `usage_ledger.records_for` (`usage_ledger.py:453`), which
  is pure. USD cost is not computed client-side; the price catalog is
  server-side.

The implementer ships the harness, its unit test (T14, from recorded fixture
messages, no model call) and a `docs/benchmarks/capability-discovery.md`
skeleton that says "not yet measured". Filling it in is part C.

## 5. Carried from #509's last review round

- Order the discovery preflights so the resolver-mode check precedes the
  token check. Drop the unrelated `MCTL_TOKEN` arrangement from the
  `legacy + discovery` test.
- Carry the session-side annotation drop per tool (a flag on
  `ProviderTool`), and count it in `_discover` after the eligibility
  `continue`s, so both halves of `annotations_dropped` share one denominator.
- Wrap `self.checkpoint.check(...)` plus `policy_checkpoint_status(...)` in
  `invoke()` (`capability_gateway.py:884`) in a fail-closed `try` that
  returns `policy-denied` when a `PolicyCheckpoint` implementation raises.

## Known and out of scope

`resolver.py:633` parses `spec.serviceSkills`, which the gitops schema
forbids (`additionalProperties: false`). This is pre-existing, unrelated to
#242, and noted for a separate issue.

## Rollback

A is additive: new optional plan fields with defaults, a new validator check
that applies only to profiles declaring the field, a standalone tool, and the
P3 fixes. Unsetting `ISSUE_INVESTIGATOR_CAPABILITY_MODE` still restores
eager behaviour. Reverting the PR restores slice 3's constant provider.
