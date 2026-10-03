# Role-aware capability discovery and MCP gateway contract

## Context

ADR 007 (`docs/adr/007-agent-definition-execution-profile-contract.md`) and
the `#227` resolver pilot (`orchestrator/resolver.py`) already answer "what
contract ran": `execute(agent, task)` materializes one immutable
`ExecutionPlan` carrying `tools`, `permissions`, `policy_ref`, budget,
timeout and sandbox. What no part of this repository answers is **what the
model could actually see and call**. Every non-shepherd options builder in
`orchestrator/options.py` connects the remote mctl MCP server
(`mctl_mcp_config(always_load=True)`) and grants the single wildcard
`mcp__mctl__*` (`_mctl_tool_globs()`, `options.py:57`). The wildcard is a
permission filter, not an exposure filter: the CLI connects the server and
loads every advertised tool schema into the first turn regardless of how
narrow the allow-list is. api.mctl.ai/mcp advertises on the order of seventy
tools today, so every investigator run pays for the full platform surface —
deploy, retire, tenant delete, domain, skill and agent-promotion tools it
will never call — before it has read one line of the issue.

This proposal defines and pilots the missing capability plane: a canonical
capability descriptor shared by remote MCP tools and execution-local tools,
a per-execution eligible set derived strictly from the resolved
`ExecutionPlan`, progressive (search-then-describe) discovery so schemas
enter context on demand, and an MCP gateway contract covering namespacing,
routing, identity propagation, failure semantics and tracing. The invariant
this work must make testable is the one ADR 009 already wrote down for
context (`docs/adr/009-context-snapshot-contract.md` sec. 5, which names
this issue by number): **discovery narrows, it never grants.** Eligibility
stays with `ExecutionProfile`; authorization stays with the `#197` policy
checkpoint and provider-side enforcement.

## User stories

- AS a platform engineer I WANT an execution to see only the capabilities its
  resolved `ExecutionProfile` declares SO THAT the boundary between declared
  permission and runtime exposure is a checked property rather than a
  convention.
- AS an agent (issue-investigator) I WANT to search capabilities by task
  intent and load only the schemas I need SO THAT my initial context is not
  dominated by tool definitions I will never use.
- AS a security reviewer I WANT proof that a capability excluded by the
  profile cannot be reached through discovery or the gateway SO THAT a
  ranking or search function never becomes a privilege-escalation surface.
- AS an incident responder I WANT a provider outage to be distinguishable
  from a legitimately empty capability set SO THAT a dead MCP connection can
  never again look like a valid silent success (the failure mode
  `orchestrator/mcp_guard.py` exists for).
- AS an auditor I WANT discovery and invocation decisions correlated to the
  execution identity and traced without arguments or results SO THAT I can
  reconstruct which capabilities a run considered and called without a new
  sensitive-data store.
- AS a maintainer I WANT a benchmark of initial tool-schema bytes and
  end-to-end token usage before and after progressive discovery SO THAT the
  claimed saving is measured rather than assumed.
- AS an operator I WANT one environment variable to restore today's eager
  exposure SO THAT rollback needs no code change or redeploy of a new image.

## Acceptance criteria (EARS)

- WHEN `execute(agent, task)` has produced an `ExecutionPlan` THE SYSTEM
  SHALL resolve exactly one sealed `CapabilitySet` whose members are the
  provider-advertised capabilities matching `ExecutionPlan.tools`, and SHALL
  record its `capability_set_id` and content hash in structured logs.
- WHILE a `CapabilitySet` is sealed THE SYSTEM SHALL treat it as immutable
  for the whole execution: no later discovery, ranking, model output or
  provider refresh may add a member.
- IF a provider advertises a capability that matches no entry in
  `ExecutionPlan.tools` THEN THE SYSTEM SHALL exclude it from the
  `CapabilitySet` and SHALL NOT expose its name, description or schema to
  the model.
- WHEN the gateway receives an invocation for a `capability_id` that is not
  a member of the sealed `CapabilitySet` THE SYSTEM SHALL refuse it with
  reason code `not-eligible`, SHALL NOT contact any provider, and SHALL
  emit a trace record of the refusal.
- WHEN a capability whose `consequence` is `consequential` is invoked THE
  SYSTEM SHALL submit it to the `#197` policy checkpoint before contacting
  the provider, and SHALL refuse it with reason code `policy-denied` on a
  deny verdict.
- WHILE the `#197` checkpoint implementation is absent THE SYSTEM SHALL use
  a named, logged pass-through adapter that reproduces today's behaviour
  exactly, SHALL record `policy_checkpoint: absent` on every invocation
  record, and SHALL NOT claim a policy decision was made.
- WHEN capability discovery is enabled for an agent THE SYSTEM SHALL expose
  to the model only the gateway's own tools (`capability_search`,
  `capability_describe`, `capability_invoke`) plus the built-in SDK tools the
  profile already grants, and SHALL NOT connect the remote mctl MCP server
  directly into the model's tool set.
- WHEN `capability_search` is called THE SYSTEM SHALL return at most
  `limit` compact rows (`capability_id`, title, one-line summary,
  `consequence`) drawn only from the sealed `CapabilitySet`, and SHALL NOT
  return input schemas.
- WHEN `capability_describe` is called with capability ids THE SYSTEM SHALL
  return full input schemas for at most `MAX_DESCRIBE_IDS` eligible ids and
  SHALL report `not-found` for any id outside the sealed set.
