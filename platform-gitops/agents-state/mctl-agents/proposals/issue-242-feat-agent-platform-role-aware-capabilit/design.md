# Design: issue-242-feat-agent-platform-role-aware-capabilit

> **Revision 2 (2026-09-23): delivered in three slices.** The design below is
> unchanged. `tasks.md` now carries slice 1 only (ADR 017, `orchestrator/capability.py`,
> the consequence table, the `PolicyCheckpoint` seam); the gateway, the builder
> and the investigator mode follow as slices 2 and 3 after slice 1 merges. The ADR
> is numbered 017: 011 is taken three times, 015 and 016 are claimed by the #199 and
> #198 proposals.

## Current state

**Tool exposure is one wildcard, applied eagerly, in five of six agents.**
`orchestrator/options.py` builds every agent's `ClaudeAgentOptions`:

- `mctl_mcp_config(always_load=True)` (`options.py:15`) returns the single
  remote server entry `{"mctl": {"type": "http", "url": MCTL_MCP_URL,
  "headers": {"Authorization": "Bearer <MCTL_TOKEN>"}, "alwaysLoad": True}}`,
  or `{}` when `MCTL_TOKEN` is unset.
- `_mctl_tool_globs()` (`options.py:57`) returns `["mcp__mctl__*"]` when that
  config is non-empty, `[]` otherwise.
- `build_service_agent_options` (`:279`), `build_implementer_agent_options`
  (`:300`), `build_mentor_options` (`:334`), `build_incident_responder_options`
  (`:348`) and `build_issue_investigator_options` (`:387`) each splice that
  wildcard into `allowed_tools` beside the built-ins. `build_shepherd_options`
  (`:476`) is the sole exception: `allowed_tools=["Read"]`, `mcp_servers={}`.

`allowed_tools` is a permission filter. Exposure is decided by which servers
are connected: with `alwaysLoad: True` the CLI blocks first-turn dispatch
until the mctl server handshake completes and then carries **every**
advertised tool schema into the first turn. The live api.mctl.ai/mcp surface
is on the order of seventy tools (tenant create/delete, deploy/retire,
rollback, domains, previews, OpenClaw identity/skills, agent publish/promote/
rollback, incidents, workflows, lifecycle ownership). An investigator that
reads an issue and writes three markdown files pays for all of it, every run.

**The eligible set already exists as data — nothing consumes it as an
exposure decision.** `orchestrator/resolver.py` (the `#227` pilot, documented
in `docs/resolver-pilot-status.md`) parses the mctl-gitops catalog
(`platform-gitops/agent-platform/execution-profiles/issue-investigator-default/profile.yaml`
and `releases/shadow/issue-investigator.yaml`) and materializes one frozen
`ExecutionPlan` (`resolver.py:226`) with `tools: tuple[str, ...]`,
`permissions`, `policy_ref`, `budget_usd`, `timeout_seconds`,
`target_repository_sha` and content hashes, plus `to_log_dict()`/`log()`.
`build_issue_investigator_options_from_plan` (`options.py:422`) maps
`plan.tools` onto `allowed_tools`, with one carefully argued rule: the mctl
wildcard survives only if **both** the profile grants it and `MCTL_TOKEN` is
configured (`options.py:459-462`), because treating configuration alone as
the condition would hand back tools a profile deliberately withheld. So the
allow-list is honoured — but the remote server is still connected wholesale
and every schema still loads.

**The claim is checked by static set equality, across two repositories.**
`orchestrator/validate_manifest.py:351` asserts
`set(options.allowed_tools) == set(manifest.tool_allow)` for v1alpha1
manifests, and `:610` asserts the catalog profile's `spec.tools` equals the
builder's actual `allowed_tools` for the v1alpha2 investigator. Any change to
what a builder puts in `allowed_tools` is therefore a lockstep change with
the mctl-gitops catalog, and `tests/test_manifest.py` goes red on main the
moment the two disagree (the raised `ISSUE_INVESTIGATOR_BUDGET_USD` default
in `options.py` documents exactly that bite).

**Connectivity is verified, not assumed.** `orchestrator/mcp_guard.py` polls
`client.get_mcp_status()` until the `mctl` server reports `connected`,
because a dead `MCTL_TOKEN` or an api.mctl.ai outage otherwise reproduces
"zero mcp__mctl__* tools" as a silent success. `_run_agent`
(`run_issue_investigator.py:1285`) calls it with `fatal=False`.

