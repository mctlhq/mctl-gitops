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
`proposed` (no verified decision exists yet). *Superseded 2026-11-09: the owner made
the merged mctl-api#968 bridge canonical; see the AMEND section below.*

This proposal adds a new, self-contained `orchestrator/assistants/` package in
`mctl-agents`: versioned input/output contracts, a `GlovoControlWorkflow`, its
activities behind ports, a transport-agnostic provider bridge port, a
standalone control-worker entrypoint pinned to namespace `mctl-assistants`, a
separate minimal Dockerfile, and a local disposable Temporal test harness. It
changes nothing in the existing DevLoop worker, queues, namespace or rollout,
and deploys nothing. Until #1043 produces a source-verified, independently
approved transport, the bridge compiles and is tested against a local fake
only, and the worker reports `BLOCKED_FOR_INTEGRATION` for the real transport.

## AMEND 2026-11-09 — alignment with the merged bridge (mctl-api#968)

Crosswalk M6-M10 and M1 (consumer side); design.md "Amendment 2026-11-09" has the table. These criteria replace the ones they name below.

- THE SYSTEM SHALL wait for provider results on the signal `bridge-result` with payload `{command_id, result_digest}`, dedupe on `command_id`, and accept a result only after reading it back from mctl-api with a matching digest.
- THE SYSTEM SHALL wait for approval by polling `read_approval` only; it SHALL register no approval signal.
- THE SYSTEM SHALL orchestrate only through mctl-api APIs (`dispatch_order`, `cancel_order`, `read_command_result` and the existing read/revalidate calls). It SHALL contain no bridge port, SHALL never compute a command id, and SHALL store the `cmd_` returned by mctl-api. (owner decision, option b)
- THE SYSTEM SHALL map every (`outcome`, `provider_effect`, `error_code`) triple of the vendored v1alpha1 enums by the the design "Result mapping (M9)" table, and IF `provider_effect` is `unknown` THEN `order_status` SHALL be `unknown` with no re-dispatch.
- THE SYSTEM SHALL take `approval_ref` and `fingerprint` from `GlovoControlInput` and SHALL NOT create an `aar_`. IF mctl-api reports a fingerprint mismatch at dispatch THEN THE SYSTEM SHALL end `refused`/`basket_changed`. Approval refusals SHALL be reported distinctly as `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `provider_disabled` or `tenant_busy`.
- THE SYSTEM SHALL accept `install_ref` as an M1a `gin_` id and `connection_ref` as an M1a `gcn_` id, and `tenant_ref`, `principal_ref`, `order_ref` only in the `tnr_`/`prr_`/`ordr_` forms minted by mctl-api.

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
  `resolving -> awaiting_approval -> dispatching -> settling -> completed`
  (`quoting` removed 2026-11-09, M10), or terminate in `refused`, `cancelled`, `expired` or `failed`.
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
- (Amended 2026-11-09) THE SYSTEM SHALL use the fingerprint and `approval_ref`
  bound by mctl-api at prepare, received in `GlovoControlInput`, and IF
  mctl-api reports a different fingerprint at dispatch THEN THE SYSTEM SHALL
  stop with `refused` (`basket_changed`).
- (Amended 2026-11-09) WHILE the input `aar_` is pending THE SYSTEM SHALL poll
  `read_approval` every `approval_poll_interval_s`, bounded by the receipt's
  expiry. It SHALL NOT create an `aar_`.
- IF the only evidence of consent is a `hir_` answer THEN THE SYSTEM SHALL NOT
  dispatch; the `hir_` id SHALL NOT be an accepted field of any dispatch input.
- (Amended 2026-11-09) WHEN the approval is `approved` and the scope
  revalidates as `live` THE SYSTEM SHALL call `dispatch_order` once (activity
  retries reuse the same call and get the same `cmd_`) and SHALL store the
  returned `cmd_`.
- WHEN a `bridge-result` signal arrives THE SYSTEM SHALL accept it only if its
  `command_id` equals the stored `cmd_` and the read-back digest matches, and
  SHALL treat a duplicate signal as a no-op.
- IF the provider effect is `unknown` THEN THE SYSTEM SHALL NOT re-dispatch and
  SHALL return `order_status=unknown`, leaving reconciliation to mctl-api's
  read-back (full map: the design "Result mapping (M9)").
- WHEN the workflow completes THE SYSTEM SHALL return a bounded
  `GlovoControlResult` with `order_status` and an opaque fake `handoff_ref`,
  and no provider payload, cookie, token or free text over 256 characters.

Integration gate (amended 2026-11-09):
- WHILE `ASSISTANTS_API_CONTRACT` pins no merged mctl-api control route
  contract THE SYSTEM SHALL refuse to construct a real `ControlApiPort` and
  SHALL report `BLOCKED_FOR_INTEGRATION` at worker startup when one is
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
- mctl-api routes, stores and authorization (mctl-api#953, #954, #957) and the
  merged bridge (mctl-api#968); this proposal codes against `ControlApiPort`.
- The public facade and the fake provider worker (mctl-telegram).
- Choosing the cross-namespace transport (decided 2026-11-09: mctl-api#968).
- Real Glovo access, payments, any LLM call from the control worker.
- A new scheduler or a second AutomationDefinition authority.

## Open questions

- Resolved 2026-11-09 (owner): mctl-api#968 is the canonical bridge; the
  workflow reaches it through mctl-api APIs only. The remaining gate is the
  control route contract (mctl-api#957 OPEN-3).
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
