# Assistants M1: trusted Glovo control workflow with fenced cross-namespace fake provider dispatch

## Context

The multi-tenant Glovo MCP needs a trusted control workflow that drives one
assistant order end to end: resolve a synthetic connection and its owner, quote a
fake basket, ask a human for an `aar_` approval, and only then let an isolated
fake provider mutate the basket. The merged PoC (mctl-telegram#1187) is a nested
test module only. Repository ownership is fixed by .github#324: `mctl-agents`
owns the orchestration code, `mctl-api` owns authorization (connections in
mctl-api#953, order index and the `aar_` write boundary in mctl-api#954), and
`mctl-telegram` owns the public facade and the private fake worker. The
cross-namespace transport between the control namespace `mctl-assistants` and
the provider is the subject of spike mctl-agents#1043, whose proposal is still
`proposed` (no verified decision exists yet).

This proposal adds a new, self-contained `orchestrator/assistants/` package in
`mctl-agents`: versioned input/output contracts, a `GlovoControlWorkflow`, its
activities behind ports, a transport-agnostic provider bridge port, a
standalone control-worker entrypoint pinned to namespace `mctl-assistants`, a
separate minimal Dockerfile, and a local disposable Temporal test harness. It
changes nothing in the existing DevLoop worker, queues, namespace or rollout,
and deploys nothing. Until #1043 produces a source-verified, independently
approved transport, the bridge compiles and is tested against a local fake
only, and the worker reports `BLOCKED_FOR_INTEGRATION` for the real transport.

## User stories

- AS mctl-api (sole authenticated Temporal caller for `mctl-assistants`) I WANT
  a control workflow with a versioned, bounded input/output contract and a
  workflow id I derive from server-owned scope SO THAT no client-supplied id,
  credential or argument can address another tenant's or user's order.
- AS a tenant member who owns a synthetic Glovo connection I WANT the provider
  to mutate my fake basket only after I approve exactly that basket with an
  `aar_` SO THAT a model, a clarification answer (`hir_`) or a replay can never
  place an order for me.
- AS a platform operator I WANT the control worker to be a separate image and
  process bound to `mctl-assistants` only, with no provider session and no
  DevLoop code SO THAT a bug in assistants cannot touch DevLoop and vice versa.
- AS a security reviewer I WANT negative tests for cross-namespace,
  cross-tenant, cross-user, stale-install and revoked-connection cases SO THAT
  the isolation is shown, not asserted.
- AS the M1 owner I WANT the real cross-namespace bridge wired only after
  #1043 is verified and approved SO THAT nobody invents a raw cross-namespace
  Activity in the meantime.

## Acceptance criteria (EARS)

Contracts and build:
- THE SYSTEM SHALL define `GlovoControlInput` and `GlovoControlResult` in
  `orchestrator/assistants/contracts.py` with `schema_version`
  `assistants.mctl.ai/glovo-control/v1alpha1`, every string length-bounded,
  every collection size-bounded, and unknown fields rejected; a JSON Schema
  generated from them SHALL be committed under
  `orchestrator/assistants/schemas/` and a test SHALL fail when the code and the
  committed schema (and its recorded sha256) diverge.
- WHEN the control image is built from `Dockerfile.assistants-control` THE
  SYSTEM SHALL install dependencies with `uv sync --locked` from the existing
  `uv.lock`, use a digest-pinned base, run as non-root, and contain neither
  `claude_agent_sdk`, `gh`, Node, nor any `orchestrator.temporal.workflows`
  DevLoop module in the worker's import graph.
- WHEN a workflow input carries an unknown `schema_version` THE SYSTEM SHALL
  fail the workflow with a non-retryable `contract_version_unsupported` error
  before any activity runs.

Namespace and caller fencing:
- WHEN the control worker starts with `TEMPORAL_NAMESPACE` other than
  `mctl-assistants`, or a task queue other than `mctl-assistants-control`, THE
  SYSTEM SHALL refuse to start (exit non-zero) without connecting.
- WHILE the control worker runs THE SYSTEM SHALL register only the assistants
  workflow and assistants activities, create no Temporal schedule, and run no
  execution-request dispatcher.
- THE SYSTEM SHALL contain no code path in `orchestrator/assistants/` that
  constructs a Temporal client for any namespace other than the one the worker
  was started with, and no activity that starts, signals, queries, lists or
  terminates any workflow.
- WHEN a workflow starts THE SYSTEM SHALL recompute the expected workflow id
  from the input's opaque `tenant_ref`, `principal_ref`, `install_ref` and
  `order_ref` and IF it differs from `workflow.info().workflow_id` THEN THE
  SYSTEM SHALL fail non-retryably with `workflow_id_scope_mismatch`.

Lifecycle and revalidation:
- WHEN the workflow runs THE SYSTEM SHALL progress only through
  `resolving -> quoting -> awaiting_approval -> dispatching -> settling ->
  completed`, or terminate in `refused`, `cancelled`, `expired` or `failed`.
- WHEN any state transition is about to happen, and at least every
  `revalidate_interval_s` (default 300) while waiting, THE SYSTEM SHALL call
  `revalidate_scope` (tenant membership, install id and revision, connection
  `gcn_` not revoked) through mctl-api, and IF it returns anything but `live`
  THEN THE SYSTEM SHALL stop with `refused` and make zero provider dispatches.
- IF `revalidate_scope` cannot get an answer (mctl-api unavailable) THEN THE
  SYSTEM SHALL treat the scope as not live for that transition (fail closed)
  and retry with bounded backoff, never proceeding on an unknown answer.
- WHEN the workflow is cancelled THE SYSTEM SHALL issue no new provider
  dispatch, SHALL only release or settle what mctl-api already reserved, and
  SHALL never re-activate a revoked connection, a revoked consent or a spent
  `aar_`.

Approval and dispatch:
- THE SYSTEM SHALL bind the basket fingerprint and the consent reference to the
  execution at the first successful quote and IF a later quote, approval or
  dispatch presents a different fingerprint THEN THE SYSTEM SHALL stop with
  `refused` (`fingerprint_mismatch`).
- WHEN the workflow requests approval THE SYSTEM SHALL ask mctl-api to create
  an `aar_` whose intent hash is computed with
  `orchestrator.action_approvals.intent_hash` over the order binding, and wait
  for the `assistants_approval_decided` signal (payload: the `aar_` id only) or
  a poll tick, bounded by the receipt's expiry.
- IF the only evidence of consent is a `hir_` answer THEN THE SYSTEM SHALL NOT
  dispatch; the `hir_` id SHALL NOT be an accepted field of any dispatch input.
- WHEN the approval is `approved` and the scope revalidates as `live` THE
  SYSTEM SHALL request exactly one provider effect through the bridge port with
  a `command_id` derived deterministically from workflow id, step and attempt.
- WHEN a provider result arrives THE SYSTEM SHALL accept it only if its
  `command_id`, `execution_id` and fingerprint match the pending command, and
  SHALL treat a duplicate result as a no-op.
- IF the provider outcome is `unknown` THEN THE SYSTEM SHALL NOT re-dispatch and
  SHALL return `order_status=unknown`, leaving reconciliation to mctl-api's
  read-back.
- WHEN the workflow completes THE SYSTEM SHALL return a bounded
  `GlovoControlResult` with `order_status` and an opaque fake `handoff_ref`,
  and no provider payload, cookie, token or free text over 256 characters.

Bridge integration gate:
- WHILE no verified decision memo from #1043 with an independently approved
  dependency is pinned in `orchestrator/assistants/bridge_decision.json` THE
  SYSTEM SHALL refuse to construct any real transport and SHALL report
  `BLOCKED_FOR_INTEGRATION` at worker startup when a real transport is
  requested.
- THE SYSTEM SHALL NOT implement or register a cross-namespace Temporal
  Activity, a raw Nexus endpoint, or any direct provider-to-control signal.

Resource budgets:
- THE SYSTEM SHALL set explicit `max_concurrent_activities`,
  `max_concurrent_workflow_tasks` and per-activity timeouts on the control
  worker, and a workflow execution timeout, all from bounded env settings.
- IF mctl-api's admission answer for a tenant is `tenant_cap_reached` THEN THE
  SYSTEM SHALL end with `refused` (`tenant_cap_reached`) without dispatch.

Safety:
- THE SYSTEM SHALL contain no Glovo HTTP client, no provider cookie or session
  handling, and no checkout, charge or payment operation; the only provider is
  synthetic.

## Out of scope

- Deploying anything: no Temporal namespace creation, no gitops service, no
  credentials, no Vault/ESO change (mctl-gitops#2457 and #2456 follow-ups).
- Changes to the DevLoop worker (`orchestrator/temporal/`), its queues,
  namespace `mctl-agents`, schedules, release-deploy paths or kuptsi.
- mctl-api routes, stores and authorization (mctl-api#953, #954) and the bridge
  routes proposed by #1043; this proposal codes against ports for them.
- The public facade and the fake provider worker (mctl-telegram).
- Choosing the cross-namespace transport (that is #1043).
- Real Glovo access, payments, any LLM call from the control worker.
- A new scheduler or a second AutomationDefinition authority.

## Open questions

- #1043 is still `proposed`; its likely outcome is `API_BRIDGE_SELECTED`. This
  proposal codes the bridge as a port and ships `BLOCKED_FOR_INTEGRATION` until
  a verified decision is pinned. Who records the "independently approved
  dependency" (owner name and PR) that unblocks integration?
- mctl-api#953/#954 route names and payloads are proposals, not merged APIs.
  The activity ports mirror them; any change there means a contract update here.
- Image publishing: should CI push `ghcr.io/mctlhq/mctl-agents-assistants-control`
  on release (proposed: only behind a repo variable that defaults off, never
  wired into release-deploy `values_path`), or only build it as a CI smoke until
  #2457 is approved? Proposal assumes build-only by default.
- Workflow id format is chosen here
  (`asst-glovo-<tenant_ref>-<principal_ref>-<install_ref>-<order_ref>`); mctl-api
  must adopt the same derivation. Confirm with the mctl-api owner.
- Live Temporal denial of DevLoop-namespace calls (start, signal, query, list,
  terminate) cannot be proven locally: the dev server has no authorizer. Local
  tests prove it structurally; the live matrix depends on #2456 enforcement.
- Exact default revalidation interval, workflow execution timeout and
  concurrency caps; proposed defaults are 300 s, 2 h, 20 activities and 20
  workflow tasks, to be tuned with real numbers.