**The adjacent contracts are written and name this issue.** ADR 009
(`docs/adr/009-context-snapshot-contract.md`) ships `orchestrator/
context_snapshot.py` — a stdlib-only, frozen-dataclass, `seal()`-based
schema with `sha256:`-prefixed hashes, derived ids, closed vocabularies,
bounded string fields, unknown-key rejection in `from_dict`, and a boundary
table (sec. 5) whose first row assigns *capability eligibility* to
`ExecutionProfile` and **mctlhq/mctl-agents#242** — this issue — with the
rule "a source recorded here grants no tool access." Its non-goals say
plainly that `#242` capability discovery is not implemented. `#195` traces,
`#196` execution identity and `#197` policy checkpoints have no
implementation in this repo at all today (`grep` finds only ADR references);
the only concrete correlation shape that exists is ADR 009's
`ExecutionCorrelation` block.

**Two unused seams already exist in the SDK the repo pins**
(`claude-agent-sdk==0.2.136`): `create_sdk_mcp_server(name, version, tools)`
plus the `@tool` decorator build an **in-process** MCP server registered
through the same `mcp_servers` dict; and `ClaudeAgentOptions` carries
`can_use_tool` (a `CanUseTool` callback returning
`PermissionResultAllow`/`PermissionResultDeny`) and `strict_mcp_config`,
neither of which this repo sets today. The only hook in use is
`_command_audit_hooks()` (`options.py:259`), a `PreToolUse` matcher that
prints Bash commands. The `mcp` client package (`mcp.client.streamable_http`)
is already installed as a pinned transitive dependency.

## Proposed solution

Four artifacts, in the shape ADR 007 and ADR 009 established: a normative
ADR, a stdlib-only contract module, a runtime module behind a default-off
flag, and a benchmark.

### 1. ADR 017 — `docs/adr/017-capability-discovery-and-gateway-contract.md`