- WHILE more than one provider is configured THE SYSTEM SHALL assign each
  provider a unique execution-scoped alias and SHALL address every
  capability by the canonical id `mctl://<provider_type>/<provider_id>/<tool>`.
- IF two providers advertise a tool whose resolved SDK-visible name would
  collide THEN THE SYSTEM SHALL fail closed at set-sealing time with a named
  collision error and SHALL NOT silently rename, shadow or drop either.
- WHEN the gateway invokes a remote capability THE SYSTEM SHALL propagate
  the execution identity/correlation fields (`#196`: agent, environment,
  `temporal_workflow_id`, `argo_workflow_name`, `target_repository_sha`,
  definition/profile versions) as provider request metadata alongside the
  existing `MCTL_TOKEN` bearer credential.
- WHEN a capability is execution-local THE SYSTEM SHALL dispatch it in
  process and SHALL NOT route it through a remote network hop, while
  describing it with the same descriptor shape as a remote capability.
- WHEN discovery or invocation emits telemetry THE SYSTEM SHALL emit
  identifiers, hashes, counts, durations and reason codes only, and SHALL
  NOT emit tool arguments, tool results, or any string derived from them.
- IF a provider is unreachable, returns an error, or times out THEN THE
  SYSTEM SHALL report the distinct reason codes `provider-unavailable`,
  `provider-error` and `timeout` respectively, and SHALL NOT report an empty
  or partial capability set as a successful discovery.
- WHILE `ISSUE_INVESTIGATOR_CAPABILITY_MODE` is unset or `eager` THE SYSTEM
  SHALL build byte-identical `ClaudeAgentOptions` to today's path, and SHALL
  NOT import or start the gateway.
- WHEN `orchestrator/validate_manifest.py` runs THE SYSTEM SHALL compare the
  catalog `ExecutionProfile`'s declared tools against the options builder's
  actual `allowed_tools` for the capability mode the profile declares, so
  that the "manifest is a checked claim, not a second implementation" rule
  holds in both modes.
- WHEN the benchmark is run THE SYSTEM SHALL record, for one fixed issue and
  target SHA, the count and serialized byte size of tool schemas present in
  the initial model context and the end-to-end input/output token usage, in
  both `eager` and `discovery` mode, and SHALL state the sample size.

## Out of scope

- Replacing Temporal or Argo, or changing any workflow topology.
- A public or general-purpose MCP marketplace, registry UI, or catalog of
  third-party servers.
- Treating capability discovery, ranking or relevance as the security
  boundary; provider-side authorization stays authoritative.
- Proxying local filesystem, git, or CLI operations (`Read`, `Glob`, `Grep`,
  `Bash`, `Write`, `Edit`) through a remote MCP server.
- Implementing the `#197` policy checkpoint, `#195` trace pipeline, `#196`
  execution-identity store or `#199` evidence store. This proposal defines
  and consumes their seams and ships named adapters, nothing more.
- Changing investigator product behaviour: the prompt's task, the proposal
  triplet, the staging/publish rules and the budget are untouched beyond
  capability loading mechanics.
- Migrating `implementer`, `shepherd`, `service-agent`, `mentor` or
  `incident-responder` to discovery mode, or flipping the default mode.
- The follow-up `mctl` MCP-to-CLI adapter inside isolated sandboxes named in
  the issue; it stays a separate, independently reviewable change.
- Semantic/vector search or embeddings for ranking. The pilot ranker is
  lexical and its name/version is recorded so a better ranker can replace it
  without a contract change.

## Open questions

- **Where a sealed `CapabilitySet` durably lives.** ADR 009 left the same
  question open for `ContextSnapshot` (`retention: execution-record` names
  the intended home, persistence is a follow-up). Proceeding with the same
  answer: structured logs plus a `retention` class field now, mctl-api
  persistence tracked separately.
- **Whether `#197` will expose a synchronous in-process check or an
  out-of-process call.** Proceeding with a narrow synchronous
  `PolicyCheckpoint` protocol in `orchestrator/capability.py` plus an
  `AbsentPolicyCheckpoint` adapter, so the invocation path has one shape
  regardless of which #197 lands.
- **Which authority assigns `provider_id` once a second remote MCP server
  exists.** Proceeding with the mctl-gitops `ExecutionProfile` as the
  authority (providers are declared there, aliases derived deterministically
  from declaration order) because that is where every other execution-
  affecting input is already reviewed.
- **The exact catalog field name for the mode switch.** Proceeding with
  `spec.capabilityDiscovery: {mode, gatewayAlias}` under the existing
  `agents.mctl.ai/v1alpha2` profile; the field is additive and defaults to
  `mode: eager`, so an older catalog resolves to today's behaviour.
- **Consequence classification source.** MCP `ToolAnnotations`
  (`readOnlyHint`/`destructiveHint`) are advisory and not guaranteed present
  on mctl-api's tools. Proceeding with a checked-in classification table in
  this repo, defaulting an unclassified capability to `consequential`
  (fail-safe), with annotations used only to corroborate.
- **Token accounting methodology.** The repo has no tokenizer dependency
  (ADR 009 sec. 6 deliberately deferred token budgets). Proceeding with the
  SDK `ResultMessage` usage numbers plus serialized schema bytes, reported
  as a single-sample measurement with its variance stated.
