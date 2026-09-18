# Agent execution identity and runtime context (`ExecutionContext` contract)

## Context

Every governance capability the platform is building — execution traces
(#195), runtime policy checkpoints (#197), human approval (#198), execution
evidence (#199) — needs one prior thing that does not exist yet: a
well-defined answer to *who and what is executing, on whose behalf, in which
scope*. Today that answer is scattered and lossy. The Temporal control plane
knows the workflow id (`orchestrator/temporal/issue_ref.py:30`,
`dev-loop-mctlhq-<repo>-<number>`) and, after an approve signal, an approver
string (`orchestrator/temporal/workflows/dev_loop.py:787-800`). The boundary
into Argo carries a flat `dict[str, str]` of at most six keys
(`SubmitAndWaitInput.params`, `orchestrator/temporal/activities/argo.py:61-67`;
`issue_url`, `service`, `slug`, `approver`, `agent_image`, `agent_version`).
The durable ledger records eight fields
(`ExecutionRecord`, `orchestrator/temporal/activities/state.py:28-44`). The
agent container reconstructs whatever it needs from argv and environment, and
every `mcp__mctl__*` call it makes reaches mctl-api under one static shared
bearer token (`orchestrator/temporal/mctl_client.py:16-31`,
`orchestrator/options.py:43-51`) that names no run, no agent, no actor and no
environment.

This proposal defines the canonical, versioned `ExecutionContext` document and
the rules for minting, propagating, consuming and trusting it. It is
deliberately the same shape of deliverable as ADR 007
(`AgentDefinition`/`ExecutionProfile`) and ADR 009 (`ContextSnapshot`): a
normative contract plus one inert, stdlib-only schema module, with producers
wired into the investigator and implementer paths. It answers *who is
executing*; it never answers *what they may do* — that stays with #197, and
the schema is built so that a policy engine cannot accidentally read
permission out of it.

## User stories

- AS a platform operator I WANT every agent execution to carry one canonical
  identity document SO THAT an audit can say which agent version, acting for
  which human, in which environment, against which repository, produced a
  given commit or PR.
- AS the mctl-api MCP server I WANT each incoming `mcp__mctl__*` call to name
  the execution that issued it SO THAT I can attribute, rate-limit and later
  authorize calls without asking the calling agent to describe itself.
- AS a policy author (#197) I WANT a stable, versioned set of identity fields
  with an explicit trust label per field SO THAT a rule written today keeps
  the same meaning when the execution pipeline changes.
- AS a trace consumer (#195) I WANT the identity fields attached to spans to
  be exactly the fields on the execution record and the context snapshot
  SO THAT traces, ledger rows and snapshots join without a translation table.
- AS a security reviewer I WANT control-plane-asserted fields to be
  unforgeable by the sandboxed workload SO THAT a prompt-injected agent cannot
  relabel itself as a different agent, actor or environment.
- AS an agent author I WANT the context available as a single loaded object
  SO THAT I never reconstruct identity from argv, env vars and the issue body
  independently in each driver.

## Acceptance criteria (EARS)

### Schema

- WHEN the `ExecutionContext` schema module is imported THE SYSTEM SHALL
  expose a frozen, JSON-primitives-only document with `api_version`
  `identity.mctl.ai/v1alpha1` and `kind: ExecutionContext`.
- WHEN an `ExecutionContext` is sealed THE SYSTEM SHALL derive
  `content_hash = "sha256:" + sha256(canonical JSON of every field except
  content_hash, context_id and issued_at)` and
  `context_id = "ex-" + content_hash[7:23]`, matching the derivation ADR 009
  fixes for `ContextSnapshot` and the `"sha256:"` prefix convention of
  `orchestrator/resolver.py:301`.
- WHEN a document declares an `api_version` the loader does not know THE
  SYSTEM SHALL fail loudly rather than parse it partially, matching
  `orchestrator/manifest.py`'s unknown-version rule.
- WHEN a caller supplies a key the schema does not declare THE SYSTEM SHALL
  reject the document rather than ignore the key.
- WHILE a document is under `identity.mctl.ai/v1alpha1` THE SYSTEM SHALL
  accept only the closed vocabularies for `actor.type`, `trigger.type`,
  `workflow_type`, `environment` and `executor.type`, where `executor.type`
  reuses the values already used by `ExecutionClaimRequest.executor_type`
  (`orchestrator/temporal/activities/lifecycle.py:330-353`).
- IF a field name containing `allow`, `deny`, `permit`, `grant`, `authorized`
  or `role` is added anywhere in the schema THEN THE SYSTEM SHALL fail its
  own test suite, mirroring the executable boundary assertion ADR 009 sec. 5
  places on `ContextSnapshot`.

### Identity content

- WHEN an execution is minted THE SYSTEM SHALL distinguish, in separate
  blocks, the human `actor` (who asked), the `trigger` (what event carried
  the ask), the `executor` (which agent/service identity runs), and the
  `scope` (tenant, repository, environment, service, slug).
- WHEN the executing agent version is pinned by
  `resolve_agent_release` (`orchestrator/temporal/activities/registry.py:59`)
  THE SYSTEM SHALL copy `version` and `image_ref` into `executor`, and WHEN no
  release resolves THE SYSTEM SHALL record the empty string rather than claim
  a version that was never passed, matching `_record`'s existing rule
  (`orchestrator/temporal/workflows/dev_loop.py:524-563`).
- WHEN a DevLoop step runs THE SYSTEM SHALL record `temporal_workflow_id`,
  `temporal_run_id`, `argo_workflow_name`, `workflow_type` and a monotonic
  `step_sequence`, so a multi-step loop yields one root context per loop and
  one child per step sharing the same `trace_id`.
- WHEN an approve signal supplies an approver
  (`dev_loop.py:787-800`) THE SYSTEM SHALL record it as
  `actor{type: github_user, id, verification: signal-asserted}` and SHALL NOT
  silently substitute the literal `"unknown"` currently sent as the CWFT
  `approver` parameter (`dev_loop.py:897-905`) without marking
  `verification: unverified`.
- WHEN a context is minted THE SYSTEM SHALL carry a `trace_id` of 32 lowercase
  hex characters (W3C trace-context compatible) that is stable for the whole
  DevLoop execution and is the join key #195 consumes.

### Propagation

- WHEN `_run_cwft` submits any CWFT (`dev_loop.py:483-517`) THE SYSTEM SHALL
  include `execution_context_id` and `trace_id` in the `params` mapping so the
  identity crosses the Temporal to Argo boundary with the work.
- WHILE an agent container is running THE SYSTEM SHALL make the sealed context
  readable at the path named by `MCTL_EXECUTION_CONTEXT_FILE`, and the drivers
  (`orchestrator/run_issue_investigator.py`,
  `orchestrator/run_implementer.py`, `orchestrator/run_shepherd.py`) SHALL
  load it through one shared loader instead of re-deriving identity.
- WHEN the mctl MCP server config is built (`orchestrator/options.py:15`) THE
  SYSTEM SHALL add `X-Mctl-Execution-Context` and `X-Mctl-Trace-Id` headers
  alongside the existing `Authorization` header, so every `mcp__mctl__*` call
  is attributable without any cooperation from the model.
- WHEN an execution record is written (`state.py:47`) THE SYSTEM SHALL include
  `execution_context_id` and `trace_id` so the ledger row, the trace and the
  context join on one key.
- WHEN a `ContextSnapshot` is sealed THE SYSTEM SHALL derive its
  `ExecutionCorrelation` block (`orchestrator/context_snapshot.py:407-475`)
  from the `ExecutionContext` by projection rather than by a second, hand-built
  copy.

### Trust model

- WHILE a workload holds a context copy THE SYSTEM SHALL treat every field in
  it as advisory for logging and prompting only; the authoritative copy SHALL
  live in mctl-api, written only by the control plane.
- WHEN mctl-api receives a call carrying `X-Mctl-Execution-Context` THE SYSTEM
  SHALL resolve identity from its own stored record for that id and SHALL
  ignore any identity claim supplied in the request body or prompt.
- IF a workload presents an `execution_context_id` that is unknown, expired,
  terminal, or bound to a different Argo workflow than the caller's THEN THE
  SYSTEM SHALL refuse to attribute the call to that context and SHALL record
  the refusal.
- WHILE no `ExecutionContext` is available in a cluster run THE SYSTEM SHALL
  fail closed when `MCTL_REQUIRE_EXECUTION_CONTEXT` is set, and SHALL degrade
  to an explicitly `unverified`, locally-minted context outside the cluster so
  local development and tests keep working.
- WHEN the context is logged or emitted to a trace THE SYSTEM SHALL emit only
  `to_log_dict()`, which contains identifiers, versions and hashes and no
  secret, token, issue body, or any string derived from a retrieved payload.

### Documentation

- WHEN this proposal is implemented THE SYSTEM SHALL ship an ADR
  (`docs/adr/011-execution-identity-contract.md`) stating the schema, the
  per-field trust table (control-plane-asserted vs workload-declared), the
  versioning rule, and the explicit statement that identity is never
  authorization.

## Out of scope

- Any allow/deny decision, policy engine, policy checkpoint or enforcement
  logic — that is #197. This proposal adds no field a policy engine could read
  as permission.
- Replacing the shared static `MCTL_TOKEN` with per-run workload credentials.
  The binding check described here narrows what a stolen context id buys, but
  real per-run authentication is its own change in mctl-api and mctl-gitops.
- Implementing the #195 trace pipeline, exporters, or any OpenTelemetry
  wiring. The worker's `TelemetryConfig` stays metrics-only
  (`orchestrator/temporal/worker.py:394-426`); this proposal only mints and
  propagates the `trace_id` that pipeline will consume.
- The mctl-api server-side storage implementation and the CWFT parameter
  declarations in mctl-gitops. Both are named as required sibling changes with
  a compatible fallback, but their code lives in other repositories.
- Changing prompts, budgets, tools, models, or any agent behaviour.
- Evidence (#199) and context provenance (#199/ADR 009) payloads.

## Open questions

- **Per-run caller authentication.** Every activity and every agent uses one
  shared admin `MCTL_TOKEN`. mctl-api therefore cannot currently prove that
  the caller presenting `execution_context_id` is the run it was issued to.
  Interpretation taken: mint the context with an `executor.binding`
  (`argo_workflow_name` plus agent name) and have mctl-api reject a mismatch
  once the Argo workflow name is observable on the call; until it is, the id
  is non-secret and attribution is best-effort-but-tamper-evident. A
  per-run token or Kubernetes workload identity is the real fix and is worth
  its own issue.
- **Where the authoritative context is stored.** Assumed to live next to
  `ExecutionRecord` in mctl-api Postgres (the same home ADR 009 names for
  sealed snapshots, `retention: execution-record`). If mctl-api prefers a
  separate table or a different endpoint than
  `/api/v1/agents/executions/context`, only the client in
  `orchestrator/temporal/activities/identity.py` changes.
- **Tenant field.** `mctl-agents` runs today under a single tenant and the
  mctl-api team-scoping model is not represented anywhere in this repo. The
  schema reserves `scope.tenant` and defaults it to `"mctlhq"` rather than
  inventing a multi-tenant mapping.
- **CWFT parameter declarations.** mctl-api passes undeclared parameters
  through (noted at `orchestrator/temporal/workflows/incidents.py:100-106`),
  which is how `agent_image`/`agent_version` already ride along. The new
  parameters are assumed to ride the same way until mctl-gitops declares them;
  if that pass-through is tightened, the gitops change becomes a hard
  prerequisite.
- **Root vs step granularity for the ledger.** One context per DevLoop step is
  assumed (matching ADR 009's root/child snapshot chaining). If mctl-api would
  rather hold one row per loop, the step fields move into the ledger row and
  the child contexts become derived values.