Normative for everything below and for `#197`/`#195` when they land: the
descriptor shape and field owners, the sealing/identity rule, the
eligibility-narrowing invariant, namespacing and collision rules, the
gateway's routing/identity/failure semantics, and the boundary table row
that mirrors ADR 009 sec. 5 in the opposite direction ("discovery may record
that a capability exists and rank it; it may never widen
`ExecutionPlan.tools` and it is not a policy decision").

### 2. `orchestrator/capability.py` — the contract (stdlib only)

Modelled field-for-field on `orchestrator/context_snapshot.py`: frozen
dataclasses, JSON primitives, `from_dict` rejecting unknown keys, bounded
string lengths, `sha256:`-prefixed hashes, `seal()` as the only constructor
that fills identity, and a `to_log_dict()` carrying counts and hashes only.
`apiVersion: capability.mctl.ai/v1alpha1`.

- **`CapabilityDescriptor`** — `capability_id` (canonical
  `mctl://<provider_type>/<provider_id>/<tool>`), `tool_name` (the
  SDK-visible `mcp__<alias>__<tool>` or built-in name), `provider`
  (`ProviderRef{type: "mcp-remote" | "mcp-local" | "sdk-builtin", id, alias,
  endpoint_ref}`), `title`, `summary` (bounded, search-index text),
  `keywords`, `input_schema_hash`, `input_schema_bytes`, `consequence`
  (`read-only | mutating | consequential`), `matched_tool_pattern` (the
  `ExecutionPlan.tools` entry that made it eligible), `annotations`.
  Remote and execution-local capabilities use this one shape; only
  `provider.type` distinguishes them, which is what keeps the discovery
  surface uniform while the execution boundary stays different.
- **`CapabilitySet`** — `execution` (an `ExecutionCorrelation` block
  field-identical to ADR 009 sec. 1 so both documents join on the same keys),
  `plan_tools` (the verbatim `ExecutionPlan.tools`), `providers`,
  `capabilities`, `excluded_count`, `strategy` (`name`, `version`,
  `ranker_name`, `ranker_version`), `retention`, then `content_hash` and
  `capability_set_id = "cap-" + content_hash[7:23]` filled by `seal()`.
  `validate()` enforces the narrowing invariant: every member's
  `matched_tool_pattern` is an element of `plan_tools`, and every
  `tool_name` matches it under the CLI's own `fnmatch` semantics.
- **`DiscoveryDecision`** — `capability_id`, `rank`, `score | null`,
  `reason_code`, `included`. **`InvocationRecord`** — `capability_id`,
  `capability_set_id`, `outcome`, `reason_code`, `duration_ms`,
  `policy_checkpoint` (`absent | allowed | denied`),
  `arguments_hash`/`result_hash` (`sha256:` of the serialized bytes, never
  the bytes). No argument, result or free-text payload field exists, and
  `from_dict`'s unknown-key rejection keeps one from being smuggled in.
- **`PolicyCheckpoint`** protocol + `AbsentPolicyCheckpoint` — a single
  `check(descriptor, correlation) -> CheckpointVerdict` seam. The absent
  adapter returns `allowed` with `policy_checkpoint: absent` recorded on
  every invocation, so the pilot cannot claim a decision was made, and `#197`
  replaces exactly one object when it ships.
- Closed reason-code vocabulary: `ok`, `not-eligible`, `not-found`,
  `policy-denied`, `invalid-arguments`, `provider-unavailable`,
  `provider-error`, `timeout`, `collision`.

Stdlib-only means the Temporal worker can import it (ADR 008's 256Mi
constraint, `tests/test_worker_isolation.py`).

### 3. `orchestrator/capability_gateway.py` — the runtime (SDK + mcp client)

Imported lazily inside `_run_agent`, exactly like `resolver`/`options`
already are (`run_issue_investigator.py:1286-1301`), so worker isolation
holds.

- `resolve_eligible(plan, correlation, providers) -> CapabilitySet`: connects
  each declared provider once (remote: `mcp.client.streamable_http` session
  with the `MCTL_TOKEN` bearer header, `list_tools()`; local: an in-process
  registry), matches advertised names against `plan.tools` with `fnmatch`,
  classifies consequence from the checked-in table, and seals. A provider
  that fails to list raises `provider-unavailable` rather than sealing a
  smaller set — the `mcp_guard.py` lesson, restated at set level: a short set
  and a broken provider must never look alike.
- **Namespacing/collision.** `provider.alias` is execution-scoped and
  assigned deterministically from the profile's provider declaration order;
  `capability_id` is the fully-qualified `mctl://...` URI; the SDK-visible
  name stays `mcp__<alias>__<tool>` so nothing about the CLI's naming rules
  changes. Two providers resolving to the same `tool_name`, or two providers
  claiming one alias, is a `collision` error at sealing time — fail closed,
  never a silent rename or shadow.
- **The gateway server.** `create_sdk_mcp_server("capability", tools=[...])`
  with three `@tool`s:
  - `capability_search(query, limit)` — lexical rank over
    `title`/`summary`/`keywords` of the sealed set; returns compact rows
    (`capability_id`, title, one-line summary, `consequence`), never schemas.
  - `capability_describe(capability_ids)` — full input schemas for at most
    `MAX_DESCRIBE_IDS` eligible ids; `not-found` for anything outside the set
    (an id outside the set is indistinguishable from a nonexistent one, so
    discovery leaks nothing about withheld capabilities).
  - `capability_invoke(capability_id, arguments)` — membership check against
    the sealed set, then `PolicyCheckpoint.check`, then dispatch: remote via
    the provider session, execution-local **in process, with no network
    hop**. Returns the provider result or a typed failure carrying one reason
    code.
- **Identity propagation (#196).** Every remote call carries the correlation
  fields as request metadata (`agent`, `environment`, `temporal_workflow_id`,
  `argo_workflow_name`, `target_repository_sha`, definition/profile versions,
  `capability_set_id`) alongside the existing bearer credential. The
  credential remains the thing the provider authorizes on; the metadata is
  for correlation, and the ADR says so, so a future reader cannot mistake it
  for an authorization claim.
- **Tracing (#195).** One `to_log_dict()` line per sealed set and per
  invocation — ids, hashes, counts, durations, reason codes. No arguments, no
  results, no strings derived from them, matching ADR 009 sec. 5's trace row.

### 4. Options/driver integration, behind a default-off flag

`build_issue_investigator_options_from_plan(plan, repo_dir, proposal_dir,
gateway=None)`: when `gateway` is `None` the function is byte-for-byte what
it is today. When a gateway is passed, `mcp_servers` becomes
`{"capability": <sdk server config>}` (the remote mctl server is **not**
connected into the model's tool set), `allowed_tools` replaces
`mcp__mctl__*` with `mcp__capability__*`, and `strict_mcp_config=True`
prevents any project-level settings file from reintroducing a server. The
mode is read per call from `ISSUE_INVESTIGATOR_CAPABILITY_MODE`
(`eager` default, `discovery` opt-in) in `run_issue_investigator.py`, mirroring
`_resolver_mode()` (`run_issue_investigator.py:108`) including the "read
fresh, not cached at import" rule and the printed
`[capability] capability_mode=...` line. Discovery mode requires
`ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`, since without a plan there is
no eligible set to derive; the combination `legacy + discovery` is rejected
at startup rather than half-applied.

`mcp_guard.ensure_mctl_connected` keeps working unchanged in eager mode. In
discovery mode the equivalent positive verification moves to
`resolve_eligible`, which either seals a set against a live provider or
fails with `provider-unavailable`; the guard's contract ("a connection you
cannot verify is a connection you cannot trust") is preserved, not dropped.

A ~15-line prompt addition in `_build_prompt` tells the agent, in discovery
mode only, to search-then-describe before invoking. Eager-mode prompt bytes
are unchanged, which keeps the prompt hash stable for the default path.

### 5. Keeping the checked claim checkable

Narrowing `allowed_tools` breaks `validate_manifest.py:610`'s set equality
unless the catalog says so. The profile therefore gains an additive
`spec.capabilityDiscovery: {mode: eager|gateway, gatewayAlias: capability,
providers: [...]}` (mctl-gitops), and `validate_manifest.py` resolves the
builder's claim **for the mode the profile declares**. A catalog without the
field means `mode: eager`, i.e. today's exact comparison. The claim stays one
implementation checked against one declaration, in both modes.

### 6. Benchmark — `tools/capability_bench.py`

Runs one fixed issue at one fixed target SHA in both modes and writes
`docs/benchmarks/capability-discovery.md`: advertised tool count and
serialized schema bytes present in the initial context (from
`client.get_mcp_status()`'s `McpServerStatus`/`McpToolInfo` in eager mode, and
from the sealed `CapabilitySet` plus the three gateway schemas in discovery
mode), end-to-end input/output tokens and cost from the SDK `ResultMessage`,
turn count, and wall clock. It reports sample size honestly: schema bytes are
deterministic, token totals are one sample of a non-deterministic run, and the
number that decides the pilot is end-to-end tokens — extra search/describe
turns can eat the initial-context saving, and the benchmark exists to catch
that rather than to confirm a hope.

## Alternatives

1. **Filter server-side: have mctl-api advertise a per-role tool subset.**
   Genuinely cheaper in context and arguably the right long-term home, but it
   makes the MCP server the owner of a decision ADR 007 assigns to the
   reviewed `ExecutionProfile`, gives execution-local tools no path into the
   same descriptor, and requires a cross-repo API change before anything can
   be measured here. Dropped as the primary mechanism, kept as a
   complementary optimisation the gateway can consume unchanged once it
   exists (fewer advertised tools simply means a smaller sealed set).
2. **Enumerate explicit tool names in the profile instead of `mcp__mctl__*`.**
   Cheap, static, and it does tighten the allow-list — but it does not solve
   the stated problem: the server is still connected and every schema still
   enters context, because `allowed_tools` filters permission, not exposure.
   It also freezes the investigator's toolbox into a file that must be
   re-reviewed in another repository whenever mctl-api adds a tool. Dropped
   as insufficient; the narrowing it offers is subsumed by `plan.tools`
   matching in `resolve_eligible`.
3. **Deploy a standalone MCP aggregator/proxy service in-cluster and point
   every agent at it.** The textbook gateway shape, and the right answer once
   several unrelated remote servers exist. Dropped for this pilot: it adds a
   deployment, a second identity hop and a new failure domain; it cannot host
   execution-local tools without violating the issue's own non-goal about
   proxying local filesystem/git operations; and mctl governance (profile
   eligibility, `#197` checkpoints, correlation) would have to be
   reimplemented server-side, which the issue explicitly warns against. The
   in-process server reuses the existing process identity and the existing
   connectivity-verification model, and ADR 017 keeps the contract
   transport-agnostic so the gateway can be lifted out later without changing
   descriptors.
4. **Ship discovery with no policy seam and let `#197` retrofit it.**
   Dropped: an invocation path built without a checkpoint tends to grow
   callers that assume none exists, and the pilot would then be the thing
   `#197` has to unpick. A one-method protocol plus an explicitly named
   `AbsentPolicyCheckpoint` costs almost nothing and makes the absence
   visible in every invocation record.

## Platform impact

- **Migrations.** None in this repo's data. One additive, defaulted field in
  the mctl-gitops `ExecutionProfile` schema (`spec.capabilityDiscovery`), and
  when the pilot is enabled, a matching `spec.tools` value for the gateway
  mode. No mctl-api schema change; no `.status.yaml` change; no manifest
  version bump for any other agent.
- **Backward compatibility.** Default `eager` keeps
  `build_issue_investigator_options*` byte-identical, keeps the remote server
  connected with `alwaysLoad`, and leaves the other five agents untouched.
  `capability_gateway` is never imported in eager mode. An older catalog
  without `capabilityDiscovery` resolves to eager.
- **Cross-repo lockstep.** This is the main sequencing risk: the
  `validate_manifest` equality check spans mctl-agents and mctl-gitops, and
  `docs/resolver-pilot-status.md` records that exactly this coupling turned
  `tests/test_manifest.py` red on main once already. Mitigation: mode-aware
  validation lands and is tested against a fixture **before** any catalog
  edit, so the eager comparison is provably unchanged when the field appears.
- **Dependency.** `mcp` is promoted from transitive to a direct pinned
  dependency in `pyproject.toml`, following the precedent set for `httpx`.
  No new package is added; `uv.lock` already pins it.
- **Worker isolation.** `orchestrator/capability.py` stays stdlib-only and
  importable by the Temporal worker; `orchestrator/capability_gateway.py`
  imports the SDK and the mcp client and must only be imported inside
  `_run_agent`. `tests/test_worker_isolation.py` is extended to assert both.
- **Resource impact.** One `list_tools` round trip per execution (cached for
  the run) plus one sha256 per descriptor; the gateway adds no process. The
  expected saving is the bulk of the initial tool-schema payload; the cost is
  one or two extra model turns for search/describe. Net effect is measured,
  not assumed — see the benchmark.
- **Risks and mitigations.**
  - *Discovery is slower or more expensive end to end.* The benchmark is an
    acceptance criterion, not a report; if end-to-end tokens regress the
    pilot stays off and the ADR/contract still stands.
  - *The gateway becomes a single point of failure for all mctl access.*
    Failure reason codes are distinct and traced, `resolve_eligible` fails
    closed rather than sealing a quietly short set, and rollback is one env
    var.
  - *Discovery drifts into authorization.* Mitigated the way ADR 009
    mitigated the mirror-image risk: a recursive field-name test asserting no
    `allow`/`deny`/`permit`/`grant`/`authorized` token appears in the
    descriptor schema, a narrowing-invariant test, and an import-direction
    test proving `orchestrator/capability.py` pulls in stdlib only.
  - *A capability is misclassified as `read-only` and skips the checkpoint.*
    Unclassified defaults to `consequential`; the classification table is
    checked in, reviewed, and covered by a test asserting every advertised
    mctl tool has an entry.
  - *The model cannot find a capability it needs and silently degrades.* The
    investigator's prompt already tolerates absent mctl tools
    (`ensure_mctl_connected(fatal=False)`), and discovery failures are logged
    per call rather than swallowed; the compatibility test suite compares
    proposal output across modes for the pilot issue set.
- **Security.** The eligible set can only shrink relative to
  `ExecutionPlan.tools`; provider-side authorization (mctl-api, GitHub,
  Kubernetes) remains the only enforcement, unchanged. The gateway holds the
  same `MCTL_TOKEN` the CLI holds today — it is not a new credential, and
  descriptors never carry credentials, arguments or results.
