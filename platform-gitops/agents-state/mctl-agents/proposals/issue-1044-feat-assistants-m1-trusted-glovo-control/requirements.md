# Assistants M1: trusted Glovo control workflow with fenced cross-namespace fake provider dispatch

## Context

The multi-tenant Glovo MCP needs a trusted control workflow that drives one
assistant order end to end: resolve a synthetic connection and its owner, quote a
fake basket, ask a human for an `aar_` approval, and only then let an isolated
fake provider mutate the basket. The merged PoC (mctl-telegram#1187) is a nested
test module only. Repository ownership is fixed by .github#324: `mctl-agents`
owns the orchestration code, `mctl-api` owns authorization (connections in
mctl-api#959-#961, order index in #988, the `aar_` write boundary in #989, control routes in #985,
prepare and facade in #957; round 7 replaced the parent issues #953 and #954 by these slices), and
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
- THE SYSTEM SHALL orchestrate only through mctl-api APIs (`read_approval`, `dispatch_order`, `cancel_order` and `read_command_result`: exactly the four routes of mctl-api#985 §2a; there is no `revalidate_scope`, `resolve_connection` or `release_reservation`, because #985 adds no route for them and mctl-api re-checks inside dispatch and the write permit). It SHALL contain no bridge port, SHALL never compute a command id, and SHALL store the `cmd_` returned by mctl-api. (owner decision, option b)
- THE SYSTEM SHALL map every (`outcome`, `provider_effect`, `error_code`) triple of the vendored v1alpha1 enums by the design "Result mapping (M9)" table, after the pair guard that reads `effect_state` with the triple (the workflow SHALL never report no effect against an observed or possible pair, nor `completed` against anything but an observed one), and IF `provider_effect` or the pair is `unknown` THEN `order_status` SHALL be `unknown` with no re-dispatch. Each M9 row states the order wire state (#957 §3a) it corresponds to: `refused` is wire `failed`, and `expired` and `cancelled` are both wire `cancelled`.
- THE SYSTEM SHALL take `approval_ref` and `fingerprint` from `GlovoControlInput` and SHALL NOT create an `aar_`. IF mctl-api reports a fingerprint mismatch at dispatch THEN THE SYSTEM SHALL end `refused`/`basket_changed`. Approval refusals SHALL be reported distinctly as `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `provider_disabled` or `tenant_busy`.
- THE SYSTEM SHALL call dispatch and cancel only through the routes of mctl-api#985, and SHALL expect to be started only by mctl-api#957's post-commit start dispatcher under the id `control_workflow_id` derives. (owner decisions D3, D5)
- THE SYSTEM SHALL carry refs and digests only: no read payload (history, preview, basket; mctl-api#986) SHALL appear in its input, activity results, signals or logs. (owner decision D1)
- THE SYSTEM SHALL accept `install_ref` as an M1a `gin_` id and `connection_ref` as an M1a `gcn_` id, and `tenant_ref`, `principal_ref`, `order_ref` only in the `tnr_`/`prr_`/`ordr_` forms minted by mctl-api.

## AMEND 2026-11-10 (independent review, AMEND): contract reconciliation against current main

Sources re-read on default branches: mctl-api `081bd6b7` (control routes #985 merged earlier,
#1001 merged as `675dff75`), mctl-agents main (#1062 merged as `46ccddce`), mctl-gitops main.
These items replace the text they name below; where this section and older text disagree, this
section wins. Items marked UNVERIFIED could not be confirmed against code and stay assumptions.

1. Contract names. mctl-api `internal/glovojoin/prepare.go` (`ControlInputSchemaVersion`) and
   `internal/glovojoin/contract/testdata/control-input.golden.json` use
   `glovo-control-input/v1alpha1` for the input. The result is `glovo-control-result/v1alpha1`
   (no mctl-api code reads it; owned here). `assistants.mctl.ai/glovo-control/v1alpha1` is dropped.
   prepare.go marks the version and `ControlLimits` (currently `{}`) as provisional until this
   schema is vendored, so `limits` members are all optional with defaults and bounds, and
   `limits: {}` is valid; unknown members are still rejected.
2. Start contract. Workflow type `GlovoControlWorkflow`, task queue `mctl-assistants-control`,
   exactly one argument of type bytes: the RFC 8785 bytes (as stored in
   `glovo.control_starts.input`). The strict raw-text pre-check (duplicate keys, non-integer
   numbers) runs first on those bytes, before any decode: a decoded dict would already have lost
   duplicate keys. How the mctl-api starter encodes the argument is UNVERIFIED on the mctl-api
   side (no starter was found on main); the golden consumer test of task 13 pins it once it exists.
3. Gating. mctl-api#985 control routes and #989 (mctl-api#1001, `675dff75`) are merged:
   vendoring `internal/glovo/control/contract/` is no longer blocked (`SHA256SUMS` digest
   `afb2e8de2fc709e7671deaa821268cc9ca3ba2d8ebceacb272c389c0954d0a06` at `675dff75` and at main
   `081bd6b7`; re-verify when vendoring). `BLOCKED_FOR_INTEGRATION` stays for the runtime only:
   docs/glovo-control.md says no production verifier mints the control principal until
   mctl-gitops#2506 (an open ZITADEL-versus-Vault issuer spike; the control-principal verifier is
   not yet in place) and no dispatcher is attached on main, so a mounted route answers 503
   `not_ready`.
4. Credentials. The static `MCTL_ASSISTANTS_TOKEN` is replaced by a credential-provider port
   for a bearer whose audience is exactly `mctl-api-glovo-control` (principal
   `service:glovo-control-worker`, permission `glovo:control-dispatch`; `internal/auth/glovo_control_worker.go`,
   docs/glovo-control.md). The issuer source is pending mctl-gitops#2506. The port refuses
   client-side a token that is not a control token (wrong audience). Temporal client auth uses
   the node A names `TEMPORAL_TOKEN_FILE`, `TEMPORAL_TLS_CA_FILE`, `TEMPORAL_TLS_SERVER_NAME`
   (VERIFIED_SOURCE: mctl-gitops `docs/runbooks/temporal-client-auth.md`, row "A. Client
   support": `TEMPORAL_TOKEN_FILE` is re-read at least every 5 minutes; only the mctl-agents
   implementation is UNVERIFIED, because mctl-agents#1057 is an open issue and no open PR for it
   was found), inert when unset, never logged, through a neutral shared module.
   `orchestrator.assistants` must not import `orchestrator.temporal.worker` (T2 enforces it);
   note that the DevLoop worker owns `Client.connect` today, so decision (c) must be taken with
   that in view. This proposal duplicates no #1057 work. The provider holds
   no Temporal credential (mctl-telegram#1276).
5. `orchestrator.action_approvals.intent_hash` import removed: after M10 the workflow never
   computes an intent. The allowed-import list shrinks accordingly.
6. OPEN-989-5 limit. The basket fingerprint may travel in Temporal history only for the
   synthetic, fake-only M1. A keyed digest is required before any real data; the ADR (task 11)
   states this.
7. Rate limiting. the mctl-api control routes never send `Retry-After` (not present in
   `internal/api/handlers_glovo_control.go` or docs/glovo-control.md; other mctl-api surfaces do
   send it: `internal/glovojoin/http.go`, openapi.yaml, docs/principals.md).
   When the header is absent the client uses bounded exponential backoff; when present it is
   honoured within the same bound.
8. Result enum source. mctl-agents#1059 is merged (#1062, `46ccddce`). `docs/contracts/bridge/v1alpha2/README.md`
   says there is no v1alpha2 write result: the unchanged v1alpha1 `result.schema.json`
   (`docs/spikes/1043/`) stays the result contract of `place_order_fake`, so the M9 enum domain is
   read from it. Prefer reusing the strict parsing of `tools/bridge_contract.py` over a local
   duplicate. `tools/bridge_contract.py` imports `jsonschema`, `referencing` and `jcs`
   (`tools/jcs.py`); `jsonschema` is in the dev dependency group of pyproject.toml only, the
   control image installs with `--no-dev`, and `tools/` is outside the image's minimal copy list,
   so availability in the image is UNVERIFIED (reuse needs the dependencies in the runtime group
   and `tools/` copied, or the pre-check stays local and stdlib-only).
9. `not_ready` currently maps to `refused`/`provider_disabled`, which conflates a transient
   not-ready (no dispatcher attached, readiness probe failed) with a disabled provider. See
   OPEN decision (e). The (`status`, `effect_state`) pair-class table stays a local copy
   (existing open item, unchanged).

OPEN owner decisions (recorded, not decided):

- (a) Schema version. Recommended: #1044 adopts `glovo-control-input/v1alpha1` (no mctl-api
  change). Alternative: mctl-api switches to the old `assistants.mctl.ai/...` string.
- (b) Image. Recommended: build-only in CI and let mctl-gitops#2576 own the reproducible build
  and digest pinning. Alternative: publish `ghcr.io/mctlhq/glovo-control-worker` (staged name)
  behind an off-by-default repo variable, never in release-deploy `values_path`.
- (c) Shared Temporal client module. #1057 is an open issue with no code yet, so "land #1057
  first" has nothing to wait on today. Recommended: one neutral shared module owned by the first
  PR that needs it, with `orchestrator.assistants` never importing `orchestrator.temporal.worker`;
  take the decision with the DevLoop worker's ownership of `Client.connect` in view.
- (d) Control token source: pending mctl-gitops#2506. Recommended: accept `BLOCKED_FOR_INTEGRATION`
  for the runtime at approval; the code, contract vendoring and tests ship now.
- (e) `not_ready` mapping (`provider_disabled` appears nowhere in mctl-api: it is only this
  workflow's mapping of `not_ready`; task 12's check that every table code exists in the vendored
  bodies must exclude workflow-only reason codes). Recommended: a distinct transient handling (bounded retry, then
  `unknown`/`dispatch_unconfirmed`, never `refused`) for the not-ready code, with
  `provider_disabled` kept for a genuinely disabled provider, if mctl-api can tell them apart.

Negative matrix (case -> named test):

| Case | Test |
|---|---|
| two tenants, two principals | T7 |
| wrong audience | T20 |
| missing team | T8 (`no_tenant`) |
| revoked connection | T8 |
| stale install | T8 |
| approval replay | T10 + T11 |
| foreign order | T21 (+ T7 foreign `command_id`) |
| ambiguous provider write | T13 + T9 |

UNVERIFIED, image health: probes, readiness endpoint and `readOnlyRootFilesystem` needs of the
worker image are not verified (no deployment exists; mctl-gitops#2576 decides).

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
  `glovo-control-input/v1alpha1` (input) and `glovo-control-result/v1alpha1` (result; amended
  2026-11-10, matching mctl-api prepare.go), every string length-bounded,
  every collection size-bounded, and unknown fields rejected, with the three `limits` members
  optional (defaults and bounds stated, `limits: {}` valid, unknown members rejected); a JSON Schema
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

Lifecycle (round 7: there is no separate revalidation call; mctl-api re-checks scope inside dispatch and the write permit):
- WHEN the workflow runs THE SYSTEM SHALL progress only through
  `awaiting_approval -> dispatching -> settling -> completed`
  (`quoting` removed 2026-11-09, M10; `resolving` removed in round 7), or terminate in
  `refused`, `cancelled`, `expired` or `failed`.
- WHEN `dispatch_order` is refused for scope reasons (`connection_revoked`,
  `connection_expired`, `stale_install`, `no_tenant` and the other codes of the design
  "Control refusal mapping (M10b)") THE SYSTEM SHALL end `refused` with the mapped reason
  and make zero provider dispatches.
- IF `read_command_result`, `cancel_order` or `read_approval` answers 503 `unavailable` THEN THE SYSTEM SHALL treat it as no information (retry, never a state); a cancellation counts only for a 200 whose `order_state` is `cancelled`.
- THE SYSTEM SHALL own the `reason_code` values that are not a row of mctl-api#957 §4.1 (design M10b, "Workflow-only reason codes") and SHALL NOT send them on the facade wire.
- IF `dispatch_order` cannot get a confirmed answer (mctl-api unavailable, timeout) THEN THE
  SYSTEM SHALL end `unknown` with reason `dispatch_unconfirmed` after bounded retries of the
  same idempotent call, SHALL NOT re-dispatch, and SHALL never proceed on an unknown answer.
- WHEN the workflow is cancelled THE SYSTEM SHALL issue no new provider dispatch, SHALL
  call only `cancel_order` (mctl-api#985 §6, idempotent), and SHALL never re-activate a
  revoked connection, a revoked consent or a spent `aar_`.

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
- (Amended 2026-11-09, round 7) WHEN the approval is `approved` THE SYSTEM SHALL call
  `dispatch_order` once (activity retries reuse the same call; a replay is answered with the
  same `cmd_` and the header `Idempotent-Replayed`, which the client treats as success) and
  SHALL store the returned `cmd_`. A `bridge-result` signal that arrives before `cmd_` is
  stored SHALL be ignored and recovered by polling `read_command_result`.
- WHEN a `bridge-result` signal arrives THE SYSTEM SHALL accept it only if its
  `command_id` equals the stored `cmd_` and the read-back digest matches, and
  SHALL treat a duplicate signal as a no-op.
- IF the provider effect is `unknown` THEN THE SYSTEM SHALL NOT re-dispatch and
  SHALL return `order_status=unknown`, leaving reconciliation to mctl-api's
  read-back (full map: the design "Result mapping (M9)").
- WHEN the workflow completes THE SYSTEM SHALL return a bounded
  `GlovoControlResult` with `order_status`, `reason_code`, `approval_ref`, `fingerprint` and
  `command_id` (no `handoff_ref`: no route returns one),
  and no provider payload, cookie, token or free text over 256 characters.

Integration gate (amended 2026-11-09):
- (Amended 2026-11-10: mctl-api#985/#989 are merged, mctl-api#1001 `675dff75`, so vendoring is unblocked; only the runtime stays `BLOCKED_FOR_INTEGRATION` until the control-principal verifier of mctl-gitops#2506 exists and a dispatcher is attached.) THE SYSTEM SHALL vendor the mctl-api#985 contract set (`internal/glovo/control/contract/*.json`
  and `SHA256SUMS`) under `orchestrator/assistants/api_contract/` with a `PROVENANCE` file, and
  `ASSISTANTS_API_CONTRACT` SHALL be `<commit>:<sha256 of SHA256SUMS>`; a test SHALL prove every
  refusal code of the vendored bodies has a row in the M10b table.
- WHILE `ASSISTANTS_API_CONTRACT` is missing or differs from the vendored `PROVENANCE` THE SYSTEM SHALL refuse to construct a real `ControlApiPort` and
  SHALL report `BLOCKED_FOR_INTEGRATION` at worker startup when one is
  requested.
- THE SYSTEM SHALL NOT implement or register a cross-namespace Temporal
  Activity, a raw Nexus endpoint, or any direct provider-to-control signal.

Resource budgets:
- THE SYSTEM SHALL set explicit `max_concurrent_activities`,
  `max_concurrent_workflow_tasks` and per-activity timeouts on the control
  worker from bounded env settings. The workflow lifetime is bounded by the approval wait
  (`aar_` expiry) plus `settle_timeout_s` from the input `limits`; there is no separate
  execution timeout.
- IF mctl-api answers a dispatch with `tenant_busy` THEN THE SYSTEM SHALL end `refused` with that
  reason (mctl-api#985 §2b) and write nothing. IF it answers `rate_limited` (429, nothing written) THEN THE
  SYSTEM SHALL retry with bounded backoff honouring `Retry-After` when present and bounded exponential backoff when absent (the control routes never send it; amended 2026-11-10), and on exhaustion end `unknown`/`dispatch_unconfirmed` as for `unavailable` (M10b); `rate_limited` is never a `reason_code`.

Safety:
- THE SYSTEM SHALL contain no Glovo HTTP client, no provider cookie or session
  handling, and no checkout, charge or payment operation; the only provider is
  synthetic.

## Out of scope

- Deploying anything: no Temporal namespace creation, no gitops service, no
  credentials, no Vault/ESO change (mctl-gitops#2457 and #2456 follow-ups).
- Changes to the DevLoop worker (`orchestrator/temporal/`), its queues,
  namespace `mctl-agents`, schedules, release-deploy paths or kuptsi.
- mctl-api routes, stores and authorization (mctl-api#957, #959-#961, #985-#989) and the
  merged bridge (mctl-api#968); this proposal codes against `ControlApiPort`.
- The public facade and the fake provider worker (mctl-telegram).
- Choosing the cross-namespace transport (decided 2026-11-09: mctl-api#968).
- Real Glovo access, payments, any LLM call from the control worker.
- A new scheduler or a second AutomationDefinition authority.

## Open questions

- Resolved 2026-11-09 (owner): mctl-api#968 is the canonical bridge; the
  workflow reaches it through mctl-api APIs only. The remaining gate is the
  dispatch/cancel route contract of mctl-api#985 (owner decision D3, 2026-11-09).
- Round 7: the mctl-api#985 control routes are proposals until merged; the vendored contract
  set and its pin make any change there a visible contract update here.
- Image publishing (amended 2026-11-10: see OPEN decision (b); staged name `ghcr.io/mctlhq/glovo-control-worker`): should CI push `ghcr.io/mctlhq/mctl-agents-assistants-control`
  on release (proposed: only behind a repo variable that defaults off, never
  wired into release-deploy `values_path`), or only build it as a CI smoke until
  #2457 is approved? Proposal assumes build-only by default.
- Workflow id format (`asst-glovo-<tenant_ref>-<principal_ref>-<install_ref>-<order_ref>`):
  mctl-api#957 §6c now derives the same id; confirmed by the design "Amendment" table.
- Live Temporal denial of DevLoop-namespace calls (start, signal, query, list,
  terminate) cannot be proven locally: the dev server has no authorizer. Local
  tests prove it structurally; the live matrix depends on #2456 enforcement.
- OPEN decisions (a)-(e) of "AMEND 2026-11-10" above are owner decisions, recommended but undecided.
- Open for mctl-api#985: add the (command `status`, `effect_state`) -> order wire state rows of §2a to the contract file set, so the pair class of design "Result mapping (M9)" is pinned by the vendored files and not by a copy kept here. Until then the class table is a labelled local copy and its test is the only drift check.
- Concurrency caps; proposed defaults are 20 activities and 20 workflow tasks, to be tuned
  with real numbers. The `limits` defaults (15 s, 15 s, 900 s) are an owner decision.
